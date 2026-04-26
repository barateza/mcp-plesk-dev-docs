import logging
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from plesk_unified.log_handler import create_os_handlers
from plesk_unified.application.services.container import AppContainer
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
from plesk_unified.indexing import JobRegistry


def setup_directories(base_dir: Path):
    """Ensure all required directories exist."""
    (base_dir / "storage" / "logs").mkdir(parents=True, exist_ok=True)
    (base_dir / "knowledge_base").mkdir(parents=True, exist_ok=True)
    (base_dir / "storage").mkdir(parents=True, exist_ok=True)


def configure_logging(settings):
    """
    Initialize and return the root logger for the application.
    Configures OS-native, file, and stream handlers.
    """
    log_file = settings.effective_log_file
    log_level_name = settings.log_level.upper()
    log_level = getattr(logging, log_level_name, logging.INFO)

    logger = logging.getLogger("plesk_unified")
    logger.setLevel(log_level)

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # OS-native / file handler(s)
    os_handlers = create_os_handlers(log_level, formatter, str(log_file))

    # Stream Handler (stderr) - CRITICAL for MCP protocol
    stream_handler = logging.StreamHandler(sys.stderr)
    stream_handler.setFormatter(formatter)
    stream_handler.setLevel(log_level)

    # Avoid adding duplicate handlers
    if not logger.handlers:
        for _h in os_handlers:
            logger.addHandler(_h)
        logger.addHandler(stream_handler)

    # Silence noisy third-party libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("git").setLevel(logging.WARNING)

    return logger


def configure_environment(settings):
    """Configure process-wide environment variables."""
    os.environ["TQDM_DISABLE"] = "1" if settings.tqdm_disable else "0"
    os.environ["TRANSFORMERS_VERBOSITY"] = settings.transformers_verbosity


def create_executor(max_workers: int = 4) -> ThreadPoolExecutor:
    """Create a shared thread pool executor."""
    return ThreadPoolExecutor(max_workers=max_workers)


def create_app(base_dir: Path, settings) -> AppContainer:
    """Composition root: create and wire all application services."""
    setup_directories(base_dir)
    configure_environment(settings)
    logger = configure_logging(settings)
    executor = create_executor()
    sources = SourceCatalog.default(base_dir / "knowledge_base")

    model_runtime = ModelRuntime()
    storage_runtime = StorageRuntime(base_dir, model_runtime)
    warmup_service = WarmupService(settings, model_runtime, storage_runtime)
    health_service = HealthService(
        settings, model_runtime, storage_runtime, warmup_service
    )

    search_formatter = SearchFormatter(sources)
    toc_formatter = TocFormatter(sources)

    lancedb_repo = LanceDbRepository(storage_runtime)
    turboquant_repo = TurboQuantRepository(storage_runtime)
    source_state_repo = SourceStateRepository(
        base_dir / "storage" / "source_state.json"
    )
    summary_cache_repo = SummaryCacheRepository(
        base_dir / "storage" / "summaries_cache.json"
    )

    processor_registry = ProcessorRegistry()

    search_service = SearchService(
        settings=settings,
        model_runtime=model_runtime,
        storage_runtime=storage_runtime,
        lancedb_repo=lancedb_repo,
        turboquant_repo=turboquant_repo,
        search_formatter=search_formatter,
        executor=executor,
    )

    indexing_service = IndexingService(
        settings=settings,
        model_runtime=model_runtime,
        storage_runtime=storage_runtime,
        lancedb_repo=lancedb_repo,
        turboquant_repo=turboquant_repo,
        source_state_repo=source_state_repo,
        summary_cache_repo=summary_cache_repo,
        processor_registry=processor_registry,
        source_catalog=sources,
        executor=executor,
    )

    job_service = JobRegistry()

    return AppContainer(
        settings=settings,
        logger=logger,
        executor=executor,
        sources=sources,
        model_runtime=model_runtime,
        storage_runtime=storage_runtime,
        warmup_service=warmup_service,
        health_service=health_service,
        search_formatter=search_formatter,
        toc_formatter=toc_formatter,
        lancedb_repo=lancedb_repo,
        turboquant_repo=turboquant_repo,
        source_state_repo=source_state_repo,
        summary_cache_repo=summary_cache_repo,
        search_service=search_service,
        indexing_service=indexing_service,
        processor_registry=processor_registry,
        job_service=job_service,
    )
