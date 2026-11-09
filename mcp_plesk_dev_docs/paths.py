"""Filesystem anchor for the server's data directories.

A source checkout and an installed wheel disagree about where this is. Deriving
the data root from ``__file__`` alone puts ``knowledge_base/`` and ``storage/``
next to the interpreter's site-packages when the package is installed from
PyPI, which means the vector index is destroyed by every venv rebuild or Python
minor-version bump.

``PLESK_BASE_DIR`` overrides it; otherwise the previous behaviour is kept (the
repository root for a checkout, the site-packages directory for a wheel).
"""

import os
from pathlib import Path


def resolve_base_dir() -> Path:
    """Return the directory that holds knowledge_base/ and storage/."""
    override = os.environ.get("PLESK_BASE_DIR")
    if override:
        return Path(override).expanduser().resolve()
    # .../<site-packages or repo>/mcp_plesk_dev_docs/paths.py -> parent dir
    return Path(__file__).parent.parent
