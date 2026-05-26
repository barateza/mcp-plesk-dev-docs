#!/usr/bin/env python3
"""
Core benchmark runner — executes retrieval benchmarks across model profiles.

This module depends on internal package APIs (AppContainer, SearchService, etc.)
and is the workhorse behind ``scripts/benchmark_profiles.py``.

Usage
-----
    from plesk_unified.benchmark_runner import run_benchmark

    results = run_benchmark(queries, profile_name="light")
"""

from __future__ import annotations

import asyncio
import gc
import os
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional
from unittest.mock import AsyncMock

import numpy as np

from plesk_unified.ai_client import AIClient
from plesk_unified.benchmark_engines import (
    DEFAULT_PILOT_CONFIG,
    StructurePilotConfig,
    bucket_query,
    rerank_with_structure,
    route_query,
)
from plesk_unified.platform_utils import get_optimal_device
from plesk_unified.tq_index import TurboQuantIndex
from plesk_unified.types import CategoryEnum

if TYPE_CHECKING:
    from plesk_unified.server.mcp_app import AppContainer


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
            # /proc may not exist on non-Linux or in containers
            pass  # nosec
    return 0.0


def _hit_rank(results: list[dict[str, Any]], relevant: list[str]) -> int | None:
    """Return 1-based rank of first hit, or None if no hit in top-k.

    Accepts list of dicts (SearchResult or pageindex-pilot result).
    """
    for rank, result in enumerate(results, start=1):
        text_to_check = result.get("text", "")
        lower = text_to_check.lower()
        if any(kw.lower() in lower for kw in relevant):
            return rank
    return None


# ---------------------------------------------------------------------------
# RAGAS (LLM-as-judge) evaluation
# ---------------------------------------------------------------------------


def evaluate_ragas_metrics(  # noqa: PLR0913
    query: str,
    answer: str,
    retrieved_context: str,
    ground_truth: str | None,
    reference_context: str | None,
    ai_client: AIClient,
    model: str | None = None,
) -> dict[str, float]:
    """
    Evaluate faithfulness, context recall, and context precision using an LLM judge.

    Parameters
    ----------
    query: The user's search query.
    answer: The generated answer to evaluate.
    retrieved_context: Concatenated retrieved chunks.
    ground_truth: Optional ideal answer (currently unused in scoring).
    reference_context: Optional reference context for recall evaluation.
    ai_client: An AIClient instance for LLM-based scoring.
    model: Optional model override for the judge LLM.

    Returns
    -------
    dict with keys ``faithfulness``, ``context_recall``, ``context_precision``.
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


def _add_ragas_summary(
    res: dict[str, Any], ragas_metrics: list[dict[str, float]]
) -> None:
    """Calculate and add aggregated RAGAS metrics to *res*."""
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


# ---------------------------------------------------------------------------
# Container bootstrap
# ---------------------------------------------------------------------------


def _load_container_for_profile(profile_name: str) -> AppContainer:
    """Load an AppContainer instance configured for the given profile."""
    from plesk_unified.settings import settings as global_settings
    from plesk_unified.server.bootstrap import create_app

    # Force the global settings singleton to use the requested profile.
    global_settings.plesk_model_profile = profile_name
    container = create_app(Path(os.getcwd()), global_settings)
    return container


# ---------------------------------------------------------------------------
# Engine / retrieval
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


def _perform_retrieval(  # noqa: PLR0913
    container: AppContainer,
    query_str: str,
    category: CategoryEnum | None,
    candidate_limit: int,
    final_k: int,
    selected_engine: str,
    selected_pilot_config: StructurePilotConfig | None,
) -> list[dict[str, Any]]:
    """Execute search and reranking steps using SearchService."""
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

    return initial_results[:final_k]


# ---------------------------------------------------------------------------
# TurboQuant
# ---------------------------------------------------------------------------


def _init_tq_index(container: AppContainer) -> TurboQuantIndex:
    """Initialise TQ index for the full-tq profile using AppContainer services."""
    tq_bits = int(os.getenv("TQ_BITS", "4"))
    tq_index = TurboQuantIndex(
        dim=container.settings.embedding_model_dimensions,
        bits=tq_bits,
        device=get_optimal_device(),
    )
    all_docs = container.lancedb_repo.get_table().search().limit(100000).to_list()
    if all_docs:
        corpus_vecs = np.array([doc["vector"] for doc in all_docs], dtype=np.float32)
        tq_index.add(corpus_vecs, all_docs)
    return tq_index


# ---------------------------------------------------------------------------
# Main benchmark entry point
# ---------------------------------------------------------------------------


def run_benchmark(  # noqa: PLR0913, PLR0915
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
    Run the full query set against the requested profile.

    Parameters
    ----------
    queries: List of query dicts with ``query``, ``relevant``, optional ``category``.
    profile_name: Model profile name (e.g. ``"light"``, ``"medium"``).
    top_k: ANN candidates before reranking.
    final_k: Number of final results returned.
    refresh: Whether to refresh the knowledge base first.
    engine_name: ``"baseline"`` or ``"pageindex-pilot"``.
    pilot_config: Structure pilot configuration (or ``None`` for default).
    routing_policy: Per-query routing policy.
    ragas: Whether to compute RAGAS metrics.
    ragas_model: Optional model override for the RAGAS judge.

    Returns
    -------
    dict with keys ``profile``, ``hit_rate``, ``mrr``, ``avg_latency_s``,
    ``model_rss_mb``, ``per_query``, ``bucket_metrics``, etc.
    """
    container = _load_container_for_profile(profile_name)
    rss_before = _rss_mb()

    # Force model initialisation through container services
    _ = container.model_runtime.get_embedding_model()
    _ = container.model_runtime.get_reranker()

    if refresh:
        print(f"  Refreshing knowledge base for profile '{profile_name}'...")
        dummy_ctx = AsyncMock()
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
        _init_tq_index(container)

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
            category = CategoryEnum(category_str)

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
        rank = _hit_rank(final_search_results, q["relevant"])

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
            retrieved_context = "\n".join(
                r.get("text", "") for r in final_search_results
            )
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
    res: dict[str, Any] = {
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

    # Clean up resources to prevent context leaks and memory accumulation
    container.shutdown()
    gc.collect()

    return res
