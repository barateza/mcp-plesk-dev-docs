#!/usr/bin/env python3
"""
CLI entry point for running retrieval benchmarks across Plesk model profiles.

Delegates to:
    - ``mcp_plesk_dev_docs.benchmark_runner.run_benchmark`` for execution logic.
    - ``scripts.benchmark_reporting`` for terminal output formatting.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from mcp_plesk_dev_docs.benchmark_engines import (
    DEFAULT_PILOT_CONFIG,
    StructurePilotConfig,
    get_pilot_configs,
    list_routing_policies,
)
from mcp_plesk_dev_docs.benchmark_gates import (
    evaluate_quality_gates,
    format_gate_report,
    load_baseline,
    load_gate_config,
    write_baseline,
)
from mcp_plesk_dev_docs.benchmark_suites import BENCHMARK_SUITES
from mcp_plesk_dev_docs.benchmark_runner import run_benchmark
from mcp_plesk_dev_docs.benchmark_reporting import (
    print_autoresearch_summary,
    print_result,
    print_summary_table,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Benchmark retrieval quality across mcp-plesk-dev-docs model profiles."
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


# ---------------------------------------------------------------------------
# CLI orchestration
# ---------------------------------------------------------------------------


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
                    print_result(result, args.final_k)
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

    print_summary_table(all_results)
    print_autoresearch_summary(all_results)
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
