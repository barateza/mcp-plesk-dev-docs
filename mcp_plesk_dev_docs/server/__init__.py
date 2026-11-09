"""Server package.

Importing this package must stay side-effect free: the application container is
built on first access to :data:`mcp`, or eagerly by
:func:`mcp_plesk_dev_docs.server.main.run_server` when actually serving. Building
it here used to create a second container (and leak its thread pool) on top of
the one ``run_server`` builds.
"""

from typing import TYPE_CHECKING, Any, Optional

from mcp_plesk_dev_docs.server.main import run_server as main

if TYPE_CHECKING:
    from fastmcp import FastMCP

__all__ = ["mcp", "main"]

_mcp: Optional["FastMCP"] = None


def __getattr__(name: str) -> Any:
    """Resolve ``mcp`` on first access, so importing the package builds nothing."""
    global _mcp
    if name == "mcp":
        if _mcp is None:
            from mcp_plesk_dev_docs.server.app import create_mcp

            _mcp = create_mcp()
        return _mcp
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
