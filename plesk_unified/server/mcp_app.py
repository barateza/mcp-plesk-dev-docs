from typing import Any
from fastmcp import FastMCP
from plesk_unified.server.mcp_app import register_tools


def create_mcp_app(app: Any) -> FastMCP:
    mcp = FastMCP("mcp-plesk-unified")
    register_tools(mcp, app)
    # register_prompts(mcp)  # Task: extract prompts
    # register_resources(mcp, app)  # Task: extract resources
    return mcp
