import logging
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from plesk_unified.log_handler import create_os_handlers


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
