#!/usr/bin/env python3
"""
Quality benchmark for mcp-plesk-unified model profiles.

Measures retrieval quality of each profile against a hand-labelled query set,
then prints a side-by-side comparison so you can make an informed trade-off.

Usage
-----
# Benchmark all profiles (requires a built index for each):
  python scripts/benchmark_profiles.py

# Benchmark a single profile (whatever PLESK_MODEL_PROFILE is set to):
  PLESK_MODEL_PROFILE=light python scripts/benchmark_profiles.py --profile light

# Use a custom query file instead of the built-in ones:
  python scripts/benchmark_profiles.py --queries my_queries.json

Query file format (JSON)
------------------------
A list of objects, each with:
  - "query"     : str    the search query
  - "relevant"  : list   substrings that MUST appear in at least one result
                          to count as a hit (case-insensitive)
  - "category"  : str?   optional category filter (same as search_plesk_unified)

Example:
  [
    {
      "query": "how to define default config settings for an extension",
      "relevant": ["ConfigDefaults", "getDefaults"],
      "category": "php-stubs"
    },
    {
      "query": "restart plesk service from CLI",
      "relevant": ["plesk repair", "service restart"],
      "category": "cli"
    }
  ]

Metrics reported
----------------
- Hit Rate (HR@5)  : fraction of queries where 61 relevant result appears in top-5
- MRR@5           : mean reciprocal rank (1/rank of first hit, averaged across queries)
- Avg latency     : wall-clock time per query (seconds)
- Peak RSS        : resident set size after loading models (MB)
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

import numpy as np

if TYPE_CHECKING:
    from plesk_unified.server.mcp_app import AppContainer

# New imports for AppContainer architecture
import asyncio
from plesk_unified.settings import PleskSettings
from plesk_unified.platform_utils import get_optimal_device
from plesk_unified.types import CategoryEnum
from unittest.mock import AsyncMock  # For dummy ctx and mocks for TQ index

from plesk_unified.ai_client import AIClient
from plesk_unified.benchmark_engines import (
    DEFAULT_PILOT_CONFIG,
    StructurePilotConfig,
    bucket_query,
    get_pilot_configs,
    list_routing_policies,
    rerank_with_structure,
    route_query,
)
from plesk_unified.benchmark_gates import (
    evaluate_quality_gates,
    format_gate_report,
    load_baseline,
    load_gate_config,
    write_baseline,
)
from plesk_unified.benchmark_suites import BENCHMARK_SUITES
from plesk_unified.tq_index import TurboQuantIndex

# ---------------------------------------------------------------------------
# Built-in query set (covers all five Plesk doc sources)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _rss_mb() -> float:
    """Return current process RSS in MB (cross-platform best-effort)."""
    try:
        import psutil  # type: ignore

        return psutil.Process().memory_info().rss / 1_048_576
    except ImportError:
        # Fallback: /proc/self/status on Linux
        try:
            status = Path("/proc/self/status").read_text()
            for line in status.splitlines():
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024
        except Exception:
            pass
    return 0.0


def _hit_rank(results: list[dict[str, Any]], relevant: list[str]) -> int | None:
    """Return 1-based rank of first hit, or None if no hit in top-k.
    Accepts list of dicts.
    """
    for rank, result in enumerate(results, start=1):
        # Assumed dict which should have 'text' key
        text_to_check = result.get("text", "")

        lower = text_to_check.lower()
        if any(kw.lower() in lower for kw in relevant):
            return rank
    return None


def evaluate_ragas_metrics(
    query: str,
    answer: str,
    retrieved_context: str,
    ground_truth: str | None,
    reference_context: str | None,
    ai_client: AIClient,
    model: str | None = None,
) -> dict[str, float]:
    """
    Evaluate faithfulness, context recall, and context precision using LLM judge.
    """
    model_list = [model] if model else None
    metrics = {}

    # 1. Faithfulness: Is the answer grounded in the retrieved context?
    prompt_f = (
        f"RETRIEVED CONTEXT:\n{retrieved_context}\n\n"
        f"ANSWER:\n{answer}\n\n"
        "Does the answer only use facts from the context? Score 0.0–1.0."
    )
    metrics["faithfulness"] = ai_client.evaluate_ragas_score(prompt_f, model_list)

    # 2. Context Recall: Did we retrieve the reference context?
    if reference_context:
        prompt_r = (
            f"REFERENCE CONTEXT:\n{reference_context}\n\n"
            f"RETRIEVED CONTEXT:\n{retrieved_context}\n\n"
            "Was the retrieved context able to recall key facts from the reference? "
            "Score 0.0–1.0."
        )
        metrics["context_recall"] = ai_client.evaluate_ragas_score(prompt_r, model_list)

    # 3. Context Precision: Are the retrieved chunks relevant to the query?
    prompt_p = (
        f"QUERY:\n{query}\n\n"
        f"RETRIEVED CONTEXT:\n{retrieved_context}\n\n"
        "Are the retrieved chunks relevant to answering the query? Score 0.0–1.0."
    )
    metrics["context_precision"] = ai_client.evaluate_ragas_score(prompt_p, model_list)

    return metrics


# Refactored to load AppContainer
def _load_container_for_profile(profile_name: str) -> AppContainer:
    """Load an AppContainer instance configured for the given profile."""
    # Ensure settings are reloaded with the new profile environment variable
    os.environ["PLESK_MODEL_PROFILE"] = profile_name

    from plesk_unified.server.bootstrap import create_app

    # Create fresh settings for this profile
    new_settings = PleskSettings()

    # Create the app container using the bootstrap logic
    container = create_app(Path(os.getcwd()), new_settings)
    return container


# ---------------------------------------------------------------------------
# Single-profile benchmark
# ---------------------------------------------------------------------------


def _get_selected_engine(
    query_str: str,
    bucket: str,
    routing_policy: str,
    engine_name: str,
    pilot_config: StructurePilotConfig | None,
) -> tuple[str, StructurePilotConfig | None, str]:
    """Determine the engine and pilot config based on the routing policy."""
    if routing_policy and routing_policy != "baseline-only":
        decision = route_query(query_str, bucket, routing_policy=routing_policy)
        return decision.engine, decision.pilot_config, decision.reason
    return engine_name, pilot_config, "manual-engine"


# Refactored _perform_retrieval
def _perform_retrieval(
    container: AppContainer,
    query_str: str,
    category: CategoryEnum | None,
    candidate_limit: int,  # This is the initial retrieval limit (top_k)
    final_k: int,
    selected_engine: str,
    selected_pilot_config: StructurePilotConfig | None,
) -> list[dict[str, Any]]:
    """Execute search and reranking steps using SearchService."""

    # SearchService.search_raw performs hybrid search and applies reranking.
    # It returns dict objects.
    initial_results: list[dict[str, Any]] = asyncio.run(
        container.search_service.search_raw(
            query=query_str,
            category=category.value if category else None,
        )
    )

    # PageIndex pilot is applied AFTER initial search and reranking.
    if selected_engine == "pageindex-pilot" and initial_results:
        reranked_dicts = rerank_with_structure(
            query_str,
            initial_results,
            config=selected_pilot_config or DEFAULT_PILOT_CONFIG,
        )[:final_k]
        return reranked_dicts

    # If not pageindex-pilot, just return the initial results, truncated to final_k
    return initial_results[:final_k]


def run_benchmark(
    queries: list[dict],
    profile_name: str,
    top_k: int = 10,
    final_k: int = 5,
    refresh: bool = False,
    engine_name: str = "baseline",
    pilot_config: StructurePilotConfig | None = None,
    routing_policy: str = "baseline-only",
    ragas: bool = False,
    ragas_model: str | None = None,
) -> dict[str, Any]:
    """
    Run the full query set against the currently loaded AppContainer.
    """
    container = _load_container_for_profile(profile_name)
    rss_before = _rss_mb()

    # Force model initialisation - now through container services
    _ = container.model_runtime.get_embedding_model()
    _ = container.model_runtime.get_reranker()

    if refresh:
        print(f"  Refreshing knowledge base for profile '{profile_name}'...")
        dummy_ctx = AsyncMock()  # Create a dummy ctx for refresh_knowledge
        report = asyncio.run(
            container.indexing_service.refresh_knowledge(
                progress_callback=dummy_ctx.report_progress,
                category="all",
                reset_db=True,
            )
        )
        print(f"  Refresh complete:\n{report}")

    rss_after = _rss_mb()
    model_rss = rss_after - rss_before

    if container.model_runtime.get_profile().use_turboquant:
        # Initialize TQ index. This should ideally be handled by the WarmupService,
        # but for benchmarking, we might want to ensure it's fresh.
        _init_tq_index_new(container)

    ai_client = AIClient() if ragas else None

    hits, reciprocal_ranks, latencies = [], [], []
    query_meta: list[dict[str, Any]] = []
    bucket_metrics_raw: dict[str, dict[str, list]] = {}
    ragas_metrics: list[dict[str, float]] = []

    for q in queries:
        t0 = time.perf_counter()
        bucket = q.get("bucket") or bucket_query(q["query"])
        category_str = q.get("category")
        category: Optional[CategoryEnum] = None
        if category_str and category_str != "mixed":
            category = CategoryEnum(
                category_str
            )  # Convert to Enum or leave as str for search

        bm = bucket_metrics_raw.setdefault(
            bucket, {"hits": [], "rrs": [], "latencies": []}
        )

        sel_engine, sel_pilot, reason = _get_selected_engine(
            q["query"], bucket, routing_policy, engine_name, pilot_config
        )

        final_search_results = _perform_retrieval(
            container,
            q["query"],
            category,
            top_k,
            final_k,
            sel_engine,
            sel_pilot,
        )

        latency = time.perf_counter() - t0

        # Extract content for _hit_rank and RAGAS evaluation
        # _hit_rank expects a list of SearchResult or dict from pageindex-pilot
        rank = _hit_rank(final_search_results, q["relevant"])

        # Record metrics
        hit_val = 1 if rank is not None else 0
        rr_val = 1 / rank if rank is not None else 0.0
        hits.append(hit_val)
        reciprocal_ranks.append(rr_val)
        latencies.append(latency)
        bm["hits"].append(hit_val)
        bm["rrs"].append(rr_val)
        bm["latencies"].append(latency)

        current_ragas = {}
        if ragas and ai_client:
            # Reconstruct retrieved_context from dicts
            retrieved_context = "\n".join(
                r.get("text", "") for r in final_search_results
            )

            # Fix faithfulness: generate a real LLM answer based on retrieved context
            # rather than using the ground truth as the "answer" field.
            gen_answer = ai_client.generate_answer(q["query"], retrieved_context)
            current_ragas = evaluate_ragas_metrics(
                q["query"],
                gen_answer,
                retrieved_context,
                q.get("ground_truth"),
                q.get("reference_context"),
                ai_client,
                ragas_model,
            )
        ragas_metrics.append(current_ragas)

        top_score = (
            final_search_results[0].get("_relevance", 0.0)
            if final_search_results
            else 0.0
        )
        query_meta.append(
            {
                "query": q["query"],
                "hit": rank is not None,
                "rr": rr_val,
                "score": top_score,
                "latency_s": latency,
                "bucket": bucket,
                "selected_engine": sel_engine,
                "selected_pilot_config": sel_pilot.name if sel_pilot else "base",
                "routing_reason": reason,
            }
        )

    n = len(queries)
    res = {
        "profile": profile_name,
        "n_queries": n,
        "hit_rate": sum(hits) / n if n else 0.0,
        "mrr": sum(reciprocal_ranks) / n if n else 0.0,
        "avg_latency_s": sum(latencies) / n if n else 0.0,
        "model_rss_mb": model_rss,
        "engine": engine_name,
        "pilot_config": pilot_config.name if pilot_config else None,
        "routing_policy": routing_policy,
        "bucket_metrics": {
            name: {
                "n": len(m["hits"]),
                "hit_rate": sum(m["hits"]) / len(m["hits"]) if m["hits"] else 0.0,
                "mrr": sum(m["rrs"]) / len(m["rrs"]) if m["rrs"] else 0.0,
                "avg_latency_s": (
                    sum(m["latencies"]) / len(m["latencies"]) if m["latencies"] else 0.0
                ),
            }
            for name, m in bucket_metrics_raw.items()
        },
        "per_query": [
            {
                "query": q["query"],
                "hit": bool(hits[i]),
                "rr": reciprocal_ranks[i],
                "latency_s": latencies[i],
                "bucket": query_meta[i]["bucket"],
                "selected_engine": query_meta[i]["selected_engine"],
                "selected_pilot_config": query_meta[i]["selected_pilot_config"],
                "routing_reason": query_meta[i]["routing_reason"],
                **ragas_metrics[i],
            }
            for i, q in enumerate(queries)
        ],
    }

    if ragas:
        _add_ragas_summary(res, ragas_metrics)

    return res


# Refactored _init_tq_index
def _init_tq_index_new(container: AppContainer) -> TurboQuantIndex:
    """Initialise TQ index for the full-tq profile using AppContainer services."""
    tq_bits = int(os.getenv("TQ_BITS", "4"))
    tq_index = TurboQuantIndex(
        dim=container.settings.embedding_model_dimensions,
        bits=tq_bits,
        device=get_optimal_device(),  # Use platform_utils
    )
    # Get all documents from LanceDB for the current profile's table
    # This might be very large, consider sampling or a more efficient way
    all_docs = container.lancedb_repo.get_table().search().limit(100000).to_list()
    if all_docs:
        corpus_vecs = np.array([doc["vector"] for doc in all_docs], dtype=np.float32)
        tq_index.add(corpus_vecs, all_docs)
    return tq_index


def _add_ragas_summary(
    res: dict[str, Any], ragas_metrics: list[dict[str, float]]
) -> None:
    """Calculate and add aggregated RAGAS metrics to results."""

    evaluated = [m for m in ragas_metrics if m]
    if evaluated:
        res["faithfulness"] = sum(m.get("faithfulness", 0.0) for m in evaluated) / len(
            evaluated
        )
        res["context_recall"] = sum(
            m.get("context_recall", 0.0) for m in evaluated
        ) / len(evaluated)
        res["context_precision"] = sum(
            m.get("context_precision", 0.0) for m in evaluated
        ) / len(evaluated)
        res["ragas_n_evaluated"] = len(evaluated)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Benchmark retrieval quality across mcp-plesk-unified model profiles."
        )
    )
    parser.add_argument(
        "--profiles",
        nargs="+",
        default=["local", "pro", "sandbox"],
        help="Profiles to benchmark (default: light medium full full-tq)",
    )
    parser.add_argument(
        "--profile",
        help="Benchmark a single profile (shortcut for --profiles X).",
    )
    parser.add_argument(
        "--queries",
        help="Path to a JSON file with custom queries (see docstring for format).",
    )
    parser.add_argument(
        "--suite",
        choices=sorted(BENCHMARK_SUITES),
        default="control",
        help="Built-in query suite to run (default: control).",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=10,
        help="ANN candidates before reranking (default: 10)",
    )
    parser.add_argument(
        "--final-k",
        type=int,
        default=5,
        help="Final results returned (default: 5)",
    )
    parser.add_argument(
        "--output",
        help="Write full JSON results to this file.",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        default=False,
        help="Incremental refresh before benchmarking.",
    )
    parser.add_argument(
        "--reset-db",
        action="store_true",
        default=False,
        help="Wipe and rebuild the index from scratch (use with --refresh).",
    )
    parser.add_argument(
        "--engine",
        choices=["baseline", "pageindex-pilot"],
        default="baseline",
        help="Retrieval engine to benchmark (default: baseline).",
    )
    parser.add_argument(
        "--autoresearch",
        action="store_true",
        default=False,
        help="Run both baseline and pageindex-pilot engines for comparison.",
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="Repeat each engine/profile run this many times for autoresearch.",
    )
    parser.add_argument(
        "--pilot-config",
        default="base",
        help="PageIndex pilot config name (default: base).",
    )
    parser.add_argument(
        "--routing-policy",
        choices=sorted(list_routing_policies()),
        default="baseline-only",
        help="Per-query routing policy (default: baseline-only).",
    )
    parser.add_argument(
        "--capture-baseline",
        action="store_true",
        default=False,
        help="Capture aggregated benchmark output as baseline artifact.",
    )
    parser.add_argument(
        "--baseline-file",
        help=(
            "Path to baseline artifact for capture or comparison. "
            "If omitted with --capture-baseline, defaults to "
            "benchmarks/baselines/<suite>.json"
        ),
    )
    parser.add_argument(
        "--gate-config",
        help=(
            "Path to quality-gate JSON config. "
            "Defaults to built-in thresholds when omitted."
        ),
    )
    parser.add_argument(
        "--fail-on-gate",
        action="store_true",
        default=False,
        help="Exit with non-zero status when any quality gate fails.",
    )
    parser.add_argument(
        "--ragas",
        action="store_true",
        default=False,
        help="Enable RAGAS metrics evaluation using LLM judge.",
    )
    parser.add_argument(
        "--ragas-model",
        help="LLM model to use as RAGAS judge (default from AIClient).",
    )
    return parser


def _load_queries(args: argparse.Namespace) -> list[dict]:
    if args.queries:
        queries = json.loads(Path(args.queries).read_text(encoding="utf-8"))
        print(f"Loaded {len(queries)} queries from {args.queries}")
        return queries

    queries = BENCHMARK_SUITES[args.suite]
    print(f"Using {len(queries)} built-in queries from suite '{args.suite}'.")
    return queries


def _print_result(result: dict[str, Any], final_k: int) -> None:
    print(f"  Hit Rate (HR@{final_k}) : {result['hit_rate']:.1%}")
    print(f"  MRR@{final_k}           : {result['mrr']:.3f}")
    if "faithfulness" in result:
        print(f"  Faithfulness       : {result['faithfulness']:.3f}")
        print(f"  Context Recall     : {result['context_recall']:.3f}")
        print(f"  Context Precision  : {result['context_precision']:.3f}")
    print(f"  Avg latency      : {result['avg_latency_s']:.3f}s")
    print(f"  Model RSS delta  : {result['model_rss_mb']:.0f} MB")
    print(f"  Routing policy   : {result['routing_policy']}")
    if result.get("bucket_metrics"):
        for bucket_name, metrics in result["bucket_metrics"].items():
            print(
                f"  {bucket_name.title()} MRR  : {metrics.get('mrr', 0.0):.3f} "
                f"(n={metrics.get('n', 0)})"
            )

    print("\n  Per-query results:")
    for pq in result["per_query"]:
        status = "HIT " if pq["hit"] else "MISS"
        print(
            f"    {status} [{pq['latency_s']:.2f}s] [{pq['bucket']}] "
            f"[{pq['selected_engine']}] {pq['query'][:70]}"
        )


def _print_summary_table(all_results: list[dict[str, Any]]) -> None:
    if len(all_results) <= 1:
        return

    print(f"\n{'=' * 60}")
    print("SUMMARY")
    print("=" * 60)
    has_ragas = any("faithfulness" in r for r in all_results)
    if has_ragas:
        header = (
            f"{'Profile':<10} {'Engine':<15} {'HR@5':>8} {'MRR@5':>8} "
            f"{'Faith':>8} {'Recall':>8} {'Prec':>8} {'Latency':>10}"
        )
    else:
        header = (
            f"{'Profile':<10} {'Engine':<15} {'HR@5':>8} {'MRR@5':>8} "
            f"{'Latency':>10} {'RSS MB':>10}"
        )
    print(header)
    print("-" * len(header))
    for result in all_results:
        if has_ragas:
            print(
                f"{result['profile']:<10} {result['engine']:<15} "
                f"{result['hit_rate']:>7.1%} "
                f"{result['mrr']:>8.3f} "
                f"{result.get('faithfulness', 0.0):>8.3f} "
                f"{result.get('context_recall', 0.0):>8.3f} "
                f"{result.get('context_precision', 0.0):>8.3f} "
                f"{result['avg_latency_s']:>9.3f}s"
            )
        else:
            print(
                f"{result['profile']:<10} {result['engine']:<15} "
                f"{result['hit_rate']:>7.1%} "
                f"{result['mrr']:>8.3f} "
                f"{result['avg_latency_s']:>9.3f}s "
                f"{result['model_rss_mb']:>9.0f}"
            )


def _print_autoresearch_summary(all_results: list[dict[str, Any]]) -> None:
    if not all_results:
        return

    pageindex_runs = [r for r in all_results if r.get("engine") == "pageindex-pilot"]
    if not pageindex_runs:
        return

    structural_best = max(
        pageindex_runs,
        key=lambda r: r.get("bucket_metrics", {}).get("structural", {}).get("mrr", 0.0),
    )
    structural_metrics = structural_best.get("bucket_metrics", {}).get("structural", {})
    structural_mrr = structural_metrics.get("mrr", 0.0)
    print("\nAUTORESEARCH SUMMARY")
    print("-" * 60)
    print(
        f"Best structural config: {structural_best.get('pilot_config') or 'base'} "
        f"(MRR={structural_mrr:.3f})"
    )
    print(
        "Stop condition: if the structural MRR no longer improves across the "
        "pilot configs, "
        "the structure-aware ceiling has been reached."
    )


def _execute_benchmark_matrix(
    profiles: list[str],
    engines: list[str],
    repeat_count: int,
    queries: list[dict],
    args: argparse.Namespace,
    pilot_config: StructurePilotConfig | None,
) -> list[dict[str, Any]]:
    """Run the benchmark for all profile/engine combinations across repeats."""
    all_results = []
    for repeat_idx in range(repeat_count):
        if repeat_count > 1:
            print(f"\n--- Repeat {repeat_idx + 1}/{repeat_count} ---")

        for profile_name in profiles:
            for engine_name in engines:
                print(f"\n{'=' * 60}")
                print(f"Benchmarking profile: {profile_name} | engine: {engine_name}")
                print("=" * 60)

                try:
                    result = run_benchmark(
                        queries,
                        profile_name=profile_name,
                        top_k=args.top_k,
                        final_k=args.final_k,
                        refresh=args.refresh and repeat_idx == 0,
                        engine_name=engine_name,
                        pilot_config=pilot_config,
                        routing_policy=args.routing_policy,
                        ragas=args.ragas,
                        ragas_model=args.ragas_model,
                    )
                    result["suite"] = args.suite
                    result["repeat"] = repeat_idx + 1
                    all_results.append(result)
                    _print_result(result, args.final_k)
                except Exception as exc:
                    print(f"  ERROR running profile '{profile_name}': {exc}")
                    import traceback

                    traceback.print_exc()
    return all_results


def _handle_baseline_and_gates(
    args: argparse.Namespace, all_results: list[dict[str, Any]]
) -> None:
    """Process baseline capture and quality gate evaluation."""
    baseline_path = args.baseline_file
    if args.capture_baseline:
        if not baseline_path:
            baseline_path = f"benchmarks/baselines/{args.suite}.json"
        write_baseline(baseline_path, all_results)
        print(f"\nBaseline captured to {baseline_path}")

    if (
        baseline_path and not args.capture_baseline
    ):  # Only load if not capturing new baseline
        baseline_runs = load_baseline(baseline_path)
        gate_config = load_gate_config(args.gate_config)
        gate_report = evaluate_quality_gates(all_results, baseline_runs, gate_config)
        print(format_gate_report(gate_report))
        if args.fail_on_gate and not gate_report["passed"]:
            raise SystemExit(2)


def _run_benchmark_cli(args: argparse.Namespace) -> None:
    profiles_to_run = [args.profile] if args.profile else args.profiles
    engines_to_run = (
        ["baseline", "pageindex-pilot"] if args.autoresearch else [args.engine]
    )
    if args.routing_policy != "baseline-only" and args.autoresearch:
        print(
            "Routing policy is active; ignoring --autoresearch and using a "
            "single routed run."
        )
        engines_to_run = [args.engine]

    pilot_configs = {cfg.name: cfg for cfg in get_pilot_configs()}
    selected_pilot_config = pilot_configs.get(args.pilot_config, DEFAULT_PILOT_CONFIG)
    queries = _load_queries(args)

    all_results = _execute_benchmark_matrix(
        profiles_to_run,
        engines_to_run,
        max(1, args.repeat),
        queries,
        args,
        selected_pilot_config,
    )

    _print_summary_table(all_results)
    _print_autoresearch_summary(all_results)
    _handle_baseline_and_gates(args, all_results)

    if args.output:
        Path(args.output).write_text(
            json.dumps(all_results, indent=2), encoding="utf-8"
        )
        print(f"\nFull results written to {args.output}")


def main() -> None:
    args = _build_parser().parse_args()
    _run_benchmark_cli(args)


if __name__ == "__main__":
    main()
