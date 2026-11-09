import logging
import math
from typing import Any, List, Set, Optional

from lancedb.index import Bitmap, BTree, IvfPq

logger = logging.getLogger("mcp_plesk_dev_docs")


def _sub_vector_count(dim: int) -> int:
    """Largest divisor of *dim* at most ``dim // 16`` for PQ sub-vectors.

    ``num_sub_vectors`` must divide the vector width, and 16 dimensions per
    sub-vector is the usual quality/size trade-off. For the 384/768/1024-d
    profiles this is exactly ``dim // 16``.
    """
    for count in range(max(1, dim // 16), 0, -1):
        if dim % count == 0:
            return count
    return 1


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
            # prefilter=True applies the predicate BEFORE the limit. Without it
            # LanceDB filters the top-N after the scan, so a category-filtered
            # query silently returns fewer than `limit` rows.
            query = query.where(filter_expr, prefilter=True)

        return query.to_list()

    def search_fts(
        self, text: str, limit: int = 10, filter_expr: Optional[str] = None
    ) -> List[dict]:
        """Perform a full-text search."""
        table = self.get_table()
        # query_type="fts" is REQUIRED. The default is "auto", which embeds the
        # string and performs a VECTOR search even when an inverted index exists
        # (measured on lancedb 0.40: auto returned _score=None hits), so the RRF
        # merge was combining a list with its own near-duplicate.
        query = table.search(text, query_type="fts").limit(limit)
        if filter_expr:
            query = query.where(filter_expr, prefilter=True)

        return query.to_list()

    def ensure_indexes(self) -> List[str]:
        """Create the ANN and scalar indexes retrieval depends on.

        Idempotent: a column already covered by ``table.list_indices()``
        (including the FTS index) is left untouched. Call this after ingest and
        after ``table.optimize()`` so new fragments are folded into the indexes.

        Returns one short label per index created, so the caller can report it.
        """
        table = self.get_table()
        created: List[str] = []

        try:
            row_count = table.count_rows()
        except Exception:
            logger.warning(
                "Could not count table rows; skipping index creation.",
                exc_info=True,
            )
            return created

        if row_count == 0:
            logger.info("Skipping index creation: table has no rows yet.")
            return created

        indexed_columns = self._indexed_columns(table)

        if "vector" in indexed_columns:
            logger.info("Vector index already present; skipping.")
        else:
            dim = self._vector_dim(table)
            if dim is None:
                logger.warning("Skipping vector index: unknown vector dimension.")
            else:
                # metric="l2" keeps the existing distance scale: the search
                # service maps `_distance` to relevance with 1/(1+distance).
                num_partitions = max(1, math.isqrt(row_count))
                num_sub_vectors = _sub_vector_count(dim)
                try:
                    table.create_index(
                        "vector",
                        config=IvfPq(
                            distance_type="l2",
                            num_partitions=num_partitions,
                            num_sub_vectors=num_sub_vectors,
                        ),
                    )
                    created.append("IVF_PQ(vector)")
                    logger.info(
                        "Created IVF_PQ index on 'vector' (metric=l2, "
                        "partitions=%d, sub_vectors=%d, rows=%d).",
                        num_partitions,
                        num_sub_vectors,
                        row_count,
                    )
                except Exception:
                    logger.warning(
                        "Could not create the IVF_PQ index; vector search "
                        "falls back to a flat scan.",
                        exc_info=True,
                    )

        scalar_indexes = (
            ("category", Bitmap, "BITMAP(category)"),
            ("filename", BTree, "BTREE(filename)"),
        )
        for column, config_type, label in scalar_indexes:
            if column in indexed_columns:
                logger.info("Scalar index on '%s' already present; skipping.", column)
                continue
            try:
                table.create_index(column, config=config_type())
                created.append(label)
                logger.info("Created %s index.", label)
            except Exception:
                logger.warning(
                    "Could not create the %s index; filtered queries may be slower.",
                    label,
                    exc_info=True,
                )

        return created

    @staticmethod
    def _indexed_columns(table: Any) -> Set[str]:
        """Return every column that already has a LanceDB index."""
        try:
            indices = table.list_indices()
        except Exception:
            logger.warning(
                "Could not list table indices; assuming none exist.",
                exc_info=True,
            )
            return set()
        columns: Set[str] = set()
        for index in indices:
            columns.update(getattr(index, "columns", None) or [])
        return columns

    @staticmethod
    def _vector_dim(table: Any) -> Optional[int]:
        """Read the fixed-size vector width from the LanceDB schema."""
        try:
            return int(table.schema.field("vector").type.list_size)
        except Exception:
            logger.warning("Could not read the vector dimension.", exc_info=True)
            return None

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
        """Fetch neighbor chunks from the same file and category."""
        table = self.get_table()
        try:
            neighbors = (
                table.search()
                .where(
                    f"filename = '{filename}' AND category = '{category}' "
                    f"AND chunk_id >= {chunk_id - window} "
                    f"AND chunk_id <= {chunk_id + window}"
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
