#!/usr/bin/env python3
"""Capture a machine-local retrieval baseline.

The committed baselines (``benchmarks/baselines/light.json`` and
``control.json``) were recorded on Apple Silicon and are the CI reference. Each
run records a ``machine`` fingerprint, so on another host the committed
baseline still gates quality (Hit Rate, MRR) but its latency is only a warning.
To gate latency on your own hardware, record a local reference once and compare
against that:

    python scripts/capture_local_baseline.py --profile light --samples 5

    PLESK_MODEL_PROFILE=light python scripts/benchmark_profiles.py \\
        --profile light --suite control \\
        --baseline-file benchmarks/baselines/light.local.json --fail-on-gate

Each sample runs in its own process because the gate itself runs one process
per invocation. ``--repeat`` inside ``benchmark_profiles.py`` reuses a single
process (and a warmed model runtime), so its timings are not comparable with a
gate run; this script spawns a fresh interpreter per sample instead.

Benchmark latency is only meaningful on an idle machine, so the script refuses
to record while CPU utilisation (measured over ``--sample-seconds``) exceeds
``--max-busy-percent`` (``--wait-seconds`` waits for it to settle; ``--force``
records anyway). CPU utilisation is used instead of the load average because a
shared or containerised host can report a high host-wide load while the CPUs a
run competes for are idle.

The output is machine-local and gitignored
(``benchmarks/baselines/*.local.json``).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

from mcp_plesk_dev_docs.benchmark_gates import build_baseline_payload

REPO_ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_SCRIPT = REPO_ROOT / "scripts" / "benchmark_profiles.py"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Capture a machine-local benchmark baseline by running the "
            "benchmark in a fresh process per sample."
        )
    )
    parser.add_argument(
        "--profile",
        default="light",
        help="Model profile to benchmark (default: light).",
    )
    parser.add_argument(
        "--suite",
        default="control",
        help="Benchmark suite to run (default: control).",
    )
    parser.add_argument(
        "--samples",
        type=int,
        default=5,
        help="Fresh-process samples to average (default: 5).",
    )
    parser.add_argument(
        "--output",
        help=(
            "Baseline artifact to write (default: "
            "benchmarks/baselines/<profile>.local.json)."
        ),
    )
    parser.add_argument(
        "--keep-samples",
        help="Directory to keep the per-sample JSON files in (default: temp).",
    )
    parser.add_argument(
        "--max-busy-percent",
        type=float,
        default=30.0,
        help=(
            "Refuse to record while CPU utilisation exceeds this percentage "
            "(default: 30)."
        ),
    )
    parser.add_argument(
        "--sample-seconds",
        type=float,
        default=2.0,
        help="Seconds to sample CPU utilisation over (default: 2).",
    )
    parser.add_argument(
        "--wait-seconds",
        type=float,
        default=0.0,
        help=(
            "Wait up to this many seconds for the machine to go quiet before "
            "giving up (default: 0, fail immediately)."
        ),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Record even when the machine is busy (timings will be inflated).",
    )
    return parser


def _cpu_busy_percent(interval: float) -> float | None:
    """Measure CPU utilisation over *interval* seconds, or None if unavailable."""
    stat = Path("/proc/stat")

    def sample() -> tuple[int, int]:
        fields = [int(part) for part in stat.read_text().splitlines()[0].split()[1:]]
        idle = fields[3] + (fields[4] if len(fields) > 4 else 0)
        return sum(fields), idle

    try:
        total_before, idle_before = sample()
        time.sleep(interval)
        total_after, idle_after = sample()
    except (OSError, ValueError, IndexError):
        return None
    total_delta = total_after - total_before
    if total_delta <= 0:
        return None
    busy = total_delta - (idle_after - idle_before)
    return max(0.0, 100.0 * busy / total_delta)


def _load_average() -> float | None:
    """Return the 1-minute load average, or None when unavailable."""
    try:
        return os.getloadavg()[0]
    except (AttributeError, OSError):
        return None


def _wait_for_quiet(args: argparse.Namespace) -> float:
    """Block until CPU utilisation is low enough. Returns busy percent."""
    deadline = time.monotonic() + args.wait_seconds
    while True:
        busy = _cpu_busy_percent(args.sample_seconds)
        if busy is None:
            print("CPU utilisation unavailable; recording anyway.")
            return 0.0
        if args.force:
            print(f"--force: recording at {busy:.0f}% CPU busy.")
            return busy
        if busy <= args.max_busy_percent:
            print(
                f"Machine quiet: CPU busy {busy:.0f}% "
                f"(limit {args.max_busy_percent:.0f}%)."
            )
            return busy
        if args.wait_seconds <= 0:
            raise SystemExit(
                f"Refusing to record a noisy baseline: CPU busy {busy:.0f}% "
                f"exceeds --max-busy-percent {args.max_busy_percent:.0f}. Re-run "
                "with --wait-seconds 1800, or --force to accept inflated timings."
            )
        if time.monotonic() >= deadline:
            raise SystemExit(
                f"Machine still busy after {args.wait_seconds:.0f}s "
                f"(CPU busy {busy:.0f}%); no baseline written. Re-run later, "
                "raise --wait-seconds, or use --force."
            )
        print(
            f"[{datetime.now():%H:%M:%S}] CPU busy {busy:.0f}%; waiting for "
            f"<= {args.max_busy_percent:.0f}%...",
            flush=True,
        )
        time.sleep(30)


def _run_sample(profile: str, suite: str, index: int, sample_dir: Path) -> dict:
    """Run one benchmark in a fresh process and return its captured payload."""
    sample_path = sample_dir / f"sample-{index}.json"
    env = dict(os.environ)
    env["PLESK_MODEL_PROFILE"] = profile
    command = [
        sys.executable,
        str(BENCHMARK_SCRIPT),
        "--profile",
        profile,
        "--suite",
        suite,
        "--capture-baseline",
        "--baseline-file",
        str(sample_path),
    ]
    print(f"[{index}] {profile}/{suite}: {' '.join(command[1:])}", flush=True)
    result = subprocess.run(command, cwd=REPO_ROOT, env=env, check=False)
    if result.returncode != 0:
        raise SystemExit(
            f"Sample {index} failed with exit code {result.returncode}; "
            "no baseline written."
        )
    return json.loads(sample_path.read_text(encoding="utf-8"))


def _print_summary(runs: list[dict], samples: int, busy_percent: float) -> None:
    print(
        f"\nMachine-local baseline ({samples} samples, {busy_percent:.0f}% CPU busy):"
    )
    for run in runs:
        print(
            f"  {run['profile']}/{run['suite']} "
            f"({run['engine']}, {run['routing_policy']}, n={run['n_runs']}): "
            f"HR@5={run.get('hit_rate', float('nan')):.3f} "
            f"MRR@5={run.get('mrr', float('nan')):.3f} "
            f"latency={run.get('avg_latency_s', float('nan')):.3f}s"
        )


def _resolve_output(args: argparse.Namespace) -> Path:
    if args.output:
        output = Path(args.output)
        if not output.is_absolute():
            output = (REPO_ROOT / output).resolve()
        return output
    return REPO_ROOT / "benchmarks" / "baselines" / f"{args.profile}.local.json"


def main() -> None:
    args = _build_parser().parse_args()
    if args.samples < 1:
        raise SystemExit("--samples must be at least 1")

    output = _resolve_output(args)
    busy_percent = _wait_for_quiet(args)
    load1 = _load_average()

    runs: list[dict] = []
    sample_dir_path: Path | None = (
        Path(args.keep_samples) if args.keep_samples else None
    )
    if sample_dir_path is not None:
        sample_dir_path.mkdir(parents=True, exist_ok=True)
        for index in range(1, args.samples + 1):
            sample = _run_sample(args.profile, args.suite, index, sample_dir_path)
            runs.extend(sample["runs"])
    else:
        with tempfile.TemporaryDirectory(prefix="plesk-baseline-") as tmp:
            sample_dir = Path(tmp)
            for index in range(1, args.samples + 1):
                sample = _run_sample(args.profile, args.suite, index, sample_dir)
                runs.extend(sample["runs"])

    payload = build_baseline_payload(runs)
    payload["capture"] = {
        "samples": args.samples,
        "cpu_busy_percent": round(busy_percent),
        "load1": round(load1, 2) if load1 is not None else None,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    _print_summary(payload["runs"], args.samples, busy_percent)
    try:
        shown = output.relative_to(REPO_ROOT)
    except ValueError:
        shown = output
    print(f"\nWrote {shown} ({args.samples} samples)")


if __name__ == "__main__":
    main()
