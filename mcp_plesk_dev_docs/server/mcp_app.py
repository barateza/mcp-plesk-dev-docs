from contextlib import AbstractAsyncContextManager, asynccontextmanager
from mcp_plesk_dev_docs.paths import resolve_base_dir
from typing import AsyncGenerator, Callable

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from mcp_plesk_dev_docs.application.services.container import AppContainer

# Root directory of the project
BASE_DIR = resolve_base_dir()


def container_lifespan(
    container: AppContainer,
) -> Callable[[FastMCP], AbstractAsyncContextManager[dict]]:
    """Return the lifespan that exposes and later releases *container*.

    The lifespan must be passed to the constructor, not registered with the
    ``@mcp.lifespan()`` decorator: that form silently registers nothing (on
    fastmcp 3.4 and 4.1 alike), so ``lifespan_context`` stayed empty and EVERY
    tool died with ``KeyError: 'container'``.
    """

    @asynccontextmanager
    async def lifespan(mcp_instance: FastMCP) -> AsyncGenerator[dict, None]:
        # Yield the container for access via ctx.request_context.lifespan_context
        yield {"container": container}

        # Release every pool the container owns: the shared and ingest
        # executors plus the retrieval pool, which are created lazily on
        # first use. Shutting down only the shared executor used to leak the
        # other two.
        container.shutdown()

    return lifespan


def create_mcp_app(container: AppContainer) -> FastMCP:
    """Create and configure the FastMCP application."""
    mcp = FastMCP("mcp-plesk-dev-docs", lifespan=container_lifespan(container))

    # Register tools
    from mcp_plesk_dev_docs.server.tools.search_tools import (
        SEARCH_OUTPUT_SCHEMA,
        search_mcp_plesk_dev_docs,
        get_file_content,
        resolve_references,
    )
    from mcp_plesk_dev_docs.server.tools.admin_tools import (
        warmup_server,
        daemon_health,
        list_model_profiles,
    )
    from mcp_plesk_dev_docs.server.tools.indexing_tools import (
        refresh_knowledge,
        trigger_index_sync,
        check_sync_status,
        requantize_knowledge,
    )

    # Search results are read-only and idempotent, so clients may cache and
    # parallelise the call; they also carry `structuredContent`.
    mcp.tool(
        annotations=ToolAnnotations(read_only_hint=True, idempotent_hint=True),
        output_schema=SEARCH_OUTPUT_SCHEMA,
    )(search_mcp_plesk_dev_docs)
    mcp.tool()(get_file_content)
    mcp.tool()(resolve_references)
    mcp.tool()(warmup_server)
    mcp.tool()(daemon_health)
    mcp.tool()(list_model_profiles)
    mcp.tool()(refresh_knowledge)
    mcp.tool()(trigger_index_sync)
    mcp.tool()(check_sync_status)
    mcp.tool()(requantize_knowledge)

    # Register prompts
    from mcp_plesk_dev_docs.server.prompts.prompt_templates import register_prompts

    register_prompts(mcp)

    # Register resources
    from mcp_plesk_dev_docs.server.resources.toc_resource import get_toc_resource

    mcp.resource("plesk://toc/{category}")(get_toc_resource)

    return mcp
