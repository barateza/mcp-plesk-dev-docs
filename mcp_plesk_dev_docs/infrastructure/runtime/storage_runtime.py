import lancedb
import logging
import numpy as np
import json
import base64
import torch
from pathlib import Path
from typing import Any, Optional, Tuple
from mcp_plesk_dev_docs.infrastructure.turboquant_index import TurboQuantIndex
from mcp_plesk_dev_docs import platform_utils


def _encode_tensor_dict(
    tensors: dict[str, torch.Tensor] | None,
) -> dict | None:
    """Encode a dict of torch Tensors as a JSON-serialisable structure."""
    if tensors is None:
        return None
    encoded = {}
    for name, t in tensors.items():
        cpu_t = t.cpu().contiguous()
        encoded[name] = {
            "data": base64.b64encode(cpu_t.numpy().tobytes()).decode("ascii"),
            "dtype": str(cpu_t.dtype),
            "shape": list(cpu_t.shape),
        }
    return {"__tensor_dict__": True, "items": encoded}


def _decode_tensor_dict(obj: dict | None) -> dict[str, torch.Tensor] | None:
    """Reconstruct a dict of torch Tensors from the encoded structure."""
    if obj is None:
        return None
    decoded = {}
    for name, enc in obj["items"].items():
        arr = np.frombuffer(base64.b64decode(enc["data"]), dtype=np.dtype(enc["dtype"]))
        decoded[name] = torch.from_numpy(arr.reshape(enc["shape"]))
    return decoded


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
        # full-tq shares embeddings/dimension with full, so reuse full's LanceDB corpus.
        db_profile = (
            "full" if getattr(profile, "use_turboquant", False) else profile.name
        )
        return self.base_dir / "storage" / f"lancedb_{db_profile}"

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

    def get_tq_index_path(self) -> Path:
        """Return the path to the TurboQuant index file for the active profile."""
        profile = self.model_runtime.get_profile()
        self.tq_dir.mkdir(parents=True, exist_ok=True)
        return self.tq_dir / f"{profile.name}.tqcache"

    def save_tq_index(self, tq_index: TurboQuantIndex) -> None:
        """Serialize and save the TurboQuant index to disk in JSON format."""
        data = {
            "compressed_db": _encode_tensor_dict(tq_index.compressed_db),
            "meta": tq_index._meta,
            "category_to_indices": tq_index._category_to_indices,
            "bits": tq_index.bits,
            "dim": tq_index.dim,
        }
        with self.get_tq_index_path().open("w") as fh:
            json.dump(data, fh)

    def load_tq_index(self) -> Optional[TurboQuantIndex]:
        """Load the TurboQuant index from disk if it exists."""
        path = self.get_tq_index_path()

        # Detect stale pickle files from previous format versions
        old_pkl = path.with_suffix(".pkl")
        if old_pkl.exists():
            logger.warning(
                "Found legacy pickle file %s. Ignoring it so the index "
                "gets rebuilt in the new JSON format.",
                old_pkl,
            )
            return None

        if not path.exists():
            return None

        profile = self.model_runtime.get_profile()
        device = self.model_runtime.detect_device()
        try:
            tq_index = TurboQuantIndex(
                dim=profile.embed_dim,
                bits=profile.tq_bits,
                device=device,
            )
        except Exception as e:
            if device in ("cuda", "mps"):
                platform_utils.log_hardware_degradation(device, e, "cpu")
                tq_index = TurboQuantIndex(
                    dim=profile.embed_dim,
                    bits=profile.tq_bits,
                    device="cpu",
                )
            else:
                raise

        with path.open("r") as fh:
            data = json.load(fh)
        tq_index.compressed_db = _decode_tensor_dict(data.get("compressed_db"))
        tq_index._meta = data.get("meta", [])
        tq_index._category_to_indices = data.get("category_to_indices", {})
        return tq_index

    def build_tq_index_from_table(self) -> TurboQuantIndex:
        """Build a new TurboQuant index by scanning the LanceDB table."""
        profile = self.model_runtime.get_profile()
        table = self.get_table(create_new=False)
        all_docs = table.search().limit(100000).to_list()

        device = self.model_runtime.detect_device()
        try:
            tq_index = TurboQuantIndex(
                dim=profile.embed_dim,
                bits=profile.tq_bits,
                device=device,
            )
        except Exception as e:
            if device in ("cuda", "mps"):
                platform_utils.log_hardware_degradation(device, e, "cpu")
                tq_index = TurboQuantIndex(
                    dim=profile.embed_dim,
                    bits=profile.tq_bits,
                    device="cpu",
                )
            else:
                raise

        if all_docs:
            corpus_vecs = np.asarray(
                [doc["vector"] for doc in all_docs], dtype=np.float32
            )
            tq_index.add(corpus_vecs, all_docs)

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
            logger.info(
                "Loaded TurboQuant index from %s", self.get_tq_index_path().name
            )
            return self._tq_index

        logger.info("TurboQuant index not found on disk. Building from LanceDB...")
        self._tq_index = self.build_tq_index_from_table()
        return self._tq_index
