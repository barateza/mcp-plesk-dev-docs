import logging
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from mcp_plesk_dev_docs.settings import PleskSettings as Settings
from mcp_plesk_dev_docs.config.sources import SourceCatalog
from mcp_plesk_dev_docs.infrastructure.runtime.model_runtime import ModelRuntime
from mcp_plesk_dev_docs.infrastructure.runtime.storage_runtime import StorageRuntime
from mcp_plesk_dev_docs.application.services.warmup_service import WarmupService
from mcp_plesk_dev_docs.application.services.health_service import HealthService
from mcp_plesk_dev_docs.formatting.search_formatter import SearchFormatter
from mcp_plesk_dev_docs.formatting.toc_formatter import TocFormatter
from mcp_plesk_dev_docs.infrastructure.repositories.lancedb_repository import (
    LanceDbRepository,
)
from mcp_plesk_dev_docs.infrastructure.repositories.turboquant_repository import (
    TurboQuantRepository,
)
from mcp_plesk_dev_docs.infrastructure.repositories.source_state_repository import (
    SourceStateRepository,
)
from mcp_plesk_dev_docs.infrastructure.repositories.summary_cache_repository import (
    SummaryCacheRepository,
)
from mcp_plesk_dev_docs.application.services.search_service import SearchService
from mcp_plesk_dev_docs.application.services.indexing_service import IndexingService
from mcp_plesk_dev_docs.infrastructure.parsers.processor_registry import (
    ProcessorRegistry,
)


@dataclass
class AppContainer:
    settings: Settings
    logger: logging.Logger
    executor: ThreadPoolExecutor
    sources: SourceCatalog
    model_runtime: ModelRuntime
    storage_runtime: StorageRuntime
    warmup_service: WarmupService
    health_service: HealthService
    search_formatter: SearchFormatter
    toc_formatter: TocFormatter
    lancedb_repo: LanceDbRepository
    turboquant_repo: TurboQuantRepository
    source_state_repo: SourceStateRepository
    summary_cache_repo: SummaryCacheRepository
    search_service: SearchService
    indexing_service: IndexingService
    processor_registry: ProcessorRegistry

    # These will be added as we extract more services
    job_service: Any = None

    def shutdown(self):
        """Shut down the executor and other resources."""
        self.logger.info("Shutting down AppContainer...")
        self.executor.shutdown(wait=True)
        # Clear model caches if possible
        if hasattr(self.model_runtime, "_embedding_model"):
            self.model_runtime._embedding_model = None
        if hasattr(self.model_runtime, "_reranker"):
            self.model_runtime._reranker = None
