"""Guards for the ``fastmcp.json`` manifest (issue #97).

The manifest used to point at ``mcp_plesk_dev_docs/server.py``, which vanished
when the server was split into a package, so ``fastmcp run fastmcp.json``
failed before it started. These tests make a future move break CI instead of
only surfacing at deployment time.
"""

import importlib.util
import inspect
import json
from pathlib import Path
from unittest.mock import MagicMock

from fastmcp import FastMCP

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPO_ROOT / "fastmcp.json"


def _source() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))["source"]


def _manifest_module():
    """Import the module the manifest names, without calling the factory."""
    path = (REPO_ROOT / _source()["path"]).resolve()
    spec = importlib.util.spec_from_file_location("fastmcp_manifest_probe", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_manifest_source_path_exists():
    source = _source()
    path = (REPO_ROOT / source["path"]).resolve()
    assert path.is_file(), (
        f"fastmcp.json source.path {source['path']!r} does not exist ({path}); "
        "the server module probably moved"
    )


def test_manifest_entrypoint_is_a_no_arg_factory():
    source = _source()
    module = _manifest_module()
    entrypoint = getattr(module, source["entrypoint"], None)

    assert entrypoint is not None, (
        f"fastmcp.json entrypoint {source['entrypoint']!r} is missing from "
        f"{source['path']!r}"
    )
    assert inspect.isfunction(entrypoint), (
        "entrypoint must be a no-argument factory returning a FastMCP server"
    )
    assert not inspect.signature(entrypoint).parameters, (
        "a FastMCP factory entrypoint must take no arguments"
    )


def test_manifest_factory_returns_a_fastmcp_server(monkeypatch):
    source = _source()
    module = _manifest_module()
    monkeypatch.setattr(module, "create_app", lambda *args, **kwargs: MagicMock())

    server = getattr(module, source["entrypoint"])()

    assert isinstance(server, FastMCP)
