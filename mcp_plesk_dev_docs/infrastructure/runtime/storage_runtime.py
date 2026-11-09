import json
import logging
from pathlib import Path
from typing import Any, Optional, Tuple

import lancedb
import numpy as np
from safetensors import safe_open
from safetensors.torch import save_file

from mcp_plesk_dev_docs import platform_utils
from mcp_plesk_dev_docs.infrastructure.parsers import chunking
from mcp_plesk_dev_docs.infrastructure.turboquant_index import TurboQuantIndex

# Version tag stored in the safetensors metadata. Bump it whenever the on-disk
# layout changes, so old files are rebuilt instead of misread.
TQ_CACHE_FORMAT = "tq-v2"
_TQ_HEADER_KEY = "tq_header"
_TQ_PAYLOAD_KEY = "tq_payload"

logger = logging.getLogger("mcp_plesk_dev_docs")


class StorageRuntime:
    def __init__(self, base_dir: Path, model_runtime: Any):
        self.base_dir = base_dir
        self.model_runtime = model_runtime
        self._tq_index: Optional[TurboQuantIndex] = None
        self._cached_table: Optional[Any] = None

    @property
    def db_path(self) -> Path:
        """Return the path to the LanceDB database for the active profile."""
        profile = self.model_runtime.get_profile()
        return self.base_dir / "storage" / f"lancedb_{profile.name}"

    @property
    def tq_dir(self) -> Path:
        """Return the directory where TurboQuant indices are stored."""
        return self.base_dir / "storage" / "turboquant"

    def get_table(self, create_new: bool = False) -> Any:
        """Connect to or create the LanceDB table."""

        # 1. Clear cache if we are rebuilding the database
        if create_new:
            self._cached_table = None

        # 2. Return the warm table if it's already loaded in memory
        if self._cached_table is not None:
            return self._cached_table

        path = self.db_path
        logger.debug("Connecting to LanceDB at %s", path)
        db = lancedb.connect(str(path))
        try:
            if create_new:
                logger.info("Creating/overwriting table 'plesk_knowledge'")
                try:
                    db.drop_table("plesk_knowledge")
                except Exception:
                    logger.debug("Failed to drop table on overwrite")
                table = db.create_table(
                    "plesk_knowledge",
                    schema=self.model_runtime.get_schema(),
                    mode="overwrite",
                )
                self._cached_table = table
                return table

            table = db.open_table("plesk_knowledge")
            self._cached_table = table
            return table
        except Exception:
            logger.info("Table not found or error opening. Creating new table.")
            try:
                db.drop_table("plesk_knowledge")
            except Exception:
                logger.debug("Failed to drop table on recovery")
            table = db.create_table(
                "plesk_knowledge", schema=self.model_runtime.get_schema(), mode="create"
            )
            self._cached_table = table
            return table

    def table_health(self) -> Tuple[bool, Optional[str]]:
        """Check if the LanceDB table is readable."""
        try:
            db = lancedb.connect(str(self.db_path))
            db.open_table("plesk_knowledge")
            return True, None
        except Exception as exc:
            return False, str(exc)

    # ------------------------------------------------------------------
    # TurboQuant cache (v2: safetensors + JSON header)
    # ------------------------------------------------------------------

    def get_tq_index_path(self) -> Path:
        """Return the v2 safetensors cache path for the active profile."""
        profile = self.model_runtime.get_profile()
        self.tq_dir.mkdir(parents=True, exist_ok=True)
        return self.tq_dir / f"{profile.name}.safetensors"

    def get_legacy_tq_index_path(self) -> Path:
        """Return the pre-v2 JSON/base64 cache path for the active profile."""
        profile = self.model_runtime.get_profile()
        return self.tq_dir / f"{profile.name}.tqcache"

    def get_legacy_pickle_path(self) -> Path:
        """Return the pre-JSON pickle cache path for the active profile."""
        profile = self.model_runtime.get_profile()
        return self.tq_dir / f"{profile.name}.pkl"

    def _table_version(self) -> Optional[int]:
        """Return the LanceDB table version, or None when it is unreachable."""
        try:
            version = getattr(self.get_table(create_new=False), "version", None)
            return int(version) if version is not None else None
        except Exception as exc:
            logger.debug("Could not read LanceDB table version: %s", exc)
            return None

    def _create_tq_index(self) -> TurboQuantIndex:
        """Create a TurboQuantIndex, degrading to CPU when needed."""
        profile = self.model_runtime.get_profile()
        device = self.model_runtime.detect_device()
        try:
            return TurboQuantIndex(
                dim=profile.embed_dim,
                bits=profile.tq_bits,
                device=device,
            )
        except Exception as exc:
            if device in ("cuda", "mps"):
                platform_utils.log_hardware_degradation(device, exc, "cpu")
                return TurboQuantIndex(
                    dim=profile.embed_dim,
                    bits=profile.tq_bits,
                    device="cpu",
                )
            raise

    def _tq_header(self, tq_index: TurboQuantIndex) -> dict[str, Any]:
        """Build the metadata header that identifies this cache generation."""
        profile = self.model_runtime.get_profile()
        return {
            "format": TQ_CACHE_FORMAT,
            "chunk_version": chunking.CHUNK_VERSION,
            "table_version": self._table_version(),
            "model": profile.embed_model,
            "bits": tq_index.bits,
            "dim": tq_index.dim,
        }

    @staticmethod
    def _read_header(handle: Any) -> Optional[dict]:
        raw = (handle.metadata() or {}).get(_TQ_HEADER_KEY)
        if not raw:
            return None
        try:
            header = json.loads(raw)
        except (TypeError, ValueError):
            return None
        return header if isinstance(header, dict) else None

    @staticmethod
    def _read_payload(handle: Any) -> dict:
        raw = (handle.metadata() or {}).get(_TQ_PAYLOAD_KEY)
        if not raw:
            return {}
        try:
            payload = json.loads(raw)
        except (TypeError, ValueError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def _header_mismatch(self, header: Optional[dict]) -> Optional[str]:
        """Return why ``header`` cannot serve the current table, or None."""
        if header is None:
            return "missing or unreadable header"

        profile = self.model_runtime.get_profile()
        expected = {
            "format": TQ_CACHE_FORMAT,
            "chunk_version": chunking.CHUNK_VERSION,
            "table_version": self._table_version(),
            "model": profile.embed_model,
            "bits": profile.tq_bits,
            "dim": profile.embed_dim,
        }
        for field, expected_value in expected.items():
            actual = header.get(field)
            if actual != expected_value:
                return f"{field}={actual!r}, expected {expected_value!r}"
        return None

    def save_tq_index(self, tq_index: TurboQuantIndex) -> None:
        """Persist the TurboQuant index as a v2 safetensors file.

        The compressed tensors and a JSON payload (doc metadata) live in the
        same file; a JSON header in the safetensors metadata records the
        generation of the LanceDB corpus the tensors were built from.
        """
        tq_index.flush()
        header = self._tq_header(tq_index)
        payload = {
            "meta": tq_index._meta,
            "category_to_indices": tq_index._category_to_indices,
        }
        tensors = {
            key: (tensor if tensor.device.type == "cpu" else tensor.cpu()).contiguous()
            for key, tensor in (tq_index.compressed_db or {}).items()
        }
        path = self.get_tq_index_path()
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        save_file(
            tensors,
            str(tmp_path),
            metadata={
                _TQ_HEADER_KEY: json.dumps(header),
                _TQ_PAYLOAD_KEY: json.dumps(payload),
            },
        )
        tmp_path.replace(path)
        logger.info(
            "Saved TurboQuant index v2 (%d documents) to %s.",
            len(tq_index._meta),
            path.name,
        )

    def load_tq_index(self) -> Optional[TurboQuantIndex]:
        """Load the v2 cache, or return None when the caller must rebuild.

        The file is opened with ``safe_open`` so the tensors are memory-mapped.
        A missing/mismatched header, an unreadable file, or a legacy cache
        (JSON/base64 ``.tqcache``, pickle ``.pkl``) all return None.
        """
        path = self.get_tq_index_path()

        pkl_path = self.get_legacy_pickle_path()
        if pkl_path.exists():
            logger.warning(
                "Found legacy pickle cache %s; it is never loaded (unsafe format).",
                pkl_path,
            )
            if not path.exists():
                return None

        legacy_json = self.get_legacy_tq_index_path()
        if not path.exists():
            if legacy_json.exists():
                logger.warning(
                    "Found legacy JSON cache %s; it has no version header, so it "
                    "is treated as stale and rebuilt from LanceDB.",
                    legacy_json,
                )
            return None

        try:
            with safe_open(str(path), framework="pt", device="cpu") as handle:
                mismatch = self._header_mismatch(self._read_header(handle))
                if mismatch is not None:
                    logger.warning(
                        "TurboQuant cache %s is stale (%s); rebuilding from LanceDB.",
                        path.name,
                        mismatch,
                    )
                    return None

                tq_index = self._create_tq_index()
                payload = self._read_payload(handle)
                tq_index.compressed_db = {
                    key: handle.get_tensor(key) for key in handle.keys()
                }
                tq_index._meta = payload.get("meta", [])
                tq_index._category_to_indices = payload.get("category_to_indices", {})
        except Exception as exc:
            logger.warning(
                "TurboQuant cache %s is unreadable (%s); rebuilding from LanceDB.",
                path.name,
                exc,
            )
            return None

        logger.info(
            "Loaded TurboQuant index v2 from %s (%d documents).",
            path.name,
            len(tq_index._meta),
        )
        return tq_index

    def build_tq_index_from_table(self) -> TurboQuantIndex:
        """Build a new TurboQuant index by scanning the LanceDB table."""
        table = self.get_table(create_new=False)
        all_docs = table.search().limit(100000).to_list()

        tq_index = self._create_tq_index()

        if all_docs:
            corpus_vecs = np.asarray(
                [doc["vector"] for doc in all_docs], dtype=np.float32
            )
            # The raw vector is redundant once the compressed tensors exist and
            # it would dominate the JSON sidecar, so it is not persisted.
            metas = [
                {key: value for key, value in doc.items() if key != "vector"}
                for doc in all_docs
            ]
            tq_index.add(corpus_vecs, metas)

        self.save_tq_index(tq_index)
        logger.info("TurboQuant index built with %d documents.", len(all_docs))
        return tq_index

    def get_tq_index(self) -> TurboQuantIndex:
        """Return the TurboQuant index, loading or building it as needed."""
        if self._tq_index is not None:
            return self._tq_index

        loaded = self.load_tq_index()
        if loaded is not None:
            self._tq_index = loaded
            logger.info("Using TurboQuant cache %s", self.get_tq_index_path().name)
            return self._tq_index

        logger.info("TurboQuant cache missing or stale; building from LanceDB table.")
        self._tq_index = self.build_tq_index_from_table()
        return self._tq_index
