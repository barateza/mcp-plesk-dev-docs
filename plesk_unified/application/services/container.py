import logging
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from plesk_unified.settings import PleskSettings as Settings
from plesk_unified.config.sources import SourceCatalog
from plesk_unified.infrastructure.runtime.model_runtime import ModelRuntime
from plesk_unified.infrastructure.runtime.storage_runtime import StorageRuntime
from plesk_unified.application.services.warmup_service import WarmupService
from plesk_unified.application.services.health_service import HealthService
from plesk_unified.formatting.search_formatter import SearchFormatter
from plesk_unified.formatting.toc_formatter import TocFormatter
from plesk_unified.infrastructure.repositories.lancedb_repository import (
    LanceDbRepository,
)
from plesk_unified.infrastructure.repositories.turboquant_repository import (
    TurboQuantRepository,
)
from plesk_unified.infrastructure.repositories.source_state_repository import (
    SourceStateRepository,
)
from plesk_unified.infrastructure.repositories.summary_cache_repository import (
    SummaryCacheRepository,
)
from plesk_unified.application.services.search_service import SearchService
from plesk_unified.application.services.indexing_service import IndexingService
from plesk_unified.infrastructure.parsers.processor_registry import ProcessorRegistry


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
