import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, List, Set, Optional, Dict, Callable
from pathlib import Path

from lancedb.index import FTS

from mcp_plesk_dev_docs.infrastructure.parsers import chunking
from mcp_plesk_dev_docs.infrastructure.repositories.protocols import IDocumentStore
from mcp_plesk_dev_docs.infrastructure.sources import acquisition, discovery
from mcp_plesk_dev_docs.infrastructure.ai_client import AIClient

logger = logging.getLogger("mcp_plesk_dev_docs")


# Files per ingest window. The old `_run_sync_tasks` built one coroutine per
# file and gathered them all, so a multi-thousand-file source had every file in
# flight at once and queued the lot on the executor.
FILE_WINDOW_SIZE = 64

# Chunks per `table.add()`. 4096 appends one fragment per few thousand rows
# instead of one per 256-1000, which is what lets `table.optimize()` keep the
# fragment count flat across refreshes. MPS keeps the small batch: large
# batches there trip multi-threaded PyTorch deadlocks (see `_persist_docs`).
BATCH_SIZE_CHUNKS_CPU = 4096
BATCH_SIZE_CHUNKS_MPS = 256


class IndexingService:
    def __init__(  # noqa: PLR0913
        self,
        settings: Any,
        model_runtime: Any,
        storage_runtime: Any,
        lancedb_repo: IDocumentStore,
        source_state_repo: Any,
        summary_cache_repo: Any,
        processor_registry: Any,
        source_catalog: Any,
        executor: Any,
    ):
        self.settings = settings
        self.model_runtime = model_runtime
        self.storage_runtime = storage_runtime
        self.lancedb_repo = lancedb_repo
        self.source_state_repo = source_state_repo
        self.summary_cache_repo = summary_cache_repo
        self.processor_registry = processor_registry
        self.source_catalog = source_catalog
        self.executor = executor

    async def _call_progress(
        self,
        progress_callback: Optional[Callable[[int, int], Any]],
        current: int,
        total: int = 4,
    ) -> None:
        if not progress_callback:
            return
        try:
            res = progress_callback(current, total)
            if asyncio.iscoroutine(res):
                await res
        except Exception as e:
            logger.debug("Progress callback failed: %s", e)

    async def _get_summary(
        self,
        f: Path,
        text: str,
        ai_client: Optional[AIClient],
        semaphore: asyncio.Semaphore,
    ) -> Optional[str]:
        if not self.settings.plesk_index_summaries or not text:
            return None

        summary = self.summary_cache_repo.get(f)
        if summary:
            logger.info("Using cached summary for %s", f.name)
            return summary

        if ai_client:
            async with semaphore:
                summary = await ai_client.generate_description_async(text)
                if summary == "Description unavailable.":
                    logger.warning("Summary unavailable for %s", f.name)
                    return None
                self.summary_cache_repo.set(f, summary)
                return summary
        return None

    async def _process_single_file(
        self,
        f: Path,
        source: Any,
        toc_map: Dict[str, Any],
        existing_map: Dict[str, List[str]],
        ai_client: Optional[AIClient],
        semaphore: asyncio.Semaphore,
    ) -> List[Any]:
        """Return new records for a file, or the hashes already stored for it.

        Hash lookups happen once per category before this runs, so the
        already-indexed branch is a dict lookup: no scan and no per-file round
        trip into LanceDB.
        """
        if f.name in existing_map:
            return list(existing_map[f.name])

        processor = self.processor_registry.get(source.source_type)

        loop = asyncio.get_running_loop()
        parsed_doc = await loop.run_in_executor(
            self.executor, lambda: processor.parse(f)
        )
        if not parsed_doc:
            return []

        if toc_map and f.name in toc_map:
            meta = toc_map[f.name]
            parsed_doc.title = meta.get("title", parsed_doc.title)
            parsed_doc.breadcrumb = meta.get("breadcrumb", parsed_doc.breadcrumb)

        summary = await self._get_summary(f, parsed_doc.text, ai_client, semaphore)

        def _chunk():
            doctype = processor.infer_doctype(parsed_doc, source)
            chunks = processor.chunk(parsed_doc, source, doctype)
            if not chunks:
                return []

            return chunking.build_doc_records(
                parsed_doc.filename,
                chunks,
                {
                    "title": parsed_doc.title,
                    "category": source.category.value,
                    "breadcrumb": parsed_doc.breadcrumb,
                    "doctype": doctype,
                    "endpoint": parsed_doc.endpoint,
                    "summary": summary,
                },
            )

        return await loop.run_in_executor(self.executor, _chunk)

    async def _handle_indexing_results(
        self, results: List[Any], existing_hashes: Set[str], category: str
    ) -> Set[str]:
        pending_docs = []
        active_hashes = set()

        # MPS trips multi-threaded PyTorch deadlocks on very large batches, so
        # it keeps the small one; CPU/CUDA flush ~16x fewer fragments.
        device = self.model_runtime.detect_device()
        batch_size = BATCH_SIZE_CHUNKS_MPS if device == "mps" else BATCH_SIZE_CHUNKS_CPU

        for result in results:
            if not result:
                continue

            if isinstance(result[0], str):
                active_hashes.update(result)
            else:
                for r in result:
                    h = r["chunk_hash"]
                    active_hashes.add(h)
                    if h not in existing_hashes:
                        pending_docs.append(r)
                    # Flush at the chunk boundary, not the file boundary: one
                    # large file must not produce an unbounded embedding batch.
                    if len(pending_docs) >= batch_size:
                        logger.info(
                            "Embedding/Saving batch of %d chunks...",
                            len(pending_docs),
                        )
                        await self._persist_docs(list(pending_docs))
                        pending_docs = []

        if pending_docs:
            logger.info(
                "Embedding/Saving final batch of %d chunks...", len(pending_docs)
            )
            await self._persist_docs(list(pending_docs))

        return active_hashes

    async def _persist_docs(self, docs: List[Dict[str, Any]]) -> None:
        device = self.model_runtime.detect_device()
        if device == "mps":
            # For MPS stability and to avoid multi-threaded PyTorch deadlocks,
            # perform persistence directly on the main thread.
            self.lancedb_repo.persist_batch(docs)
        else:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                self.executor, lambda: self.lancedb_repo.persist_batch(docs)
            )

    async def _run_sync_tasks(
        self,
        source: Any,
        files: List[Path],
        toc_map: Dict[str, Any],
        existing_map: Dict[str, List[str]],
    ) -> List[Any]:
        semaphore = asyncio.Semaphore(10)
        ai_client = (
            AIClient(api_key=self.settings.openrouter_api_key)
            if self.settings.plesk_index_summaries
            else None
        )

        targets = [
            f for f in files if not (f.name.startswith("_") or f.name == "toc.json")
        ]

        # Bounded fan-out: windows keep the pending coroutine count and the
        # executor queue flat, so a 2 000-file source no longer queues 2 000
        # parse/chunk jobs before the first one finishes.
        results: List[Any] = []
        for start in range(0, len(targets), FILE_WINDOW_SIZE):
            window = targets[start : start + FILE_WINDOW_SIZE]
            window_results = await asyncio.gather(
                *(
                    self._process_single_file(
                        f, source, toc_map, existing_map, ai_client, semaphore
                    )
                    for f in window
                )
            )
            results.extend(window_results)
        if ai_client:
            await ai_client.close()
        self.summary_cache_repo.save()
        return results

    async def _sync_single_source(
        self,
        source: Any,
        reset_db: bool,
        source_entries: Dict[str, Any],
    ) -> str:
        logger.info("Processing source: %s", source.category.value)
        legacy_source = {
            "path": source.path,
            "cat": source.category.value,
            "type": source.source_type,
            "repo_url": source.repo_url,
            "zip_url": source.zip_url,
        }

        if not acquisition.ensure_source_exists(legacy_source):
            logger.error("SKIPPED %s (Source check failed)", source.category.value)
            return f"SKIPPED {source.category.value} (Source check failed)"

        loop = asyncio.get_running_loop()
        fingerprint, file_count = await loop.run_in_executor(
            self.executor, lambda: discovery.compute_source_fingerprint(legacy_source)
        )
        prev_meta = source_entries.get(source.category.value, {})

        table_is_empty = False
        try:
            table = self.lancedb_repo.get_table()
            table_is_empty = (
                await loop.run_in_executor(self.executor, table.count_rows) == 0
            )
        except Exception:
            table_is_empty = True

        source_changed = (
            reset_db
            or table_is_empty
            or prev_meta.get("fingerprint") != fingerprint
            or prev_meta.get("chunk_version") != chunking.CHUNK_VERSION
        )

        if not source_changed:
            logger.info(
                "SKIPPED %s (No source changes detected)", source.category.value
            )
            return f"SKIPPED {source.category.value} (No source changes detected)"

        try:
            # One projected scan per category feeds both the diff set and the
            # per-file hash map; the vector column never leaves LanceDB.
            hash_map = self.lancedb_repo.get_chunk_hash_map(source.category.value)
            existing_hashes = {h for hashes in hash_map.values() for h in hashes}
            # A chunker version bump must rechunk every file, but the old rows
            # are still needed below to delete the hashes this run replaces.
            reusable_map: Dict[str, List[str]] = {}
            if (
                not reset_db
                and prev_meta.get("chunk_version") == chunking.CHUNK_VERSION
            ):
                reusable_map = hash_map

            toc_map = await loop.run_in_executor(
                self.executor,
                lambda: (
                    discovery.load_toc_map(source.path)
                    if source.source_type == "html"
                    else {}
                ),
            )
            files = discovery.collect_files_for_source(legacy_source)

            results = await self._run_sync_tasks(source, files, toc_map, reusable_map)

            active_hashes = await self._handle_indexing_results(
                results, existing_hashes, source.category.value
            )

            if not reset_db:
                stale_hashes = existing_hashes - active_hashes
                if stale_hashes:
                    await loop.run_in_executor(
                        self.executor,
                        lambda: self.lancedb_repo.delete_stale_chunks(
                            source.category.value, stale_hashes
                        ),
                    )

            source_entries[source.category.value] = {
                "fingerprint": fingerprint,
                "chunk_version": chunking.CHUNK_VERSION,
                "file_count": file_count,
                "indexed_at": datetime.now(timezone.utc).isoformat(),
            }
        except Exception:
            logger.exception("Error processing source %s", source.category.value)
            source_entries[source.category.value] = {
                "fingerprint": fingerprint,
                "file_count": file_count,
                "indexed_at": datetime.now(timezone.utc).isoformat(),
                "error": "indexing-failed",
            }

        return f"Finished pass for {source.category.value}."

    async def _rebuild_indices(
        self, progress_callback: Optional[Callable[[int, int], Any]] = None
    ) -> List[str]:
        loop = asyncio.get_running_loop()
        report = []

        # Ingest appends one fragment per batch, so without compaction the table
        # accumulates files and every scan opens more of them. optimize() also
        # folds rows added since the last index build into the existing indexes.
        table = self.lancedb_repo.get_table()
        try:
            await loop.run_in_executor(self.executor, table.optimize)
            report.append("Table optimized (compaction + index folding).")
        except Exception:
            logger.warning("Table optimize failed; continuing.", exc_info=True)
            report.append("ERROR optimizing the table.")

        # ANN (IVF_PQ) + scalar (BITMAP/BTREE) indexes. Best-effort: a missing
        # index costs latency, not correctness, so this never fails the refresh.
        ensure_indexes = getattr(self.lancedb_repo, "ensure_indexes", None)
        if ensure_indexes is not None:
            try:
                created = list(
                    await loop.run_in_executor(self.executor, ensure_indexes) or []
                )
                if created:
                    report.append(f"Search indexes created: {', '.join(created)}.")
                else:
                    report.append("Search indexes already present.")
            except Exception:
                logger.warning("Could not ensure search indexes.", exc_info=True)
                report.append("ERROR creating search indexes.")

        # Native LanceDB FTS. Tantivy-backed FTS was removed in lancedb 0.40
        # (`use_tantivy=True` now raises), and a native index covers exactly one
        # field, so only `text` is indexed: filenames are opaque such as
        # "79359.htm" and carry no terms worth BM25-scoring.
        #
        # Failure is re-raised, not logged and swallowed. The old code produced
        # "job completed, error: null" while no FTS index existed at all, which
        # silently degraded hybrid search to vector-only.
        try:
            await loop.run_in_executor(
                self.executor,
                lambda: table.create_index(
                    "text",
                    config=FTS(
                        language="English",
                        stem=True,
                        remove_stop_words=True,
                        ascii_folding=True,
                    ),
                ),
            )
            report.append("FTS index rebuilt successfully.")
        except Exception as exc:
            logger.exception("Failed to rebuild FTS index.")
            raise RuntimeError(
                "FTS index rebuild failed; hybrid search would silently degrade "
                f"to vector-only. Cause: {exc}"
            ) from exc

        await self._call_progress(progress_callback, 3, 4)

        profile = self.model_runtime.get_profile()
        if getattr(profile, "use_turboquant", False):
            try:
                await loop.run_in_executor(
                    self.executor, self.storage_runtime.build_tq_index_from_table
                )
                report.append("TurboQuant index rebuilt and persisted.")
            except Exception:
                logger.exception("Failed to rebuild TurboQuant index.")
                report.append("ERROR rebuilding TurboQuant index.")

        return report

    async def refresh_knowledge(
        self,
        progress_callback: Optional[Callable[[int, int], Any]] = None,
        category: str = "all",
        reset_db: bool = False,
    ) -> str:
        """The main knowledge refresh pipeline."""
        await self._call_progress(progress_callback, 1, 4)

        logger.info(
            "Starting refresh_knowledge: target=%s, reset_db=%s",
            category,
            reset_db,
        )

        profile = self.model_runtime.get_profile()
        source_state = self.source_state_repo.load()
        profile_state = source_state.setdefault(profile.name, {})
        source_entries = profile_state.setdefault("sources", {})

        if reset_db:
            self.storage_runtime.get_table(create_new=True)
            logger.warning("Database wiped by request.")

        tasks = []
        for source in self.source_catalog.all():
            if category in {"all", source.category.value}:
                tasks.append(self._sync_single_source(source, reset_db, source_entries))

        report = []
        if tasks:
            for task in tasks:
                result = await task
                report.append(result)

        await self._call_progress(progress_callback, 2, 4)

        self.source_state_repo.save(source_state)

        index_report = await self._rebuild_indices(progress_callback)
        report.extend(index_report)

        await self._call_progress(progress_callback, 4, 4)

        return "\n".join(report)
