import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, List, Set, Optional, Dict, Callable
from pathlib import Path

from plesk_unified import io_utils, chunking
from plesk_unified.ai_client import AIClient

logger = logging.getLogger("plesk_unified")


class IndexingService:
    def __init__(  # noqa: PLR0913
        self,
        settings: Any,
        model_runtime: Any,
        storage_runtime: Any,
        lancedb_repo: Any,
        turboquant_repo: Any,
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
        self.turboquant_repo = turboquant_repo
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
        existing_files: Set[str],
        ai_client: Optional[AIClient],
        semaphore: asyncio.Semaphore,
    ) -> List[Dict[str, Any]]:
        """Process a single file and return records or existing hashes."""
        if f.name in existing_files:

            def _fetch_hashes():
                table = self.lancedb_repo.get_table()
                rows = (
                    table.search()
                    .where(
                        f"filename = '{f.name}' AND "
                        f"category = '{source.category.value}'"
                    )
                    .select(["chunk_hash"])
                    .limit(1000)
                    .to_list()
                )
                return [row["chunk_hash"] for row in rows]

            return await asyncio.get_running_loop().run_in_executor(
                self.executor, _fetch_hashes
            )

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

        # Optimize batch size for device (MPS is inefficient with very large batches)
        device = self.model_runtime.detect_device()
        BATCH_SIZE_CHUNKS = 256 if device == "mps" else 1000

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

            if len(pending_docs) >= BATCH_SIZE_CHUNKS:
                logger.info("Embedding/Saving batch of %d chunks...", len(pending_docs))
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
        existing_files: Set[str],
    ) -> List[Any]:
        semaphore = asyncio.Semaphore(10)
        ai_client = (
            AIClient(api_key=self.settings.openrouter_api_key)
            if self.settings.plesk_index_summaries
            else None
        )

        tasks = []
        for f in files:
            if f.name.startswith("_") or f.name == "toc.json":
                continue
            tasks.append(
                self._process_single_file(
                    f, source, toc_map, existing_files, ai_client, semaphore
                )
            )

        results = await asyncio.gather(*tasks)
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

        if not io_utils.ensure_source_exists(legacy_source):
            logger.error("SKIPPED %s (Source check failed)", source.category.value)
            return f"SKIPPED {source.category.value} (Source check failed)"

        loop = asyncio.get_running_loop()
        fingerprint, file_count = await loop.run_in_executor(
            self.executor, lambda: io_utils.compute_source_fingerprint(legacy_source)
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
            existing_hashes = self.lancedb_repo.get_existing_hashes(
                source.category.value
            )
            existing_files = set()
            if (
                not reset_db
                and prev_meta.get("chunk_version") == chunking.CHUNK_VERSION
            ):
                existing_files = self.lancedb_repo.get_existing_filenames(
                    source.category.value
                )

            toc_map = await loop.run_in_executor(
                self.executor,
                lambda: (
                    io_utils.load_toc_map(source.path)
                    if source.source_type == "html"
                    else {}
                ),
            )
            files = io_utils.collect_files_for_source(legacy_source)

            results = await self._run_sync_tasks(source, files, toc_map, existing_files)

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

        try:
            table = self.lancedb_repo.get_table()
            await loop.run_in_executor(
                self.executor,
                lambda: table.create_fts_index(
                    ["text", "filename"], use_tantivy=True, replace=True
                ),
            )
            report.append("FTS index rebuilt successfully.")
        except Exception:
            logger.exception("Failed to rebuild FTS index.")
            report.append("ERROR rebuilding FTS index.")

        await self._call_progress(progress_callback, 3, 4)

        profile = self.model_runtime.get_profile()
        if getattr(profile, "use_turboquant", False):
            try:
                await loop.run_in_executor(
                    self.executor, self.turboquant_repo.build_from_table
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
