import logging
from typing import Any, List, Set, Optional

logger = logging.getLogger("plesk_unified")


class LanceDbRepository:
    def __init__(self, storage_runtime: Any):
        self.storage_runtime = storage_runtime

    def get_table(self) -> Any:
        """Return the LanceDB table."""
        return self.storage_runtime.get_table()

    def search_vector(
        self, vector: List[float], limit: int = 10, filter_expr: Optional[str] = None
    ) -> List[dict]:
        """Perform a vector search."""
        table = self.get_table()
        query = table.search(vector).limit(limit)
        if filter_expr:
            query = query.where(filter_expr)
        return query.to_list()

    def search_fts(
        self, text: str, limit: int = 10, filter_expr: Optional[str] = None
    ) -> List[dict]:
        """Perform a full-text search."""
        table = self.get_table()
        query = table.search(text).limit(limit)
        if filter_expr:
            query = query.where(filter_expr)
        return query.to_list()

    def get_existing_hashes(self, category: str) -> Set[str]:
        """Return all chunk hashes currently in the database for a category."""
        table = self.get_table()
        try:
            rows = (
                table.search()
                .where(f"category = '{category}'")
                .select(["chunk_hash"])
                .limit(1000000)
                .to_list()
            )
            return {r["chunk_hash"] for r in rows if r.get("chunk_hash")}
        except Exception:
            logger.warning(
                "Could not fetch existing hashes for category '%s'.",
                category,
                exc_info=True,
            )
            return set()

    def get_existing_filenames(self, category: str) -> Set[str]:
        """Return all unique filenames currently in the database for a category."""
        table = self.get_table()
        try:
            rows = (
                table.search()
                .where(f"category = '{category}'")
                .select(["filename"])
                .limit(1000000)
                .to_list()
            )
            return {r["filename"] for r in rows if r.get("filename")}
        except Exception:
            logger.warning(
                "Could not fetch existing filenames for category '%s'.",
                category,
                exc_info=True,
            )
            return set()

    def delete_stale_chunks(self, category: str, active_hashes: Set[str]) -> None:
        """Delete chunks for a category that are not in the active_hashes set."""
        table = self.get_table()
        if not active_hashes:
            logger.info("No active hashes for category '%s', deleting all.", category)
            table.delete(f"category = '{category}'")
            return

        # LanceDB's `delete` with `NOT IN` can be slow for large sets.
        # But for typically < 10k hashes it's fine.
        hash_list = ",".join([f"'{h}'" for h in active_hashes])
        filter_expr = f"category = '{category}' AND chunk_hash NOT IN ({hash_list})"
        table.delete(filter_expr)

    def persist_batch(self, records: List[dict]) -> None:
        """Append a batch of records to the table."""
        if not records:
            return
        table = self.get_table()
        table.add(records)

    def get_neighbors(
        self, filename: str, category: str, chunk_id: int, window: int = 1
    ) -> List[dict]:
        """Fetch neighbor chunks (id-window to id+window) from same file and category."""
        table = self.get_table()
        try:
            neighbors = (
                table.search()
                .where(
                    f"filename = '{filename}' AND category = '{category}' "
                    f"AND chunk_id >= {chunk_id - window} AND chunk_id <= {chunk_id + window}"
                )
                .limit(2 * window + 1)
                .to_list()
            )
            # Sort locally to be sure
            neighbors.sort(key=lambda x: x.get("chunk_id", 0))
            return neighbors
        except Exception as e:
            logger.warning(
                "Neighbor retrieval failed for %s:%d: %s", filename, chunk_id, e
            )
            return []
