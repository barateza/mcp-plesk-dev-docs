#!/usr/bin/env python3
"""Build or refresh the LanceDB index the quality gate benchmarks against.

A fresh checkout ships neither ``knowledge_base/`` (the corpus) nor ``storage/``
(the index); both are gitignored. Without an index the gate cannot run, and
building one by hand means knowing the profile, the cache locations and the
refresh API. This script is that one command:

    uv run python scripts/bootstrap_index.py --profile light

Model weights are cached inside the workspace (``.cache/hf``) because
``~/.cache/huggingface`` is not writable in a sandboxed session.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
# Must be set before sentence-transformers / transformers import.
os.environ.setdefault("HF_HOME", str(REPO_ROOT / ".cache" / "hf"))

from mcp_plesk_dev_docs.paths import resolve_base_dir  # noqa: E402
from mcp_plesk_dev_docs.server.bootstrap import create_app  # noqa: E402
from mcp_plesk_dev_docs.settings import PleskSettings  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile",
        default=os.environ.get("PLESK_MODEL_PROFILE", "light"),
        help="Model profile to index for (default: light).",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Drop the table before indexing (full re-embed).",
    )
    parser.add_argument(
        "--category",
        default="all",
        help="Category to index (default: all).",
    )
    args = parser.parse_args(argv)

    os.environ["PLESK_MODEL_PROFILE"] = args.profile
    settings = PleskSettings(_env_file=None, plesk_model_profile=args.profile)

    started = time.time()
    app = create_app(resolve_base_dir(), settings)
    print(f"Indexing profile '{args.profile}' (reset={args.reset})...")
    report = asyncio.run(
        app.indexing_service.refresh_knowledge(
            category=args.category, reset_db=args.reset
        )
    )
    print(report)

    table = app.storage_runtime.get_table(create_new=False)
    print(f"rows={table.count_rows()} version={table.version}")
    for index in table.list_indices():
        print(f"index: {index.index_type} on {list(index.columns)}")
    print(f"elapsed {time.time() - started:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
