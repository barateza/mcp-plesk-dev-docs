"""Source acquisition — clone, download, extract, and validate documentation sources."""

import logging
import os
import re
import shutil
import stat
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Dict
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sphinx documentation infrastructure files bundled in documentation zips.
# These are search-UI assets with no Plesk-specific content; indexing them
# pollutes retrieval results and displaces real documentation.
# ---------------------------------------------------------------------------

_SKIP_FILES: frozenset[str] = frozenset(
    {
        "doctools.js",
        "searchtools.js",
        "websupport.js",
        "jquery.js",
        "jquery-3.2.1.js",
        "underscore.js",
        "underscore-1.3.1.js",
        "documentation_options.js",
        "language_data.js",
        "basic.js",
        "_sphinx_javascript_frameworks_compat.js",
    }
)

# Documentation pages that are boilerplate or redundant summaries (api-rpc specific).
_API_RPC_SKIP_FILES: frozenset[str] = frozenset(
    {
        "45121.htm",  # Before Using The Reference
        "45023.htm",  # Data Types
        "28784.htm",  # Reference
        "36543.htm",  # Uploading Files Using .NET
    }
)

# Documentation pages that are boilerplate or redundant summaries
# (extensions-guide specific).
_GUIDE_SKIP_FILES: frozenset[str] = frozenset(
    {
        "73625.htm",
        "76104.htm",
        "76105.htm",
        "76343.htm",
        "76103.htm",
    }
)

# Internal build scripts, test utilities, and configuration irrelevant to
# SDK API Reference
_JS_SDK_SKIP_DIRS: frozenset[str] = frozenset(
    {
        "test",
        "__tests__",
        "bin",
        "lib",
    }
)

_JS_SDK_SKIP_FILES: frozenset[str] = frozenset(
    {
        "CNAGELOG.md",
    }
)


def _on_rm_error(func, path, _exc_info):
    """Helper for shutil.rmtree to handle read-only files."""
    os.chmod(path, stat.S_IWRITE)
    func(path)


_GIT_PATH: str | None = None


def _get_git_path() -> str:
    """Return the absolute path to the git executable, cached."""
    global _GIT_PATH
    if _GIT_PATH is None:
        resolved = shutil.which("git")
        if resolved is None:
            raise RuntimeError("git executable not found on PATH. Install git.")
        _GIT_PATH = resolved
    return _GIT_PATH


_SAFE_GIT_RE = re.compile(r"^https://([\w-]+\.)+[\w-]+(:\d+)?/[\w\-._~/]+(\.git)?$")


def _validate_repo_url(url: str) -> None:
    """Validate that a repo URL is a safe HTTPS URL matching expected patterns."""
    if not url or not isinstance(url, str):
        raise ValueError(f"Invalid repo_url type: {type(url).__name__}")
    if not _SAFE_GIT_RE.match(url):
        raise ValueError(f"repo_url rejected by safety check: {url[:80]}")


def _validate_zip_url(zip_url: str) -> None:
    """Validate that a zip URL uses the HTTPS scheme."""
    if not zip_url or not isinstance(zip_url, str):
        raise ValueError(f"Invalid zip_url type: {type(zip_url).__name__}")
    if urlparse(zip_url).scheme != "https":
        raise ValueError("zip_url scheme not allowed — only https:// accepted")


def _extract_zip_with_strip(zip_ref: zipfile.ZipFile, source_path: Path) -> None:
    """Extract zip content, automatically stripping a single top-level directory."""
    with tempfile.TemporaryDirectory() as temp_dir_str:
        temp_dir = Path(temp_dir_str)
        zip_ref.extractall(temp_dir)

        # Check if zip contains only one top-level directory
        items = list(temp_dir.iterdir())
        if len(items) == 1 and items[0].is_dir():
            # Extract contents of the top-level directory directly into source_path
            for item in items[0].iterdir():
                shutil.move(str(item), str(source_path / item.name))
            logger.info("Stripped top-level directory '%s' from zip", items[0].name)
        else:
            # Move all items to source_path
            for item in items:
                shutil.move(str(item), str(source_path / item.name))


def ensure_source_exists(source: Dict[str, Any]) -> bool:
    """Ensure the source repository exists and is not empty."""
    source_path = source.get("path")

    if (
        source_path
        and isinstance(source_path, Path)
        and source_path.exists()
        and any(source_path.iterdir())
    ):
        logger.debug("Source %s already exists", source.get("cat"))
        return True

    repo_url = source.get("repo_url")
    zip_url = source.get("zip_url")

    # If repo_url is present, clone from Git via subprocess.
    if repo_url and source_path:
        _validate_repo_url(repo_url)
        # Only used after URL validation above
        import subprocess  # nosec

        git_path = _get_git_path()
        logger.info("Cloning %s with %s", repo_url, git_path)
        try:
            # repo_url validated by _validate_repo_url above
            result = subprocess.run(  # nosec
                [git_path, "clone", "--", repo_url, str(source_path)],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                raise RuntimeError(result.stderr)
            # Cleanup unnecessary artifacts
            for folder in [".git", ".github", "tests"]:
                target = source_path / folder
                if target.exists() and target.is_dir():
                    shutil.rmtree(target, onerror=_on_rm_error)
            return True
        except Exception:
            logger.error("Clone failed for %s", source.get("cat"), exc_info=True)
            return False

    # If zip_url is present, download and extract the Zip file.
    if zip_url and source_path:
        _validate_zip_url(zip_url)
        # Only used after URL validation above
        import urllib.request  # nosec

        logger.info("Downloading zip %s from %s...", source.get("cat"), zip_url)
        try:
            source_path.mkdir(parents=True, exist_ok=True)
            # zip_url validated by _validate_zip_url above
            response = urllib.request.urlopen(  # nosec
                zip_url, timeout=30
            )
            data = response.read()
            logger.info("Downloaded %s (%.1f MB)", zip_url, len(data) / (1024 * 1024))
            with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp:
                tmp.write(data)
            try:
                with zipfile.ZipFile(tmp.name, "r") as zip_ref:
                    _extract_zip_with_strip(zip_ref, source_path)
                return True
            finally:
                if os.path.exists(tmp.name):
                    os.unlink(tmp.name)
        except Exception:
            logger.error("Zip failed for %s", source.get("cat"), exc_info=True)
            return False

    return False
