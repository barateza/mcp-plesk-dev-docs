from fastmcp import Context
from plesk_unified.error_handling import tool_error_boundary


@tool_error_boundary
async def get_toc_resource(category: str, ctx: Context) -> str:
    """
    Get the Table of Contents for a specific Plesk documentation category.
    """
    container = ctx.request_context.lifespan_context["container"]
    # Use TocFormatter from the container to return the TOC as a JSON string
    return container.toc_formatter.to_json(category)
