"""Source discovery — TOC parsing, file collection, and fingerprinting."""

import hashlib
import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp_plesk_dev_docs.infrastructure.sources.acquisition import (
    _API_RPC_SKIP_FILES,
    _GUIDE_SKIP_FILES,
    _JS_SDK_SKIP_DIRS,
    _JS_SDK_SKIP_FILES,
    _SKIP_FILES,
)

logger = logging.getLogger(__name__)


def parse_toc_recursive(
    nodes: List[Dict[str, Any]],
    parent_path: str = "",
    file_map: Optional[Dict[str, Dict[str, str]]] = None,
) -> Dict[str, Dict[str, str]]:
    """Recursively parse TOC nodes to build a file map."""
    if file_map is None:
        file_map = {}
    for node in nodes:
        title = node.get("text", "Untitled")
        url_raw = node.get("url", "")
        current_path = f"{parent_path} > {title}" if parent_path else title
        filename = url_raw.split("#")[0]
        if filename and filename not in file_map:
            file_map[filename] = {"title": title, "breadcrumb": current_path}
        if "children" in node:
            parse_toc_recursive(node["children"], current_path, file_map)
    return file_map


@lru_cache(maxsize=64)
def load_toc_map(folder_path: Path) -> Dict[str, Dict[str, str]]:
    """Load and parse a TOC map from a folder's toc.json file.

    Searches ``folder_path / toc.json`` first, then falls back to the first
    ``toc.json`` found anywhere under ``folder_path`` (handles zip-extracted
    sources that unpack into a nested subdirectory).
    """
    toc_path = folder_path / "toc.json"
    if not toc_path.exists():
        candidates = list(folder_path.rglob("toc.json"))
        if not candidates:
            return {}
        toc_path = candidates[0]
    try:
        data = json.loads(toc_path.read_text(encoding="utf-8"))
        # handle case where toc structure might have a top level "files" array
        # vs direct nested nodes
        # The TOC JSON may be either a list of nodes or a dict with a
        # top-level "files" list. Normalize to a `List[Dict[str, Any]]`
        # before calling `parse_toc_recursive` so the type matches what
        # the parser expects (and to satisfy type checkers like Pylance).
        if (
            isinstance(data, dict)
            and "files" in data
            and isinstance(data["files"], list)
        ):
            nodes = data["files"]
        elif isinstance(data, list):
            nodes = data
        else:
            return {}

        return parse_toc_recursive(nodes)
    except Exception:
        logger.warning("Failed to parse TOC at %s", toc_path, exc_info=True)
        return {}


def collect_files_for_source(source: Dict[str, Any]) -> List[Path]:
    """Collects files for a source depending on its type."""
    source_path = source.get("path")
    if not source_path or not isinstance(source_path, Path):
        return []

    stype = source.get("type")

    if stype == "html":
        files = list(source_path.rglob("*.htm")) + list(source_path.rglob("*.html"))
    elif stype == "php":
        files = list(source_path.rglob("*.php"))
    else:
        files = list(source_path.rglob("*.js")) + list(source_path.rglob("*.md"))

    skip_set = _SKIP_FILES
    if source.get("cat") == "api":
        skip_set = skip_set.union(_API_RPC_SKIP_FILES)
    elif source.get("cat") == "guide":
        skip_set = skip_set.union(_GUIDE_SKIP_FILES)

    # Base filtering
    filtered_files = [f for f in files if f.name not in skip_set]

    # Additional filtering for js-sdk
    if source.get("cat") == "js-sdk":
        filtered_files = [
            f
            for f in filtered_files
            if f.name not in _JS_SDK_SKIP_FILES
            and not any(part in _JS_SDK_SKIP_DIRS for part in f.parts)
        ]

    return filtered_files


def compute_source_fingerprint(source: Dict[str, Any]) -> tuple[str, int]:
    """Build a stable digest for source content currently present on disk."""
    files = sorted(collect_files_for_source(source), key=lambda p: str(p))
    hasher = hashlib.sha256()

    source_path = source.get("path")
    for f in files:
        try:
            rel = str(f.relative_to(source_path)) if source_path else f.name
            stat_info = f.stat()
            hasher.update(rel.encode("utf-8", errors="ignore"))
            hasher.update(str(stat_info.st_size).encode("ascii", errors="ignore"))
            hasher.update(str(stat_info.st_mtime_ns).encode("ascii", errors="ignore"))
        except Exception:
            logger.debug("Skipping file hash due to transient error: %s", f)
            continue

    toc = None
    if source_path and isinstance(source_path, Path):
        candidate = source_path / "toc.json"
        if candidate.exists():
            toc = candidate

    if toc is not None:
        try:
            toc_stat = toc.stat()
            hasher.update(b"toc.json")
            hasher.update(str(toc_stat.st_size).encode("ascii", errors="ignore"))
            hasher.update(str(toc_stat.st_mtime_ns).encode("ascii", errors="ignore"))
        except Exception:
            logger.debug("Skipping toc.json hash due to transient error")

    return hasher.hexdigest(), len(files)
