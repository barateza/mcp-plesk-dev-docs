import asyncio
import logging
from typing import Any, Dict
from fastmcp import Context
from plesk_unified.error_handling import tool_error_boundary
from plesk_unified.types import CategoryOrAll, CategoryEnum, validate_category

logger = logging.getLogger("plesk_unified")


class IndexingTools:
    """
    Logic for indexing-related tools.
    """

    def __init__(self, indexing_service: Any, job_registry: Any):
        self.indexing_service = indexing_service
        self.job_registry = job_registry

    async def refresh_knowledge(
        self,
        ctx: Context,
        category: CategoryOrAll = "all",
        reset_db: bool = False,
    ) -> str:
        """Index Plesk documentation (blocking)."""
        cat_str = category.value if isinstance(category, CategoryEnum) else category
        validate_category(cat_str, allow_all=True)
        return await self.indexing_service.refresh_knowledge(ctx, cat_str, reset_db)

    async def trigger_index_sync(
        self,
        ctx: Context,
        category: CategoryOrAll = "all",
        reset_db: bool = False,
    ) -> Dict[str, str]:
        """Trigger async re-indexing of Plesk documentation."""
        cat_str = category.value if isinstance(category, CategoryEnum) else category
        validate_category(cat_str, allow_all=True)

        def job_wrapper(cat: CategoryOrAll, reset: bool) -> str:
            # Run the async refresh in a new event loop within the background thread
            cat_str = cat.value if isinstance(cat, CategoryEnum) else cat
            res = asyncio.run(
                self.indexing_service.refresh_knowledge(None, cat_str, reset)
            )
            if isinstance(res, str) and res.startswith("[ERROR]"):
                raise RuntimeError(res)
            return res

        job_id = self.job_registry.submit_job(job_wrapper, category, reset_db)
        return {"job_id": job_id, "status": "queued"}

    async def check_sync_status(self, job_id: str) -> Dict[str, Any]:
        """Check the status of a background indexing job."""
        return self.job_registry.get_status(job_id)

    async def requantize_knowledge(self) -> str:
        """Rebuild the TurboQuant index from stored vectors."""
        return await self.indexing_service._rebuild_indices(None)


@tool_error_boundary
async def refresh_knowledge(
    ctx: Context,
    category: CategoryOrAll = "all",
    reset_db: bool = False,
) -> str:
    """
    Index Plesk documentation into LanceDB.

    This tool provides a blocking refresh that returns a report of the
    indexing operation. For very large documentation sets, use
    `trigger_index_sync` instead.
    """
    container = ctx.request_context.lifespan_context["container"]
    tools = IndexingTools(container.indexing_service, container.job_service)
    return await tools.refresh_knowledge(ctx, category, reset_db)


@tool_error_boundary
async def trigger_index_sync(
    ctx: Context,
    category: CategoryOrAll = "all",
    reset_db: bool = False,
) -> Dict[str, str]:
    """Trigger async re-indexing of Plesk documentation. Returns job_id immediately."""
    container = ctx.request_context.lifespan_context["container"]
    tools = IndexingTools(container.indexing_service, container.job_service)
    return await tools.trigger_index_sync(ctx, category, reset_db)


@tool_error_boundary
async def check_sync_status(ctx: Context, job_id: str) -> Dict[str, Any]:
    """Check the status of a background indexing job."""
    container = ctx.request_context.lifespan_context["container"]
    tools = IndexingTools(container.indexing_service, container.job_service)
    return await tools.check_sync_status(job_id)


@tool_error_boundary
async def requantize_knowledge(ctx: Context) -> str:
    """
    Rebuild the TurboQuant index from already-stored LanceDB vectors.
    """
    container = ctx.request_context.lifespan_context["container"]
    tools = IndexingTools(container.indexing_service, container.job_service)
    return await tools.requantize_knowledge()
