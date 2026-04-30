import lancedb
import logging
import numpy as np
import pickle
from pathlib import Path
from typing import Any, Optional, Tuple
from plesk_unified.tq_index import TurboQuantIndex
from plesk_unified import platform_utils

logger = logging.getLogger("plesk_unified")


class StorageRuntime:
    def __init__(self, base_dir: Path, model_runtime: Any):
        self.base_dir = base_dir
        self.model_runtime = model_runtime
        self._tq_index: Optional[TurboQuantIndex] = None

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
        path = self.db_path
        logger.debug("Connecting to LanceDB at %s", path)
        db = lancedb.connect(str(path))
        try:
            if create_new:
                logger.info("Creating/overwriting table 'plesk_knowledge'")
                try:
                    db.drop_table("plesk_knowledge")
                except Exception:
                    pass
                table = db.create_table(
                    "plesk_knowledge",
                    schema=self.model_runtime.get_schema(),
                    mode="overwrite",
                )
                # Task A: Enable Full-Text Search (FTS) for hybrid retrieval.
                table.create_fts_index(
                    ["text", "filename"], use_tantivy=True, replace=True
                )
                return table
            return db.open_table("plesk_knowledge")
        except Exception:
            logger.info("Table not found or error opening. Creating new table.")
            try:
                db.drop_table("plesk_knowledge")
            except Exception:
                pass
            table = db.create_table(
                "plesk_knowledge", schema=self.model_runtime.get_schema(), mode="create"
            )
            table.create_fts_index(["text", "filename"], use_tantivy=True, replace=True)
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
        return self.tq_dir / f"{profile.name}.pkl"

    def save_tq_index(self, tq_index: TurboQuantIndex) -> None:
        """Serialize and save the TurboQuant index to disk."""
        data = {
            "compressed_db": tq_index.compressed_db,
            "meta": tq_index._meta,
            "category_to_indices": tq_index._category_to_indices,
            "bits": tq_index.bits,
            "dim": tq_index.dim,
        }
        with self.get_tq_index_path().open("wb") as fh:
            pickle.dump(data, fh)

    def load_tq_index(self) -> Optional[TurboQuantIndex]:
        """Load the TurboQuant index from disk if it exists."""
        path = self.get_tq_index_path()
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

        with path.open("rb") as fh:
            data = pickle.load(fh)
        tq_index.compressed_db = data.get("compressed_db")
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
