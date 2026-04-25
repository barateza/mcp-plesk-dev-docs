from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from fastmcp import FastMCP
from plesk_unified.application.services.container import AppContainer

# Root directory of the project
BASE_DIR = Path(__file__).parent.parent.parent


def create_mcp_app(container: AppContainer) -> FastMCP:
    """Create and configure the FastMCP application."""
    mcp = FastMCP("mcp-plesk-unified")

    @mcp.lifespan()
    @asynccontextmanager
    async def lifespan(mcp_instance: FastMCP) -> AsyncGenerator[dict, None]:
        # Yield the container for access via ctx.request_context.lifespan_context
        yield {"container": container}

        # Cleanup
        container.executor.shutdown(wait=False)

    # Register tools
    from plesk_unified.server.tools.search_tools import search_plesk_unified
    from plesk_unified.server.tools.admin_tools import (
        warmup_server,
        daemon_health,
        list_model_profiles,
    )
    from plesk_unified.server.tools.indexing_tools import (
        refresh_knowledge,
        trigger_index_sync,
        check_sync_status,
        requantize_knowledge,
    )

    mcp.tool()(search_plesk_unified)
    mcp.tool()(warmup_server)
    mcp.tool()(daemon_health)
    mcp.tool()(list_model_profiles)
    mcp.tool()(refresh_knowledge)
    mcp.tool()(trigger_index_sync)
    mcp.tool()(check_sync_status)
    mcp.tool()(requantize_knowledge)

    # Register prompts
    from plesk_unified.server.prompts.prompt_templates import register_prompts

    register_prompts(mcp)

    # Register resources
    from plesk_unified.server.resources.toc_resource import get_toc_resource

    mcp.resource("plesk://toc/{category}")(get_toc_resource)

    return mcp
