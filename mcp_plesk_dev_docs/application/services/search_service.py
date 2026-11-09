import asyncio
import logging
import time
from typing import Any, List, Optional, Dict, Tuple

import numpy as np

from mcp_plesk_dev_docs.infrastructure.repositories.protocols import ISearchRepository
from mcp_plesk_dev_docs.application.services.query_cache import QueryCache

logger = logging.getLogger("mcp_plesk_dev_docs")


class SearchService:
    def __init__(  # noqa: PLR0913
        self,
        settings: Any,
        model_runtime: Any,
        storage_runtime: Any,
        lancedb_repo: ISearchRepository,
        search_formatter: Any,
        executor: Any,
    ):
        self.settings = settings
        self.model_runtime = model_runtime
        self.storage_runtime = storage_runtime
        self.lancedb_repo = lancedb_repo
        self.search_formatter = search_formatter
        self.executor = executor

        # Bounded LRU for expanded results; see _build_cache_key for the key.
        cache_size = getattr(settings, "plesk_query_cache_size", 256)
        if not isinstance(cache_size, int) or cache_size < 1:
            cache_size = 256
        cache_enabled = bool(getattr(settings, "plesk_query_cache_enabled", True))
        self._query_cache: Optional[QueryCache] = (
            QueryCache(maxsize=cache_size) if cache_enabled else None
        )

    def _sigmoid(self, x: np.ndarray | list[float] | float) -> np.ndarray | float:
        """Map raw logit(s) to [0, 1] probability using the sigmoid function."""
        return 1.0 / (1.0 + np.exp(-np.asarray(x, dtype=np.float64)))

    def _rerank_and_score(
        self, query: str, candidates: List[dict], reranker: Any
    ) -> List[dict]:
        """Apply a cross-encoder reranker to candidates and store _relevance scores."""
        if not candidates or reranker is None:
            return candidates

        texts = [r.get("text", "") for r in candidates]
        raw_scores = reranker.predict([(query, t) for t in texts])

        # Vectorized sigmoid application
        probabilities = self._sigmoid(raw_scores)

        scored = []
        for r, prob in zip(candidates, probabilities.tolist(), strict=True):
            result = dict(r)
            result["_relevance"] = float(prob)
            scored.append(result)

        scored.sort(key=lambda x: x["_relevance"], reverse=True)
        return scored

    def _deduplicate_by_filename(
        self, results: List[dict], max_per_file: int = 1
    ) -> List[dict]:
        """Return up to *max_per_file* entries per source file."""
        counts: Dict[str, int] = {}
        deduped: List[dict] = []
        for r in results:
            fname = r.get("filename", "")
            count = counts.get(fname, 0)
            if count < max_per_file:
                counts[fname] = count + 1
                deduped.append(r)
        return deduped

    def _rrf_merge(
        self, vector_results: List[dict], fts_results: List[dict], k: int = 20
    ) -> List[dict]:
        """Merge two ranked lists using Reciprocal Rank Fusion."""
        scores: Dict[str, float] = {}
        docs: Dict[str, dict] = {}

        for rank, doc in enumerate(vector_results):
            key = f"{doc.get('filename')}:{doc.get('text')}"
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank + 1)
            docs[key] = doc

        for rank, doc in enumerate(fts_results):
            key = f"{doc.get('filename')}:{doc.get('text')}"
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank + 1)
            if key not in docs:
                docs[key] = doc

        sorted_keys = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)
        results = []
        rrf_factor = float(k + 1)

        for key in sorted_keys:
            doc = docs[key]
            rrf_score = min(1.0, scores[key] * rrf_factor)
            if "_relevance" in doc:
                doc["_relevance"] = min(doc["_relevance"], rrf_score)
            else:
                doc["_relevance"] = rrf_score
            results.append(doc)

        logger.debug(
            "RRF Merge: %d vector, %d FTS -> %d unique results.",
            len(vector_results),
            len(fts_results),
            len(results),
        )
        return results

    def _get_vector_candidates(
        self, query: str, category: Optional[str], n_candidates: int
    ) -> List[Dict[str, Any]]:
        """Perform Vector Search."""
        profile = self.model_runtime.get_profile()

        if getattr(profile, "use_turboquant", False):
            query_vec = np.asarray(
                self.model_runtime.get_embedding_model().compute_query_embeddings(
                    query
                )[0],
                dtype=np.float32,
            )
            tq_results = self.storage_runtime.get_tq_index().search(
                query_vec,
                top_k=max(profile.tq_top_k, n_candidates),
                category=category,
            )
            vector_candidates = []
            for meta, score in tq_results:
                r = dict(meta)
                r["_relevance"] = float(self._sigmoid(float(score) * 5.0))
                vector_candidates.append(r)
            return vector_candidates

        filter_expr = f"category = '{category}'" if category else None
        raw = self.lancedb_repo.search_vector(
            query, limit=n_candidates, filter_expr=filter_expr
        )
        vector_candidates = []
        for r in raw:
            rc = dict(r)
            dist = float(rc.get("_distance") or 0.0)
            rc["_relevance"] = float(1.0 / (1.0 + dist))
            vector_candidates.append(rc)
        return vector_candidates

    def _get_fts_candidates(
        self, query: str, category: Optional[str], n_candidates: int
    ) -> List[Dict[str, Any]]:
        """Perform FTS search when enabled, otherwise return empty list."""
        enable_fts = getattr(self.settings, "plesk_enable_fts", True)
        if not enable_fts:
            return []

        safe_query = (query or "").strip()
        if not safe_query:
            return []

        filter_expr = f"category = '{category}'" if category else None
        start = time.monotonic()
        try:
            raw = self.lancedb_repo.search_fts(
                safe_query, limit=n_candidates, filter_expr=filter_expr
            )
            count = len(raw)
            elapsed_ms = (time.monotonic() - start) * 1000
            logger.info(
                "FTS search: query='%s', candidates=%d, latency=%.2fms",
                safe_query,
                count,
                elapsed_ms,
            )
        except Exception:
            logger.warning(
                "FTS search failed; falling back to vector only.", exc_info=True
            )
            return []

        # FTS ranks CHUNKS, so one long page can fill the whole candidate list
        # (measured: the top three hits for a UI query were three chunks of the
        # same 73624.htm). Cap it at two chunks per file so distinct documents
        # get a fair share of the RRF merge.
        return self._deduplicate_by_filename([dict(r) for r in raw], max_per_file=2)

    def _get_search_candidates(
        self, query: str, category: Optional[str], n_candidates: int
    ) -> List[Dict[str, Any]]:
        """Retrieve candidate pool using Hybrid Search (Vector + FTS)."""
        vector_candidates = self._get_vector_candidates(query, category, n_candidates)
        fts_candidates = self._get_fts_candidates(query, category, n_candidates)
        return self._rrf_merge(vector_candidates, fts_candidates)

    def _apply_relevance_gate(self, results: List[Dict[str, Any]]) -> Optional[str]:
        """Check top result against profile threshold. Returns error if below."""
        if not results:
            return "I could not find a reliable answer."

        profile = self.model_runtime.get_profile()
        min_relevance = (
            self.settings.plesk_min_relevance_threshold or profile.relevance_gate
        )

        if results[0].get("_relevance", 0.0) < min_relevance:
            logger.info(
                "Search confidence below threshold (%.4f < %.4f) for profile '%s'.",
                results[0].get("_relevance", 0.0),
                min_relevance,
                profile.name,
            )
            return "I could not find a reliable answer."
        return None

    def _expand_context_with_neighbors(self, results: List[dict]) -> List[dict]:
        """Fetch adjacent chunks for the top-5 results."""
        if not results:
            return results

        to_expand = results[:5]
        expanded_results = []

        for r in results:
            if r not in to_expand:
                expanded_results.append(r)
                continue

            fname = r.get("filename")
            cat = r.get("category")
            cid = r.get("chunk_id")

            if fname is None or cid is None:
                expanded_results.append(r)
                continue

            neighbors = self.lancedb_repo.get_neighbors(fname, cat, cid, window=1)
            if not neighbors:
                expanded_results.append(r)
                continue

            # Merge the texts
            texts = [n.get("text", "") for n in neighbors]
            clean_texts = []
            for t in texts:
                if "\n\n" in t:
                    clean_texts.append(t.split("\n\n", 1)[1].strip())
                else:
                    clean_texts.append(t)

            meta_header = r.get("text", "").split("\n\n", 1)[0]
            # Copy record to avoid mutation issues
            expanded = dict(r)
            expanded["text"] = f"{meta_header}\n\n" + "\n[...]\n".join(clean_texts)
            expanded_results.append(expanded)

        return expanded_results

    async def search_raw(
        self, query: str, category: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Run the search pipeline and return raw results."""
        return await self._run_search_pipeline(query, category)

    async def search(
        self, query: str, category: Optional[str] = None
    ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """
        The main search pipeline entrypoint.
        Returns (expanded_results, error_message).
        """
        safe_query = query or ""
        loop = asyncio.get_running_loop()

        def _sync_search():
            results = self._search_core(safe_query, category)
            # 4. Relevance Gate
            error_msg = self._apply_relevance_gate(results)
            if error_msg:
                return [], error_msg
            return results, None

        return await loop.run_in_executor(self.executor, _sync_search)

    @staticmethod
    def _normalize_query(query: str) -> str:
        """Collapse case and whitespace so equivalent queries share a key."""
        return " ".join((query or "").lower().split())

    def _get_table_version(self) -> Any:
        """Return the current LanceDB table version, or None if unavailable."""
        try:
            return self.lancedb_repo.get_table().version
        except Exception:
            # No table yet, or the repository is closed. Caching is skipped;
            # the search pipeline reports the real failure on its own path.
            logger.debug(
                "Query cache disabled: table version unavailable.", exc_info=True
            )
            return None

    def _build_cache_key(
        self, query: str, category: Optional[str], profile: Any
    ) -> Optional[Tuple[Any, ...]]:
        """Key expanded results on query, category, profile and table version.

        The table version makes a newly ingested index miss automatically; the
        profile name covers a profile switch. Returns None when caching is off
        or the table cannot be reached.
        """
        if self._query_cache is None:
            return None
        table_version = self._get_table_version()
        if table_version is None:
            return None
        return (
            self._normalize_query(query),
            category,
            profile.name,
            table_version,
        )

    def invalidate(self) -> None:
        """Drop cached results after a change that does not bump table.version.

        Ingest is covered by the version component of the cache key, but
        TurboQuant requantization re-ranks rows in place, so it must clear the
        cache explicitly.
        """
        if self._query_cache is not None:
            self._query_cache.clear()
            logger.info("Search cache invalidated.")

    def _search_core(
        self, safe_query: str, category: Optional[str]
    ) -> List[Dict[str, Any]]:
        """Shared core of the search pipeline.

        Candidates -> rerank -> dedup -> expand, with the expanded result list
        cached in an in-process LRU keyed on (normalized query, category,
        profile name, table version). A hit returns a shallow copy so callers
        cannot mutate the cached list.
        """
        started = time.monotonic()
        profile = self.model_runtime.get_profile()
        cache_key = self._build_cache_key(safe_query, category, profile)

        if cache_key is not None and self._query_cache is not None:
            cached = self._query_cache.get(cache_key)
            if cached is not None:
                elapsed_ms = (time.monotonic() - started) * 1000
                logger.info(
                    "Search cache: cache=hit query='%s' latency=%.2fms",
                    safe_query,
                    elapsed_ms,
                )
                return list(cached)

        n_candidates = profile.rerank_candidates
        candidates = self._get_search_candidates(safe_query, category, n_candidates)

        # 2. Rerank only top candidates to avoid cross-encoder bottleneck
        max_rerank = 35
        reranker = self.model_runtime.get_reranker()
        results = self._rerank_and_score(safe_query, candidates[:max_rerank], reranker)

        # 3. Deduplicate
        results = self._deduplicate_by_filename(results, max_per_file=1)

        # 4. Expand context
        expanded = self._expand_context_with_neighbors(results)

        if cache_key is not None and self._query_cache is not None:
            # Store a copy so a caller mutating the returned list cannot
            # mutate the cached entry (rows themselves are shared).
            self._query_cache.set(cache_key, list(expanded))
            elapsed_ms = (time.monotonic() - started) * 1000
            logger.info(
                "Search cache: cache=miss query='%s' latency=%.2fms",
                safe_query,
                elapsed_ms,
            )

        return expanded

    async def _run_search_pipeline(
        self, query: str, category: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Run _search_core inside the executor."""
        safe_query = query or ""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            self.executor, self._search_core, safe_query, category
        )

    async def get_file_content(self, filename: str, category: str) -> str:
        """Retrieve the full content of a specific documentation file."""
        loop = asyncio.get_running_loop()

        def _sync_get():
            table = self.lancedb_repo.get_table()
            # Fetch all chunks for this file, sorted by chunk_id
            chunks = (
                table.search()
                .where(f"filename = '{filename}' AND category = '{category}'")
                .limit(1000)
                .to_list()
            )
            if not chunks:
                return f"File '{filename}' not found in category '{category}'."

            chunks.sort(key=lambda x: x.get("chunk_id", 0))

            # Assemble full text.
            # We skip the meta-header for all but the first chunk if needed,
            # but usually chunks contain the full text block.
            # For simplicity, we join them with clear markers.
            parts = []
            for i, c in enumerate(chunks):
                text = c.get("text", "")
                if i > 0 and "\n\n" in text:
                    # Strip meta-header from subsequent chunks
                    parts.append(text.split("\n\n", 1)[1])
                else:
                    parts.append(text)

            return "\n\n".join(parts)

        return await loop.run_in_executor(self.executor, _sync_get)
