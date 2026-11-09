"""Keep user-facing profile docs, the benchmark CLI, and baselines honest.

``mcp_plesk_dev_docs.domain.models._PROFILES`` is the single source of truth
for model-profile names. These tests fail when ``.env.example``, the benchmark
CLI, or a committed baseline artifact drifts away from it — the regression
described in issue #94 (``local`` / ``pro`` / ``sandbox`` were documented long
after they had been renamed).
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from mcp_plesk_dev_docs.domain.models import _PROFILES, DEFAULT_PROFILE

if TYPE_CHECKING:
    from collections.abc import Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
ENV_EXAMPLE = REPO_ROOT / ".env.example"
BENCHMARK_SCRIPT = REPO_ROOT / "scripts" / "benchmark_profiles.py"
BASELINES_DIR = REPO_ROOT / "benchmarks" / "baselines"

_PROFILE_LINE = re.compile(r"^#\s+(?P<name>[a-z][a-z0-9-]*)\s+~", re.MULTILINE)
_PROFILE_DEFAULT = re.compile(r"^PLESK_MODEL_PROFILE=(?P<value>\S+)\s*$", re.MULTILINE)


def _parse_env_example(path: Path) -> tuple[list[str], str]:
    """Return the documented profile names and the configured default."""
    text = path.read_text(encoding="utf-8")
    header = re.search(r"^# MODEL PROFILE$", text, re.MULTILINE)
    assert header, f"{path} has no MODEL PROFILE section"

    tail = text[header.end() :]
    default = _PROFILE_DEFAULT.search(tail)
    assert default, f"{path} does not set PLESK_MODEL_PROFILE"

    # Only the comment block above the setting documents selectable names.
    section = tail[: default.start()]
    names: list[str] = []
    for match in _PROFILE_LINE.finditer(section):
        name = match.group("name")
        if name not in names:
            names.append(name)
    return names, default.group("value")


def _assert_known_profiles(
    names: list[str], profiles: Mapping[str, Any] | None = None
) -> None:
    """Fail when any name is absent from the profile registry."""
    known = _PROFILES if profiles is None else profiles
    unknown = sorted(set(names) - set(known))
    assert not unknown, (
        f"documented profile(s) {unknown} are not in _PROFILES ({', '.join(known)})"
    )


def _load_benchmark_module() -> Any:
    """Import ``scripts/benchmark_profiles.py`` without running its CLI."""
    spec = importlib.util.spec_from_file_location(
        "_profile_docs_benchmark_profiles", BENCHMARK_SCRIPT
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


benchmark = _load_benchmark_module()


# ---------------------------------------------------------------------------
# .env.example
# ---------------------------------------------------------------------------


def test_env_example_documents_only_known_profiles():
    names, _ = _parse_env_example(ENV_EXAMPLE)
    assert names, ".env.example documents no profile names"
    _assert_known_profiles(names, _PROFILES)


def test_env_example_documents_every_profile():
    names, _ = _parse_env_example(ENV_EXAMPLE)
    assert set(names) == set(_PROFILES)


def test_env_example_default_matches_code_default():
    _, configured = _parse_env_example(ENV_EXAMPLE)
    assert configured == DEFAULT_PROFILE


def test_validation_rejects_a_profile_removed_from_the_registry():
    """The guard fails when a documented name no longer exists in `_PROFILES`.

    Simulates the regression: a name stays in `.env.example` after being
    deleted from the registry (a reduced copy is used so other tests keep the
    real registry intact).
    """
    names, _ = _parse_env_example(ENV_EXAMPLE)
    assert "full-tq" in names
    reduced = dict(_PROFILES)
    del reduced["full-tq"]
    with pytest.raises(AssertionError, match="full-tq"):
        _assert_known_profiles(names, reduced)


# ---------------------------------------------------------------------------
# benchmark CLI
# ---------------------------------------------------------------------------


def test_benchmark_cli_names_are_known_profiles():
    assert benchmark.PROFILE_NAMES
    _assert_known_profiles(list(benchmark.PROFILE_NAMES), _PROFILES)


def test_benchmark_cli_default_profiles_are_known():
    args = benchmark._build_parser().parse_args([])
    assert args.profiles, "a bare run must benchmark at least one profile"
    _assert_known_profiles(list(args.profiles), _PROFILES)
    assert args.profile is None


def test_benchmark_cli_rejects_ghost_profiles():
    parser = benchmark._build_parser()
    for ghost in ("local", "pro", "sandbox"):
        with pytest.raises(SystemExit):
            parser.parse_args(["--profiles", ghost])
        with pytest.raises(SystemExit):
            parser.parse_args(["--profile", ghost])


def test_benchmark_help_lists_the_four_real_profiles():
    help_text = benchmark._build_parser().format_help()
    for name in _PROFILES:
        assert name in help_text


# ---------------------------------------------------------------------------
# committed baselines
# ---------------------------------------------------------------------------


def test_baselines_reference_only_known_profiles():
    files = sorted(BASELINES_DIR.glob("*.json"))
    assert files, f"no baseline artifacts under {BASELINES_DIR}"
    for path in files:
        data = json.loads(path.read_text(encoding="utf-8"))
        runs = data["runs"]
        assert runs, f"{path.name} contains no runs"
        profiles = {run["profile"] for run in runs}
        unknown = sorted(profiles - set(_PROFILES))
        assert not unknown, f"{path.name} names unknown profile(s): {unknown}"


def test_baselines_have_no_backup_or_stray_files():
    backup_files = sorted(path.name for path in BASELINES_DIR.rglob("*.bak"))
    assert not backup_files, f"tracked backup file(s): {backup_files}"
    stray = sorted(
        path.name for path in BASELINES_DIR.iterdir() if path.suffix != ".json"
    )
    assert not stray, f"unexpected file(s) in {BASELINES_DIR}: {stray}"
