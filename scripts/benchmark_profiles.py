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

# ---------------------------------------------------------------------------
# Built-in query set (covers all five Plesk doc sources)
# ---------------------------------------------------------------------------

BUILTIN_QUERIES: list[dict] = [
    # php-stubs
    {
        "query": "how to define default config settings for a Plesk extension",
        "relevant": ["ConfigDefaults", "getDefaults"],
        "category": "php-stubs",
    },
    {
        "query": "retrieve extension configuration values",
        "relevant": ["pm_Config", "getDefaults"],
        "category": "php-stubs",
    },
    {
        "query": "hook interface for Plesk modules",
        "relevant": ["pm_Hook_Interface", "Hook"],
        "category": "php-stubs",
    },
    # cli
    {
        "query": "restart Plesk service from command line",
        "relevant": ["plesk repair", "restart"],
        "category": "cli",
    },
    {
        "query": "create a new subscription via CLI",
        "relevant": ["subscription", "add"],
        "category": "cli",
    },
    # api
    {
        "query": "list all domains via Plesk REST API",
        "relevant": ["List of Domains", "admin-domain-list", "domain-list"],
        "category": "api",
    },
    {
        "query": "authenticate with Plesk API using secret key",
        "relevant": ["X-API-Key", "secret_key", "Authorization"],
        "category": "api",
    },
    # guide
    {
        "query": "add a custom button to Plesk panel",
        "relevant": ["button", "custom_buttons", "addButton"],
        "category": "guide",
    },
    {
        "query": "package a Plesk extension for distribution",
        "relevant": ["plesk ext", "package", ".zip"],
        "category": "guide",
    },
    # js-sdk
    {
        "query": "register a new page in Plesk JS SDK",
        "relevant": ["registerPage", "router"],
        "category": "js-sdk",
    },
    # cross-source
    {
        "query": "SSL certificate management",
        "relevant": ["certificate", "SSL", "TLS"],
        "category": None,
    },
    {
        "query": "backup and restore Plesk",
        "relevant": ["backup", "restore"],
        "category": None,
    },
]


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


# ---------------------------------------------------------------------------
# Single-profile benchmark
# ---------------------------------------------------------------------------


def run_benchmark(
    queries: list[dict],
    profile_name: str,
    top_k: int = 10,
    final_k: int = 5,
    refresh: bool = False,
) -> dict[str, Any]:
    """
    Run the full query set against the currently loaded server module
    (with PLESK_MODEL_PROFILE already set in the environment).

    Returns a results dict.
    """
    # Import lazily so env var is already set when server.py resolves the profile
    # We import the search function directly to bypass MCP serialisation overhead
    sys.path.insert(0, str(Path(__file__).parent.parent))
    os.environ["PLESK_MODEL_PROFILE"] = profile_name

    # Reset module-level singletons if re-importing in the same process
    import importlib

    import plesk_unified.server as srv

    importlib.reload(srv)

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

    hits = []
    reciprocal_ranks = []
    latencies = []

    for q in queries:
        t0 = time.perf_counter()

        table = srv.get_table()
        reranker = srv.get_reranker()

        candidate_limit = top_k if reranker else final_k
        search_op = table.search(q["query"])
        if q.get("category"):
            search_op = search_op.where(f"category = '{q['category']}'")

        results = search_op.limit(candidate_limit).to_list()

        if reranker and results:
            texts_raw = [r.get("text", "") for r in results]
            scores = reranker.predict([(q["query"], t) for t in texts_raw])
            ranked = sorted(
                zip(scores, results, strict=True), key=lambda x: x[0], reverse=True
            )
            results = [r for _, r in ranked[:final_k]]

        latency = time.perf_counter() - t0
        latencies.append(latency)

        result_texts = [r.get("text", "") for r in results]
        rank = _hit_rank(result_texts, q["relevant"])

        hits.append(1 if rank is not None else 0)
        reciprocal_ranks.append(1 / rank if rank is not None else 0.0)

    n = len(queries)
    return {
        "profile": profile_name,
        "n_queries": n,
        "hit_rate": sum(hits) / n if n else 0.0,
        "mrr": sum(reciprocal_ranks) / n if n else 0.0,
        "avg_latency_s": sum(latencies) / n if n else 0.0,
        "model_rss_mb": model_rss,
        "per_query": [
            {
                "query": q["query"],
                "hit": bool(hits[i]),
                "rr": reciprocal_ranks[i],
                "latency_s": latencies[i],
            }
            for i, q in enumerate(queries)
        ],
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Benchmark retrieval quality across mcp-plesk-unified model profiles."
        )
    )
    parser.add_argument(
        "--profiles",
        nargs="+",
        default=["light", "medium", "full"],
        help="Profiles to benchmark (default: light medium full)",
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
        help="Re-index all documentation (reset_db=True) for each profile before benchmarking.",
    )
    args = parser.parse_args()

    profiles_to_run = [args.profile] if args.profile else args.profiles

    # Load queries
    if args.queries:
        queries = json.loads(Path(args.queries).read_text(encoding="utf-8"))
        print(f"Loaded {len(queries)} queries from {args.queries}")
    else:
        queries = BUILTIN_QUERIES
        print(f"Using {len(queries)} built-in queries.")

    all_results = []
    for profile_name in profiles_to_run:
        print(f"\n{'=' * 60}")
        print(f"Benchmarking profile: {profile_name}")
        print("=" * 60)

        try:
            result = run_benchmark(
                queries,
                profile_name=profile_name,
                top_k=args.top_k,
                final_k=args.final_k,
                refresh=args.refresh,
            )
            all_results.append(result)

            print(f"  Hit Rate (HR@{args.final_k}) : {result['hit_rate']:.1%}")
            print(f"  MRR@{args.final_k}           : {result['mrr']:.3f}")
            print(f"  Avg latency      : {result['avg_latency_s']:.3f}s")
            print(f"  Model RSS delta  : {result['model_rss_mb']:.0f} MB")

            # Per-query breakdown
            print("\n  Per-query results:")
            for pq in result["per_query"]:
                status = "HIT " if pq["hit"] else "MISS"
                print(f"    {status} [{pq['latency_s']:.2f}s] {pq['query'][:70]}")

        except Exception as exc:
            print(f"  ERROR running profile '{profile_name}': {exc}")
            import traceback

            traceback.print_exc()

    # --- Summary table ---
    if len(all_results) > 1:
        print(f"\n{'=' * 60}")
        print("SUMMARY")
        print("=" * 60)
        header = (
            f"{'Profile':<10} {'HR@5':>8} {'MRR@5':>8} {'Latency':>10} {'RSS MB':>10}"
        )
        print(header)
        print("-" * len(header))
        for r in all_results:
            print(
                f"{r['profile']:<10} "
                f"{r['hit_rate']:>7.1%} "
                f"{r['mrr']:>8.3f} "
                f"{r['avg_latency_s']:>9.3f}s "
                f"{r['model_rss_mb']:>9.0f}"
            )

    # --- Optional JSON output ---
    if args.output:
        Path(args.output).write_text(
            json.dumps(all_results, indent=2), encoding="utf-8"
        )
        print(f"\nFull results written to {args.output}")


if __name__ == "__main__":
    main()
