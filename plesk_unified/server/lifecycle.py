import asyncio
import logging
import time
from plesk_unified.settings import settings

logger = logging.getLogger("plesk_unified")


def log_server_ready(start_time: float) -> None:
    """Log that the server is ready and the initialization time."""
    logger.info("Starting Plesk Unified MCP Server...")
    logger.info("Server module initialized in %.2fs.", time.perf_counter() - start_time)


def maybe_refresh_changed_sources() -> None:
    """At startup, refresh only categories whose source fingerprint changed."""
    if not settings.plesk_auto_refresh_on_startup:
        logger.info("Startup source refresh disabled by env var.")
        return

    from plesk_unified.legacy_server import refresh_knowledge

    try:
        logger.info("Running startup source change detection.")
        try:
            asyncio.get_running_loop()
            asyncio.create_task(
                refresh_knowledge(None, target_category="all", reset_db=False)
            )
        except RuntimeError:
            report = asyncio.run(
                refresh_knowledge(None, target_category="all", reset_db=False)
            )
            logger.info("Startup source refresh report:\n%s", report)
    except Exception:
        logger.exception("Startup source refresh failed.")


def maybe_start_background_warmup() -> None:
    """Start background warmup if enabled."""
    from plesk_unified.legacy_server import _maybe_start_background_warmup

    _maybe_start_background_warmup()
