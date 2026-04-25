import asyncio
from typing import Any, Dict


class IndexingTools:
    def __init__(self, indexing_service: Any, job_registry: Any):
        self.indexing_service = indexing_service
        self.job_registry = job_registry

    async def trigger_index_sync(
        self,
        ctx: Any,
        category: str = "all",
        reset_db: bool = False,
    ) -> Dict[str, str]:
        """Trigger async re-indexing of Plesk documentation."""

        def job_wrapper(cat: str, reset: bool) -> str:
            res = asyncio.run(self.indexing_service.refresh_knowledge(None, cat, reset))
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
