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
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

from plesk_unified.benchmark_engines import (
    DEFAULT_PILOT_CONFIG,
    StructurePilotConfig,
    bucket_query,
    get_pilot_configs,
    list_routing_policies,
    rerank_with_structure,
    route_query,
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


def _hit_rank(result_texts: list[str], relevant: list[str]) -> int | None:
    """Return 1-based rank of first hit, or None if no hit in top-k."""
    for rank, text in enumerate(result_texts, start=1):
        lower = text.lower()
        if any(kw.lower() in lower for kw in relevant):
            return rank
    return None


def _load_server_for_profile(profile_name: str):
    """Reload the server module after selecting the active profile."""
    sys.path.insert(0, str(Path(__file__).parent.parent))
    actual_profile_env = "full" if profile_name == "full-tq" else profile_name
    os.environ["PLESK_MODEL_PROFILE"] = actual_profile_env

    import importlib

    import plesk_unified.server as srv

    importlib.reload(srv)
    return srv


def _search_candidates(
    srv: Any,
    query: str,
    category: str | None,
    candidate_limit: int,
    profile_name: str,
    tq_index: TurboQuantIndex | None,
) -> list[dict[str, Any]]:
    """Return candidate documents using the active retrieval path."""
    if profile_name == "full-tq" and tq_index is not None:
        query_vec = np.asarray(
            srv.get_embedding_model().compute_query_embeddings(query)[0],
            dtype=np.float32,
        )
        tq_results = tq_index.search(
            query_vec,
            top_k=candidate_limit,
            category=category,
        )
        results = []
        for meta, score in tq_results:
            enriched = dict(meta)
            enriched["_score_tq"] = score
            results.append(enriched)
        return results

    table = srv.get_table()
    search_op = table.search(query)
    if category:
        search_op = search_op.where(f"category = '{category}'")
    return search_op.limit(candidate_limit).to_list()


# ---------------------------------------------------------------------------
# Single-profile benchmark
# ---------------------------------------------------------------------------


def run_benchmark(
    queries: list[dict],
    profile_name: str,
    top_k: int = 10,
    final_k: int = 5,
    refresh: bool = False,
    engine_name: str = "baseline",
    pilot_config: StructurePilotConfig | None = None,
    routing_policy: str = "baseline-only",
) -> dict[str, Any]:
    """
    Run the full query set against the currently loaded server module
    (with PLESK_MODEL_PROFILE already set in the environment).

    Returns a results dict.
    """
    srv = _load_server_for_profile(profile_name)

    rss_before = _rss_mb()

    # Force model initialisation
    _ = srv.get_embedding_model()
    _ = srv.get_reranker()

    if refresh:
        print(f"  Refreshing knowledge base for profile '{profile_name}'...")
        report = srv.refresh_knowledge(target_category="all", reset_db=True)
        print(f"  Refresh complete:\n{report}")

    rss_after = _rss_mb()
    model_rss = rss_after - rss_before

    tq_index: TurboQuantIndex | None = None
    if profile_name == "full-tq":
        tq_bits = int(os.getenv("TQ_BITS", "3"))
        tq_index = TurboQuantIndex(
            dim=1024,
            bits=tq_bits,
            device=srv._detect_device(),
        )
        all_docs = srv.get_table().search().limit(100000).to_list()
        if all_docs:
            corpus_vecs = np.array(
                [doc["vector"] for doc in all_docs], dtype=np.float32
            )
            tq_index.add(corpus_vecs, all_docs)

    hits = []
    reciprocal_ranks = []
    latencies = []
    query_meta: list[dict[str, Any]] = []
    bucket_hits: dict[str, list[int]] = {}
    bucket_rrs: dict[str, list[float]] = {}
    bucket_latencies: dict[str, list[float]] = {}

    for q in queries:
        t0 = time.perf_counter()
        bucket = q.get("bucket") or bucket_query(q["query"])

        bucket_hits.setdefault(bucket, [])
        bucket_rrs.setdefault(bucket, [])
        bucket_latencies.setdefault(bucket, [])

        if routing_policy and routing_policy != "baseline-only":
            decision = route_query(q["query"], bucket, routing_policy=routing_policy)
            selected_engine = decision.engine
            selected_pilot_config = decision.pilot_config
            routing_reason = decision.reason
        else:
            selected_engine = engine_name
            selected_pilot_config = pilot_config
            routing_reason = "manual-engine"

        reranker = srv.get_reranker()
        candidate_limit = (
            top_k if (reranker or selected_engine == "pageindex-pilot") else final_k
        )

        results = _search_candidates(
            srv,
            q["query"],
            q.get("category"),
            candidate_limit,
            profile_name,
            tq_index,
        )

        if reranker and results:
            texts_raw = [r.get("text", "") for r in results]
            scores = reranker.predict([(q["query"], t) for t in texts_raw])
            ranked = sorted(
                zip(scores, results, strict=True), key=lambda x: x[0], reverse=True
            )
            results = [r for _, r in ranked[:final_k]]

        if selected_engine == "pageindex-pilot" and results:
            results = rerank_with_structure(
                q["query"],
                results,
                config=selected_pilot_config or DEFAULT_PILOT_CONFIG,
            )[:final_k]

        latency = time.perf_counter() - t0
        latencies.append(latency)

        result_texts = [r.get("text", "") for r in results]
        rank = _hit_rank(result_texts, q["relevant"])

        hits.append(1 if rank is not None else 0)
        reciprocal_ranks.append(1 / rank if rank is not None else 0.0)
        bucket_hits[bucket].append(1 if rank is not None else 0)
        bucket_rrs[bucket].append(1 / rank if rank is not None else 0.0)
        bucket_latencies[bucket].append(latency)
        query_meta.append(
            {
                "bucket": bucket,
                "selected_engine": selected_engine,
                "selected_pilot_config": (
                    selected_pilot_config.name if selected_pilot_config else None
                ),
                "routing_reason": routing_reason,
            }
        )

    n = len(queries)
    return {
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
                "n": len(vals),
                "hit_rate": (
                    sum(bucket_hits[name]) / len(bucket_hits[name])
                    if bucket_hits[name]
                    else 0.0
                ),
                "mrr": (
                    sum(bucket_rrs[name]) / len(bucket_rrs[name])
                    if bucket_rrs[name]
                    else 0.0
                ),
                "avg_latency_s": (
                    sum(bucket_latencies[name]) / len(bucket_latencies[name])
                    if bucket_latencies[name]
                    else 0.0
                ),
            }
            for name, vals in bucket_hits.items()
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
            }
            for i, q in enumerate(queries)
        ],
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Benchmark retrieval quality across mcp-plesk-unified model profiles."
        )
    )
    parser.add_argument(
        "--profiles",
        nargs="+",
        default=["light", "medium", "full", "full-tq"],
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
        help=(
            "Re-index all documentation (reset_db=True) for each profile "
            "before benchmarking."
        ),
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
    header = (
        f"{'Profile':<10} {'Engine':<15} {'HR@5':>8} {'MRR@5':>8} "
        f"{'Latency':>10} {'RSS MB':>10}"
    )
    print(header)
    print("-" * len(header))
    for result in all_results:
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
    repeat_count = max(1, args.repeat)
    pilot_configs = {cfg.name: cfg for cfg in get_pilot_configs()}
    selected_pilot_config = pilot_configs.get(args.pilot_config, DEFAULT_PILOT_CONFIG)

    queries = _load_queries(args)

    all_results = []
    for repeat_idx in range(repeat_count):
        if repeat_count > 1:
            print(f"\n--- Repeat {repeat_idx + 1}/{repeat_count} ---")

        for profile_name in profiles_to_run:
            for engine_name in engines_to_run:
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
                        pilot_config=selected_pilot_config,
                        routing_policy=args.routing_policy,
                    )
                    result["repeat"] = repeat_idx + 1
                    all_results.append(result)

                    _print_result(result, args.final_k)

                except Exception as exc:
                    print(f"  ERROR running profile '{profile_name}': {exc}")
                    import traceback

                    traceback.print_exc()

    _print_summary_table(all_results)
    _print_autoresearch_summary(all_results)

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
