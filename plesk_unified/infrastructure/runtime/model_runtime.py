import logging
import time
from typing import Any, Optional
from plesk_unified import platform_utils
from plesk_unified.model_config import get_active_profile

logger = logging.getLogger("plesk_unified")


class ModelRuntime:
    def __init__(self):
        self._embedding_model: Any = None
        self._schema_class: Any = None
        self._reranker: Any = None
        self._active_profile: Any = None
        self._detected_device: Optional[str] = None
        self._reranker_failed: bool = False

    def get_profile(self) -> Any:
        """Return the active model profile."""
        if self._active_profile is None:
            self._active_profile = get_active_profile()
        return self._active_profile

    def detect_device(self) -> str:
        """Detect the best available compute device (CUDA > MPS > CPU)."""
        if self._detected_device is not None:
            return self._detected_device

        platform_utils.log_platform_info()
        self._detected_device = platform_utils.get_optimal_device()
        logger.info("Selected compute device: %s", self._detected_device.upper())
        return self._detected_device

    def get_embedding_model(self) -> Any:
        """Return the embedding model, initializing it on first call."""
        if self._embedding_model is not None:
            return self._embedding_model

        from lancedb.embeddings import get_registry  # type: ignore

        profile = self.get_profile()
        device = self.detect_device()
        logger.info(
            "Initializing embedding model %s on %s...", profile.embed_model, device
        )
        init_started = time.perf_counter()

        reg = get_registry().get("huggingface")

        try:
            # Attempt 1: Optimal device
            try:
                self._embedding_model = reg.create(
                    name=profile.embed_model, device=device
                )
            except TypeError:
                # Fallback for older lancedb versions
                logger.debug("Device argument rejected, retrying without device kwarg.")
                self._embedding_model = reg.create(name=profile.embed_model)

            logger.info(
                "Embedding model initialized successfully in %.2fs.",
                time.perf_counter() - init_started,
            )
        except Exception as e:
            # If we failed and were using a hardware accelerator, fallback to CPU
            if device in ("cuda", "mps"):
                platform_utils.log_hardware_degradation(device, e, "cpu")
                try:
                    self._embedding_model = reg.create(
                        name=profile.embed_model, device="cpu"
                    )
                    logger.info("Embedding model initialized on CPU successfully.")
                except Exception as e2:
                    logger.critical(
                        "Embedding model failed to initialize even on CPU: %s",
                        e2,
                        exc_info=True,
                    )
                    raise
            else:
                logger.critical(
                    "Embedding model could not be initialized on %s: %s",
                    device,
                    e,
                    exc_info=True,
                )
                raise

        return self._embedding_model

    def get_schema(self) -> Any:
        """Return the LanceDB schema class, creating it on first call."""
        if self._schema_class is not None:
            return self._schema_class

        from lancedb.pydantic import LanceModel, Vector  # type: ignore

        profile = self.get_profile()
        em = self.get_embedding_model()
        dim = profile.embed_dim

        class UnifiedSchema(LanceModel):
            vector: Vector(dim) = em.VectorField()  # type: ignore
            text: str = em.SourceField()
            title: str
            filename: str
            category: str
            breadcrumb: str
            doctype: str  # Task: Persist doctype to enable doctype-aware reranking
            chunk_hash: str  # Task: Chunk-level fingerprinting
            endpoint: Optional[str] = None
            summary: Optional[str] = None  # Task REQ-3: global macro-context
            chunk_id: int  # Task D: Sequential ID within filename

        self._schema_class = UnifiedSchema
        return self._schema_class

    def get_reranker(self) -> Any:
        """Return the cross-encoder reranker, initializing it on first call."""
        if self._reranker is not None or self._reranker_failed:
            return self._reranker

        profile = self.get_profile()

        if not profile.reranker_enabled or not profile.reranker_model:
            logger.info("Reranker disabled by profile '%s'.", profile.name)
            return None

        logger.info("Initializing reranker %s...", profile.reranker_model)
        init_started = time.perf_counter()
        try:
            from sentence_transformers import CrossEncoder  # type: ignore

            device = self.detect_device()
            # TASK: Explicitly pass device and verify initialization
            self._reranker = CrossEncoder(profile.reranker_model, device=device)

            # Verification of actual device
            actual_device = "unknown"
            if hasattr(self._reranker, "model") and hasattr(
                self._reranker.model, "device"
            ):
                actual_device = str(self._reranker.model.device)
            elif hasattr(self._reranker, "device"):
                actual_device = str(self._reranker.device)

            logger.info(
                "Reranker initialized on %s (requested %s) in %.2fs.",
                actual_device,
                device,
                time.perf_counter() - init_started,
            )
        except Exception as e:
            self._reranker_failed = True
            logger.warning(
                "Reranker initialization failed on %s: %s. Reranking will be disabled.",
                self.detect_device(),
                str(e),
                exc_info=True,
            )
            return None

        return self._reranker
