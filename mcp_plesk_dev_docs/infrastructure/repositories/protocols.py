"""Protocol interfaces for repository dependencies."""

from typing import List, Optional, Protocol, Set


class IVectorRepository(Protocol):
    """Interface for vector search operations."""

    def search_vector(
        self, vector: List[float], limit: int = 10, filter_expr: Optional[str] = None
    ) -> List[dict]: ...

    def get_neighbors(
        self, filename: str, category: str, chunk_id: int, window: int = 1
    ) -> List[dict]: ...


class IFtsRepository(Protocol):
    """Interface for full-text search operations."""

    def search_fts(
        self, text: str, limit: int = 10, filter_expr: Optional[str] = None
    ) -> List[dict]: ...

    def get_existing_hashes(self, category: str) -> Set[str]: ...

    def get_existing_filenames(self, category: str) -> Set[str]: ...


class ISearchRepository(IVectorRepository, IFtsRepository, Protocol):
    """Combined interface for the search service repository (vector + FTS)."""

    pass


class IDocumentStore(Protocol):
    """Interface for document storage operations (indexing path)."""

    def get_table(self) -> object: ...

    def persist_batch(self, records: List[dict]) -> None: ...

    def delete_stale_chunks(self, category: str, active_hashes: Set[str]) -> None: ...

    def get_existing_hashes(self, category: str) -> Set[str]: ...

    def get_existing_filenames(self, category: str) -> Set[str]: ...
