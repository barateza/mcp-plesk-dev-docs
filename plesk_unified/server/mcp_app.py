from typing import Any
from fastmcp import FastMCP


def create_mcp_app(app: Any) -> FastMCP:
    mcp = FastMCP("mcp-plesk-unified")
    # Task: register tools, prompts, resources
    # register_tools(mcp, app)
    # register_prompts(mcp)
    # register_resources(mcp, app)
    return mcp
