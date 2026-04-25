import logging
from typing import Any, Optional
from plesk_unified.tq_index import TurboQuantIndex

logger = logging.getLogger("plesk_unified")


class TurboQuantRepository:
    def __init__(self, storage_runtime: Any):
        self.storage_runtime = storage_runtime

    def load(self) -> Optional[TurboQuantIndex]:
        """Load the TurboQuant index from disk."""
        return self.storage_runtime.load_tq_index()

    def save(self, tq_index: TurboQuantIndex) -> None:
        """Save the TurboQuant index to disk."""
        self.storage_runtime.save_tq_index(tq_index)

    def build_from_table(self) -> TurboQuantIndex:
        """Build a new TurboQuant index from the database."""
        return self.storage_runtime.build_tq_index_from_table()
