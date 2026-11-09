"""Explicit factory for the default MCP application.

Importing this module is deliberately side-effect free: nothing is constructed
until :func:`create_mcp` is called. That leaves exactly one eager construction
point per process — ``run_server`` for the console script and ``python -m``,
this factory for ``fastmcp run fastmcp.json`` — instead of also building a
container at package import time.
"""

from fastmcp import FastMCP

from mcp_plesk_dev_docs.paths import resolve_base_dir
from mcp_plesk_dev_docs.server.bootstrap import create_app
from mcp_plesk_dev_docs.server.mcp_app import create_mcp_app
from mcp_plesk_dev_docs.settings import settings

__all__ = ["create_mcp"]


def create_mcp() -> FastMCP:
    """Build the default FastMCP server around a fresh application container.

    A no-argument factory is what the ``fastmcp.json`` source accepts: its
    ``entrypoint`` may name a server object or a function that returns one, so
    the manifest can resolve the server without importing a pre-built app.
    """
    return create_mcp_app(create_app(resolve_base_dir(), settings))
