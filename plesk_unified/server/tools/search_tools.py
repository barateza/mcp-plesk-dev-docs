import logging
from typing import Optional
from fastmcp import Context
from plesk_unified.types import CategoryEnum, validate_category
from plesk_unified.error_handling import tool_error_boundary

logger = logging.getLogger("plesk_unified")


class SearchTools:
    """
    Wrapper for search-related tools.
    """

    def __init__(self, search_service):
        self.search_service = search_service

    async def search_plesk_unified(
        self, ctx: Context, query: str, category: Optional[CategoryEnum] = None
    ) -> str:
        """
        Search the unified Plesk documentation for a specific query.

        This tool provides access to the most up-to-date documentation for Plesk,
        including guides, CLI references, and API documentation.
        Use this for any questions about how Plesk works, how to use its CLI or APIs.
        """
        # Ensure it calls self.search_service.search(ctx, query, category)
        # SearchService.search expects category as Optional[str]
        cat_str = category.value if isinstance(category, CategoryEnum) else category
        if cat_str:
            validate_category(cat_str, allow_all=False)
        return await self.search_service.search(ctx, query, cat_str)


@tool_error_boundary
async def search_plesk_unified(
    ctx: Context,
    query: str,
    category: Optional[CategoryEnum] = None,
) -> str:
    """
    Search the unified Plesk documentation for a specific query.

    This tool provides access to the most up-to-date documentation for Plesk,
    including guides, CLI references, and API documentation.
    Use this for any questions about how Plesk works, how to use its CLI or APIs.
    """
    container = ctx.request_context.lifespan_context["container"]
    search_tools = SearchTools(container.search_service)
    return await search_tools.search_plesk_unified(ctx, query, category)
