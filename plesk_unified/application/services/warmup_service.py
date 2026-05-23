import logging
import threading
from typing import Any, List, Optional

logger = logging.getLogger("plesk_unified")


class WarmupService:
    def __init__(self, settings: Any, model_runtime: Any, storage_runtime: Any):
        self.settings = settings
        self.model_runtime = model_runtime
        self.storage_runtime = storage_runtime
        self._warmup_state = "idle"
        self._warmup_error: Optional[str] = None
        self._warmup_lock = threading.Lock()
        self._warmup_thread: Optional[threading.Thread] = None

    def begin_warmup(self) -> bool:
        """Attempt to start a warmup operation, returning True if successful."""
        with self._warmup_lock:
            if self._warmup_state == "running":
                return False
            self._warmup_state = "running"
            self._warmup_error = None
            return True

    def finish_warmup(self, error: Optional[Exception] = None) -> None:
        """Mark the warmup operation as finished."""
        with self._warmup_lock:
            if error is None:
                self._warmup_state = "ready"
                self._warmup_error = None
            else:
                self._warmup_state = "failed"
                self._warmup_error = str(error)

    def run_warmup_sequence(self) -> List[str]:
        """Synchronously execute the warmup sequence."""
        profile = self.model_runtime.get_profile()
        logger.info("Starting warmup for profile %s.", profile.name)

        parts = [f"Warmup started for profile '{profile.name}'."]

        self.model_runtime.get_embedding_model()
        parts.append(f"Embedding model ready: {profile.embed_model}.")

        reranker = self.model_runtime.get_reranker()
        if reranker is None:
            parts.append("Reranker not loaded.")
        else:
            parts.append(f"Reranker ready: {profile.reranker_model}.")

        self.storage_runtime.get_table(create_new=False)
        parts.append("LanceDB table ready.")

        # Warm up FTS index to avoid first-query lazy-load spike
        if getattr(self.settings, "plesk_enable_fts", True):
            try:
                table = self.storage_runtime.get_table(create_new=False)
                table.search("warmup").limit(1).to_list()
                parts.append("LanceDB FTS index warmed up.")
            except Exception as e:
                logger.debug("Failed to warm up FTS index: %s", e)

        if getattr(profile, "use_turboquant", False):
            tq_path = self.storage_runtime.get_tq_index_path()
            if tq_path.exists():
                self.storage_runtime.get_tq_index()
                parts.append(f"TurboQuant index loaded from {tq_path.name}.")
            else:
                parts.append(
                    "TurboQuant index not present; skipped build during warmup."
                )

        logger.info("Warmup complete for profile %s.", profile.name)
        return parts

    def _background_warmup_worker(self) -> None:
        """Worker thread entrypoint for background warmup."""
        if not self.begin_warmup():
            logger.info("Background warmup skipped because warmup is already running.")
            return

        try:
            self.run_warmup_sequence()
            self.finish_warmup()
        except Exception as exc:
            self.finish_warmup(exc)
            logger.exception("Background warmup failed.")

    def maybe_start_background_warmup(self) -> None:
        """Start background warmup if enabled in settings."""
        if not self.settings.plesk_daemon_auto_warmup:
            return

        with self._warmup_lock:
            if self._warmup_thread is not None and self._warmup_thread.is_alive():
                return
            self._warmup_thread = threading.Thread(
                target=self._background_warmup_worker,
                name="plesk-daemon-warmup",
                daemon=True,
            )
            self._warmup_thread.start()

        logger.info("Background daemon warmup started.")

    @property
    def state(self) -> str:
        return self._warmup_state

    @property
    def error(self) -> Optional[str]:
        return self._warmup_error
