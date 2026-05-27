import os
from pathlib import Path
from typing import Literal, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class PleskSettings(BaseSettings):
    """
    Configuration settings for mcp-plesk-dev-docs.

    Fields map to environment variables (e.g., log_level maps to LOG_LEVEL).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Logging
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_file: Optional[str] = None
    log_handler: Literal["os", "file", "both"] = "os"

    # Model Profile & Overrides
    plesk_model_profile: str = "full-tq"
    plesk_embed_model: Optional[str] = None
    plesk_reranker_model: Optional[str] = None
    plesk_reranker_enabled: Optional[bool] = None
    plesk_embed_dim: Optional[int] = None

    # Operational Behaviors
    plesk_daemon_auto_warmup: bool = False
    plesk_auto_refresh_on_startup: bool = False
    plesk_index_summaries: bool = False
    plesk_enable_fts: bool = True
    plesk_enable_ast_chunking: bool = False
    plesk_enable_sampling: bool = False
    # Default number of candidates to send to the reranker when not overridden.
    # Historically this default was 50; keep that default for backward compatibility.
    plesk_rerank_candidates: Optional[int] = 50
    plesk_min_relevance_threshold: Optional[float] = None

    # External APIs & Hardware
    openrouter_api_key: str = ""
    force_device: Optional[str] = None
    plesk_html_llm_table_normalize: bool = False

    # Third-party library silencing
    tqdm_disable: bool = True
    transformers_verbosity: str = "error"

    @property
    def effective_log_file(self) -> str:
        """Resolve the log file path, ensuring the parent directory exists."""
        if self.log_file:
            return self.log_file
        base_dir = Path(__file__).parent.parent
        log_dir = base_dir / "storage" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        return str(log_dir / "mcp_plesk_dev_docs.log")

    @property
    def embedding_model_dimensions(self) -> int:
        """Return embedding vector dimension: explicit override or profile default.

        Priority: `plesk_embed_dim` (explicit env override) -> profile default.
        Lazy-imports model_config to avoid expensive imports at module load time.
        """
        if self.plesk_embed_dim:
            return self.plesk_embed_dim
        # Lazy import so we don't cause circular imports at module import time.
        from mcp_plesk_dev_docs.application.services.profile_service import (
            get_active_profile,
        )

        return get_active_profile().embed_dim


# Allow tests to suppress .env loading by setting PLESK_ENV_FILE="" or to another file.
_env_file: str | None = os.environ.get("PLESK_ENV_FILE", ".env")
if not _env_file:
    _env_file = None

# Update the class-level model_config before instantiating the settings singleton.
# We intentionally set `env_file` even when `_env_file` is `None` so tests can
# suppress .env loading by setting `PLESK_ENV_FILE=""` in the environment.
PleskSettings.model_config = SettingsConfigDict(
    env_file=_env_file,
    env_file_encoding="utf-8",
    extra="ignore",
)

settings = PleskSettings()
