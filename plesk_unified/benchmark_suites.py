from __future__ import annotations

import json
from pathlib import Path

SUITES_DIR = Path(__file__).parent.parent / "benchmarks" / "suites"


def load_suite(name: str) -> list[dict]:
    """Load a benchmark suite from its corresponding JSON file."""
    path = SUITES_DIR / f"{name}.json"
    if not path.exists():
        # Fallback to an empty list if suite not found, or raise error if mandatory
        return []
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


# Load built-in suites from JSON definitions
BUILTIN_QUERIES = load_suite("control")
STRUCTURAL_QUERIES = load_suite("structural")
LONG_DOC_QUERIES = load_suite("long-doc")
MULTI_HOP_QUERIES = load_suite("multi-hop")

BENCHMARK_SUITES: dict[str, list[dict]] = {
    "control": BUILTIN_QUERIES,
    "structural": STRUCTURAL_QUERIES,
    "long-doc": LONG_DOC_QUERIES,
    "multi-hop": MULTI_HOP_QUERIES,
}
