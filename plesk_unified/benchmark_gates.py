from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

DEFAULT_GATE_CONFIG: dict[str, Any] = {
    "regression": {
        "hit_rate": {"max_drop": 0.01},
        "mrr": {"max_drop": 0.02},
        "avg_latency_s": {"max_increase_ratio": 0.20},
    },
    "absolute_minimums": {
        "context_recall": 0.85,
        "faithfulness": 0.90,
    },
    "required_metrics": [],
}

_NUMERIC_METRICS = (
    "hit_rate",
    "mrr",
    "avg_latency_s",
    "faithfulness",
    "context_recall",
    "context_precision",
)


def _identity(run: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(run.get("suite", "control")),
        str(run.get("profile", "unknown")),
        str(run.get("engine", "baseline")),
        str(run.get("routing_policy", "baseline-only")),
    )


def _identity_string(run: dict[str, Any]) -> str:
    suite, profile, engine, routing = _identity(run)
    return (
        f"suite={suite}, profile={profile}, engine={engine}, routing_policy={routing}"
    )


def aggregate_runs(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate repeated runs by identity, averaging numeric quality metrics."""
    grouped: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for run in runs:
        grouped.setdefault(_identity(run), []).append(run)

    aggregated: list[dict[str, Any]] = []
    for key, items in grouped.items():
        base = {
            "suite": key[0],
            "profile": key[1],
            "engine": key[2],
            "routing_policy": key[3],
            "n_runs": len(items),
        }
        for metric in _NUMERIC_METRICS:
            values = [
                item[metric]
                for item in items
                if isinstance(item.get(metric), (int, float))
            ]
            if values:
                base[metric] = float(mean(values))
        aggregated.append(base)

    aggregated.sort(key=_identity)
    return aggregated


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load_gate_config(path: str | None) -> dict[str, Any]:
    config = dict(DEFAULT_GATE_CONFIG)
    if not path:
        return config

    override = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(override, dict):
        raise ValueError("Gate config must be a JSON object.")
    return _deep_merge(config, override)


def build_baseline_payload(runs: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "runs": aggregate_runs(runs),
    }


def write_baseline(path: str, runs: list[dict[str, Any]]) -> dict[str, Any]:
    payload = build_baseline_payload(runs)
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def load_baseline(path: str) -> list[dict[str, Any]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return aggregate_runs(payload)
    if isinstance(payload, dict) and isinstance(payload.get("runs"), list):
        return aggregate_runs(payload["runs"])
    raise ValueError("Baseline file must be a JSON list or object with 'runs'.")


def evaluate_quality_gates(
    current_runs: list[dict[str, Any]],
    baseline_runs: list[dict[str, Any]],
    gate_config: dict[str, Any],
) -> dict[str, Any]:
    current = aggregate_runs(current_runs)
    baseline_map = {_identity(run): run for run in aggregate_runs(baseline_runs)}

    failures: list[str] = []
    warnings: list[str] = []

    regression_cfg = gate_config.get("regression", {})
    absolute_cfg = gate_config.get("absolute_minimums", {})
    required_metrics = gate_config.get("required_metrics", [])

    for run in current:
        ident = _identity(run)
        run_name = _identity_string(run)
        baseline = baseline_map.get(ident)

        if baseline is None:
            warnings.append(f"No baseline run matched: {run_name}")
            continue

        for metric in required_metrics:
            if metric not in run:
                failures.append(
                    f"Missing required metric '{metric}' in current run: {run_name}"
                )

        for metric, cfg in regression_cfg.items():
            if metric not in run:
                warnings.append(f"Metric '{metric}' missing in current run: {run_name}")
                continue
            if metric not in baseline:
                warnings.append(
                    f"Metric '{metric}' missing in baseline run: {run_name}"
                )
                continue

            current_value = float(run[metric])
            baseline_value = float(baseline[metric])

            if "max_drop" in cfg:
                drop = baseline_value - current_value
                if drop > float(cfg["max_drop"]):
                    failures.append(
                        f"Regression gate failed for {metric} ({run_name}): "
                        f"drop={drop:.4f}, allowed={float(cfg['max_drop']):.4f}"
                    )
            if "max_increase_ratio" in cfg and baseline_value > 0:
                increase_ratio = (current_value - baseline_value) / baseline_value
                if increase_ratio > float(cfg["max_increase_ratio"]):
                    failures.append(
                        f"Regression gate failed for {metric} ({run_name}): "
                        f"increase_ratio={increase_ratio:.4f}, "
                        f"allowed={float(cfg['max_increase_ratio']):.4f}"
                    )

        for metric, threshold in absolute_cfg.items():
            if metric not in run:
                warnings.append(
                    f"Absolute gate metric '{metric}' missing in current run: {run_name}"
                )
                continue
            if float(run[metric]) < float(threshold):
                failures.append(
                    f"Absolute gate failed for {metric} ({run_name}): "
                    f"value={float(run[metric]):.4f}, threshold={float(threshold):.4f}"
                )

    return {
        "passed": len(failures) == 0,
        "failures": failures,
        "warnings": warnings,
        "current_count": len(current),
        "baseline_count": len(baseline_map),
    }


def format_gate_report(report: dict[str, Any]) -> str:
    lines = [
        "\nQUALITY GATE REPORT",
        "-" * 60,
        f"Current runs : {report.get('current_count', 0)}",
        f"Baseline runs: {report.get('baseline_count', 0)}",
    ]

    warnings = report.get("warnings", [])
    failures = report.get("failures", [])

    if warnings:
        lines.append("Warnings:")
        lines.extend(f"  - {w}" for w in warnings)

    if failures:
        lines.append("Failures:")
        lines.extend(f"  - {f}" for f in failures)
    else:
        lines.append("All configured quality gates passed.")

    return "\n".join(lines)
