from pathlib import Path

from mcp_plesk_dev_docs.benchmark_gates import (
    aggregate_runs,
    evaluate_quality_gates,
    format_gate_report,
    load_baseline,
    load_gate_config,
    write_baseline,
)


def _run(
    *,
    suite="control",
    profile="pro",
    engine="baseline",
    routing_policy="baseline-only",
    hit_rate=1.0,
    mrr=0.95,
    avg_latency_s=1.0,
    **extra,
):
    payload = {
        "suite": suite,
        "profile": profile,
        "engine": engine,
        "routing_policy": routing_policy,
        "hit_rate": hit_rate,
        "mrr": mrr,
        "avg_latency_s": avg_latency_s,
    }
    payload.update(extra)
    return payload


def test_aggregate_runs_averages_repeats():
    runs = [_run(mrr=0.9), _run(mrr=1.0)]
    aggregated = aggregate_runs(runs)
    assert len(aggregated) == 1
    assert aggregated[0]["n_runs"] == 2
    assert aggregated[0]["mrr"] == 0.95


def test_write_and_load_baseline_roundtrip(tmp_path: Path):
    target = tmp_path / "baseline.json"
    runs = [_run(), _run(profile="local", mrr=0.9)]
    write_baseline(str(target), runs)

    loaded = load_baseline(str(target))
    assert len(loaded) == 2
    profiles = {r["profile"] for r in loaded}
    assert profiles == {"pro", "local"}


def test_quality_gate_passes_when_within_limits(tmp_path: Path):
    baseline_file = tmp_path / "baseline.json"
    write_baseline(str(baseline_file), [_run(mrr=0.95, avg_latency_s=1.0)])

    report = evaluate_quality_gates(
        [_run(mrr=0.94, avg_latency_s=1.15)],
        load_baseline(str(baseline_file)),
        load_gate_config(None),
    )

    assert report["passed"] is True
    assert report["failures"] == []


def test_quality_gate_fails_on_mrr_drop(tmp_path: Path):
    baseline_file = tmp_path / "baseline.json"
    write_baseline(str(baseline_file), [_run(mrr=0.95)])

    report = evaluate_quality_gates(
        [_run(mrr=0.80)],
        load_baseline(str(baseline_file)),
        load_gate_config(None),
    )

    assert report["passed"] is False
    assert any("mrr" in failure for failure in report["failures"])


def test_quality_gate_fails_on_required_metric(tmp_path: Path):
    baseline_file = tmp_path / "baseline.json"
    write_baseline(str(baseline_file), [_run()])

    gate_config = load_gate_config(None)
    gate_config["required_metrics"] = ["context_recall"]

    report = evaluate_quality_gates(
        [_run()],
        load_baseline(str(baseline_file)),
        gate_config,
    )

    assert report["passed"] is False
    assert any(
        "Missing required metric 'context_recall'" in f for f in report["failures"]
    )


def test_quality_gate_fails_on_absolute_minimum(tmp_path: Path):
    baseline_file = tmp_path / "baseline.json"
    write_baseline(str(baseline_file), [_run(context_recall=0.9)])

    current = [_run(context_recall=0.7)]
    report = evaluate_quality_gates(
        current,
        load_baseline(str(baseline_file)),
        load_gate_config(None),
    )

    assert report["passed"] is False
    assert any("context_recall" in f for f in report["failures"])


def test_format_gate_report_contains_header():
    text = format_gate_report(
        {
            "passed": True,
            "failures": [],
            "warnings": [],
            "current_count": 1,
            "baseline_count": 1,
        }
    )
    assert "QUALITY GATE REPORT" in text
