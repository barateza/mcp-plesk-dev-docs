#!/usr/bin/env python3
"""
Terminal reporting helpers for benchmark results.

Pure presentation logic — no internal package dependencies.
"""

from __future__ import annotations

from typing import Any


def print_result(result: dict[str, Any], final_k: int) -> None:
    """Print a single profile/engine benchmark result."""
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


def print_summary_table(all_results: list[dict[str, Any]]) -> None:
    """Print a side-by-side comparison table of all benchmark results."""
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


def print_autoresearch_summary(all_results: list[dict[str, Any]]) -> None:
    """Print the autoresearch summary, highlighting the best structural config."""
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
