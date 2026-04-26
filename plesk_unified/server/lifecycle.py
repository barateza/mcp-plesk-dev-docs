import asyncio
import logging
import time

from plesk_unified.application.services.container import AppContainer

logger = logging.getLogger("plesk_unified")


def log_server_ready(start_time: float) -> None:
    """Log that the server is ready and the initialization time."""
    logger.info("Starting Plesk Unified MCP Server...")
    logger.info("Server module initialized in %.2fs.", time.perf_counter() - start_time)


def maybe_refresh_changed_sources(container: AppContainer) -> None:
    """At startup, refresh only categories whose source fingerprint changed."""
    if not container.settings.plesk_auto_refresh_on_startup:
        logger.info("Startup source refresh disabled by env var.")
        return

    try:
        logger.info("Running startup source change detection.")
        try:
            asyncio.get_running_loop()
            asyncio.create_task(
                container.indexing_service.refresh_knowledge(
                    progress_callback=None, category="all", reset_db=False
                )
            )
        except RuntimeError:
            report = asyncio.run(
                container.indexing_service.refresh_knowledge(
                    progress_callback=None, category="all", reset_db=False
                )
            )
            logger.info("Startup source refresh report:\n%s", report)
    except Exception:
        logger.exception("Startup source refresh failed.")


def maybe_start_background_warmup(container: AppContainer) -> None:
    """Start background warmup if enabled."""
    container.warmup_service.maybe_start_background_warmup()
