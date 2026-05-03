import asyncio
import logging
import time
from typing import Any, List, Optional, Dict, Tuple

import numpy as np

logger = logging.getLogger("plesk_unified")


class SearchService:
    def __init__(  # noqa: PLR0913
        self,
        settings: Any,
        model_runtime: Any,
        storage_runtime: Any,
        lancedb_repo: Any,
        turboquant_repo: Any,
        search_formatter: Any,
        executor: Any,
    ):
        self.settings = settings
        self.model_runtime = model_runtime
        self.storage_runtime = storage_runtime
        self.lancedb_repo = lancedb_repo
        self.turboquant_repo = turboquant_repo
        self.search_formatter = search_formatter
        self.executor = executor

    def _sigmoid(self, x: float) -> float:
        """Map a raw logit to a [0, 1] probability using the sigmoid function."""
        return 1.0 / (1.0 + np.exp(-x))

    def _rerank_and_score(
        self, query: str, candidates: List[dict], reranker: Any
    ) -> List[dict]:
        """Apply a cross-encoder reranker to candidates and store _relevance scores."""
        if not candidates or reranker is None:
            return candidates

        texts = [r.get("text", "") for r in candidates]
        raw_scores = reranker.predict([(query, t) for t in texts])

        scored = []
        for r, raw in zip(candidates, raw_scores, strict=True):
            result = dict(r)
            result["_relevance"] = float(self._sigmoid(float(raw)))
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
            tq_results = self.turboquant_repo.get_tq_index().search(
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

        return [dict(r) for r in raw]

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
        default_threshold = 0.55
        if profile.name == "light":
            default_threshold = 0.50
        elif profile.name == "medium":
            default_threshold = 0.60

        min_relevance = self.settings.plesk_min_relevance_threshold or default_threshold

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
        safe_query = query or ""
        loop = asyncio.get_running_loop()

        def _sync_pipeline():
            # 1. Retrieve candidates
            candidates = self._get_search_candidates(safe_query, category, 15)

            # 2. Rerank
            reranker = self.model_runtime.get_reranker()
            results = self._rerank_and_score(safe_query, candidates, reranker)

            # 3. Deduplicate
            results = self._deduplicate_by_filename(results, max_per_file=1)

            # 4. Expand context
            expanded_results = self._expand_context_with_neighbors(results)
            return expanded_results

        return await loop.run_in_executor(self.executor, _sync_pipeline)

    async def search(
        self, query: str, category: Optional[str] = None
    ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """
        The main search pipeline entrypoint.
        Returns (expanded_results, error_message).
        """
        safe_query = query or ""
        loop = asyncio.get_running_loop()

        def _sync_pipeline():
            # 1. Retrieve candidates
            candidates = self._get_search_candidates(safe_query, category, 15)

            # 2. Rerank
            reranker = self.model_runtime.get_reranker()
            results = self._rerank_and_score(safe_query, candidates, reranker)

            # 3. Deduplicate
            results = self._deduplicate_by_filename(results, max_per_file=1)

            # 4. Relevance Gate
            error_msg = self._apply_relevance_gate(results)
            if error_msg:
                return [], error_msg

            # 5. Expand context
            expanded_results = self._expand_context_with_neighbors(results)
            return expanded_results, None

        return await loop.run_in_executor(self.executor, _sync_pipeline)

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
