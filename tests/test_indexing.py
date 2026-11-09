import pytest
import time
import asyncio
import threading
from unittest.mock import MagicMock, AsyncMock, patch
import concurrent.futures
from pathlib import Path

from lancedb.index import Bitmap, BTree, IvfPq

# New imports from the service-based architecture
from fastmcp import Context
from mcp_plesk_dev_docs.application.services.container import AppContainer
from mcp_plesk_dev_docs.settings import PleskSettings as Settings
from mcp_plesk_dev_docs.application.services.indexing_service import (
    FILE_WINDOW_SIZE,
    IndexingService,
)
from mcp_plesk_dev_docs.infrastructure.parsers import chunking
from mcp_plesk_dev_docs.infrastructure.repositories.lancedb_repository import (
    LanceDbRepository,
)

# New tool imports
from mcp_plesk_dev_docs.server.tools.indexing_tools import (
    trigger_index_sync,
)
from mcp_plesk_dev_docs.infrastructure.jobs.job_registry import (
    JobRegistry,
)


# Helper to create a completed Future
def make_completed_future(result_value):
    f = concurrent.futures.Future()
    f.set_result(result_value)
    return f


# Fixture to provide a fresh JobRegistry for each test
@pytest.fixture
def job_registry_instance():
    return JobRegistry()


@pytest.fixture
async def mock_indexing_dependencies(job_registry_instance):
    mock_container = MagicMock(spec=AppContainer)
    mock_ctx = MagicMock(spec=Context)

    # Configure mock_ctx to provide mock_container
    mock_ctx.request_context.lifespan_context = {"container": mock_container}

    # --- Mock settings ---
    mock_container.settings = MagicMock(spec=Settings)
    mock_container.settings.plesk_model_profile = "pro"

    # --- Mock executor ---
    mock_container.executor = MagicMock(spec=concurrent.futures.ThreadPoolExecutor)
    mock_container.executor.submit.side_effect = make_completed_future

    # --- Mock logger ---
    mock_container.logger = MagicMock()

    # --- Mock LanceDbRepository and its table ---
    mock_container.lancedb_repo = MagicMock()
    mock_table = MagicMock()
    mock_table.create_index.return_value = None
    mock_container.lancedb_repo.get_table.return_value = mock_table

    # --- Mock SourceStateRepository ---
    mock_container.source_state_repo = MagicMock()
    mock_container.source_state_repo.load.return_value = {"sources": {}}
    mock_container.source_state_repo.save.return_value = None

    # --- Mock SourceCatalog (sources) ---
    mock_container.sources = MagicMock()
    mock_container.sources.ensure_source_exists.return_value = True
    mock_container.sources.compute_source_fingerprint.return_value = ("abc", 10)

    # --- Mock ModelRuntime ---
    mock_container.model_runtime = MagicMock()
    mock_profile = MagicMock()
    mock_profile.name = "pro"
    mock_profile.use_turboquant = False
    mock_container.model_runtime.get_profile.return_value = mock_profile

    # --- Mock IndexingService ---
    mock_container.indexing_service = MagicMock()
    mock_container.indexing_service.refresh_knowledge = AsyncMock()
    mock_container.indexing_service.refresh_knowledge.return_value = (
        "Mock refresh completed successfully."
    )
    mock_container.indexing_service.process_source_files = MagicMock()
    mock_container.indexing_service.process_source_files.return_value = (
        set()
    )  # For trigger_index_sync
    mock_container.indexing_service.persist_batch = AsyncMock()
    mock_container.indexing_service.persist_batch.return_value = None
    mock_container.indexing_service.create_index.return_value = None
    mock_container.indexing_service.delete_source.return_value = None

    # --- Mock JobService to be the JobRegistry instance ---
    mock_container.job_service = job_registry_instance

    yield mock_ctx, mock_container, job_registry_instance


@pytest.mark.asyncio
async def test_submit_job_returns_job_id_within_100ms(job_registry_instance):
    """
    Tests that submit_job returns a job_id promptly, simulating a quick submission.
    """
    start_time = time.perf_counter()
    job_id = job_registry_instance.submit_job(
        lambda: time.sleep(0.001)
    )  # A very short job
    end_time = time.perf_counter()

    assert isinstance(job_id, str)
    assert len(job_id) == 8  # Default uuid4[:8]
    assert (end_time - start_time) * 1000 < 100  # Should be well under 100ms


@pytest.mark.asyncio
async def test_check_sync_status_unknown_id_returns_not_found(job_registry_instance):
    """
    Tests that check_sync_status returns 'not_found' for a job_id that doesn't exist.
    """
    status = job_registry_instance.get_status("non-existent-id")
    assert status == {"status": "not_found"}


@pytest.mark.asyncio
async def test_job_transitions_queued_to_completed(job_registry_instance):
    """
    Tests the full lifecycle of a job: queued -> running -> completed.
    Uses polling to reliably observe state transitions.
    """
    job_started_in_thread = (
        threading.Event()
    )  # Use threading.Event for cross-thread signaling

    def mock_job_work():
        job_started_in_thread.set()  # Indicate that the job's work has begun
        time.sleep(0.01)  # Simulate some blocking work

    job_id = job_registry_instance.submit_job(mock_job_work)

    # Poll for 'running' status
    status = {"status": "queued"}
    for _ in range(100):  # Try up to 100 times
        status = job_registry_instance.get_status(job_id)
        if status["status"] == "running":
            break
        await asyncio.sleep(0.001)
    assert status["status"] in (
        "running",
        "completed",
    )  # Might be already completed on fast machines

    # Wait for the job's work to actually start (via event)
    job_started_in_thread.wait(timeout=1)

    # Poll for 'completed' status
    for _ in range(100):
        status = job_registry_instance.get_status(job_id)
        if status["status"] == "completed":
            break
        await asyncio.sleep(0.001)
    assert status["status"] == "completed"
    assert status["error"] is None
    assert status["finished_at"] is not None


@pytest.mark.asyncio
async def test_job_transitions_queued_to_failed(job_registry_instance):
    """
    Tests that a job transitions from queued -> running -> failed if an exception
    occurs.
    Uses polling to reliably observe state transitions.
    """
    job_started_in_thread = threading.Event()

    def mock_failing_job_work():
        job_started_in_thread.set()
        raise ValueError("Simulated job failure")

    job_id = job_registry_instance.submit_job(mock_failing_job_work)

    # Wait for the job's work to actually start (via event)
    job_started_in_thread.wait(timeout=1)

    # Poll for 'failed' status
    status = job_registry_instance.get_status(job_id)
    for _ in range(100):
        status = job_registry_instance.get_status(job_id)
        if status["status"] == "failed":
            break
        await asyncio.sleep(0.001)
    assert status["status"] == "failed"
    assert "Simulated job failure" in status["error"]
    assert status["finished_at"] is not None


@pytest.mark.asyncio
async def test_10_concurrent_submits_are_thread_safe(
    mock_indexing_dependencies,
):
    """
    Tests that 10 concurrent job submissions via trigger_index_sync
    are thread-safe and all complete successfully.
    """
    mock_ctx, mock_container, job_registry_instance = mock_indexing_dependencies
    num_jobs = 10

    async def submit_and_check():
        result = await trigger_index_sync(mock_ctx, category="cli")
        job_id = result["job_id"]

        # Poll for completion
        status = {"status": "queued"}
        for _ in range(500):
            status = job_registry_instance.get_status(job_id)
            if status["status"] == "completed":
                break
            if status["status"] == "failed":
                pytest.fail(f"Job {job_id} failed unexpectedly: {status.get('error')}")
            await asyncio.sleep(0.01)

        assert status["status"] == "completed"
        return job_id, status

    tasks = [submit_and_check() for _ in range(num_jobs)]
    completed_jobs_info = await asyncio.gather(*tasks)

    assert len(completed_jobs_info) == num_jobs
    all_job_ids = [job_id for job_id, _ in completed_jobs_info]
    assert len(set(all_job_ids)) == num_jobs  # Ensure unique job IDs

    for _job_id, final_status in completed_jobs_info:
        assert final_status["status"] == "completed"


# ---------------------------------------------------------------------------
# LanceDbRepository.ensure_indexes
# ---------------------------------------------------------------------------


def _make_index_table(rows=100, dim=384, indexed_columns=()):
    table = MagicMock()
    table.count_rows.return_value = rows
    table.schema.field.return_value.type.list_size = dim
    table.list_indices.return_value = [
        MagicMock(columns=[column]) for column in indexed_columns
    ]
    return table


def _repository_for(table):
    storage = MagicMock()
    storage.get_table.return_value = table
    return LanceDbRepository(storage)


def test_ensure_indexes_creates_vector_and_scalar_indexes():
    table = _make_index_table(rows=100, dim=384)
    repo = _repository_for(table)

    created = repo.ensure_indexes()

    assert created == ["IVF_PQ(vector)", "BITMAP(category)", "BTREE(filename)"]
    table.create_index.assert_any_call(
        "vector",
        config=IvfPq(distance_type="l2", num_partitions=10, num_sub_vectors=24),
    )
    table.create_index.assert_any_call("category", config=Bitmap())
    table.create_index.assert_any_call("filename", config=BTree())


def test_ensure_indexes_is_idempotent():
    table = _make_index_table(indexed_columns=("vector", "category", "filename"))
    repo = _repository_for(table)

    assert repo.ensure_indexes() == []
    table.create_index.assert_not_called()


def test_ensure_indexes_skips_an_empty_table():
    table = _make_index_table(rows=0)
    repo = _repository_for(table)

    assert repo.ensure_indexes() == []
    table.create_index.assert_not_called()


# ---------------------------------------------------------------------------
# IndexingService._rebuild_indices
# ---------------------------------------------------------------------------


def _run_now(fn, *args, **kwargs):
    future = concurrent.futures.Future()
    try:
        future.set_result(fn(*args, **kwargs))
    except Exception as exc:  # pragma: no cover - defensive
        future.set_exception(exc)
    return future


@pytest.mark.asyncio
async def test_rebuild_indices_optimizes_creates_indexes_then_rebuilds_fts():
    order = []
    table = MagicMock()
    table.optimize.side_effect = lambda: order.append("optimize")
    table.create_index.side_effect = lambda *args, **kwargs: order.append("fts")

    repo = MagicMock()
    repo.get_table.return_value = table

    def _ensure_indexes():
        order.append("ensure_indexes")
        return ["IVF_PQ(vector)"]

    repo.ensure_indexes.side_effect = _ensure_indexes

    profile = MagicMock()
    profile.use_turboquant = False
    model_runtime = MagicMock()
    model_runtime.get_profile.return_value = profile

    executor = MagicMock(spec=concurrent.futures.ThreadPoolExecutor)
    executor.submit.side_effect = _run_now

    service = IndexingService(
        settings=MagicMock(),
        model_runtime=model_runtime,
        storage_runtime=MagicMock(),
        lancedb_repo=repo,
        source_state_repo=MagicMock(),
        summary_cache_repo=MagicMock(),
        processor_registry=MagicMock(),
        source_catalog=MagicMock(),
        executor=executor,
    )

    report = await service._rebuild_indices()

    assert order == ["optimize", "ensure_indexes", "fts"]
    table.optimize.assert_called_once()
    assert "Search indexes created: IVF_PQ(vector)." in report
    assert "FTS index rebuilt successfully." in report


# ---------------------------------------------------------------------------
# Issue #90: one hash map per category, bounded fan-out, isolated executor
# ---------------------------------------------------------------------------

FILES_BY_CATEGORY = {
    "guide": [Path("a.htm"), Path("b.htm"), Path("d.htm"), Path("e.htm")],
    "cli": [Path("c.htm"), Path("f.htm")],
}

HASH_ROWS_BY_CATEGORY = {
    "guide": [
        {"filename": "a.htm", "chunk_hash": "a1"},
        {"filename": "a.htm", "chunk_hash": "a2"},
        {"filename": "b.htm", "chunk_hash": "b1"},
        {"filename": "d.htm", "chunk_hash": "d1"},
        {"filename": "e.htm", "chunk_hash": "e1"},
    ],
    "cli": [
        {"filename": "c.htm", "chunk_hash": "c1"},
        {"filename": "f.htm", "chunk_hash": "f1"},
    ],
}


class _HashScanTable:
    """Table double that records the shape of every hash scan it receives."""

    def __init__(self, rows_by_category, row_count=100):
        self.rows_by_category = rows_by_category
        self.row_count = row_count
        self.search_calls = 0
        self.selected = []
        self.filters = []
        self._filter = None

    def count_rows(self):
        return self.row_count

    def search(self, *args, **kwargs):
        self.search_calls += 1
        return self

    def where(self, expr, **kwargs):
        self.filters.append(expr)
        self._filter = expr
        return self

    def select(self, columns):
        self.selected.append(list(columns))
        return self

    def limit(self, _limit):
        return self

    def to_list(self):
        category = self._filter.split("'")[1]
        return self.rows_by_category.get(category, [])

    def delete(self, *_args, **_kwargs):  # pragma: no cover - guard only
        raise AssertionError("a refresh with no removed files must not delete")


def _source(category, source_type="html"):
    source = MagicMock()
    source.category.value = category
    source.path = Path("/dev/null") / category
    source.source_type = source_type
    source.repo_url = None
    source.zip_url = None
    return source


def _indexing_service(repo=None, device="cpu", summaries=False):
    settings = MagicMock()
    settings.plesk_index_summaries = summaries
    model_runtime = MagicMock()
    model_runtime.detect_device.return_value = device
    executor = MagicMock(spec=concurrent.futures.ThreadPoolExecutor)
    executor.submit.side_effect = _run_now
    return IndexingService(
        settings=settings,
        model_runtime=model_runtime,
        storage_runtime=MagicMock(),
        lancedb_repo=repo if repo is not None else MagicMock(),
        source_state_repo=MagicMock(),
        summary_cache_repo=MagicMock(),
        processor_registry=MagicMock(),
        source_catalog=MagicMock(),
        executor=executor,
    )


@pytest.mark.asyncio
async def test_hash_lookups_are_one_per_category_not_per_file():
    table = _HashScanTable(HASH_ROWS_BY_CATEGORY)
    service = _indexing_service(_repository_for(table))
    # A matching chunk version lets the run reuse stored hashes; the stale
    # fingerprint still forces the refresh to do its work.
    entries = {
        category: {"chunk_version": chunking.CHUNK_VERSION, "fingerprint": "old"}
        for category in FILES_BY_CATEGORY
    }

    def _files(legacy_source):
        return FILES_BY_CATEGORY[legacy_source["cat"]]

    with (
        patch(
            "mcp_plesk_dev_docs.infrastructure.sources.acquisition"
            ".ensure_source_exists",
            return_value=True,
        ),
        patch(
            "mcp_plesk_dev_docs.infrastructure.sources.discovery"
            ".compute_source_fingerprint",
            return_value=("fresh", 6),
        ),
        patch(
            "mcp_plesk_dev_docs.infrastructure.sources.discovery"
            ".collect_files_for_source",
            side_effect=_files,
        ),
        patch(
            "mcp_plesk_dev_docs.infrastructure.sources.discovery.load_toc_map",
            return_value={},
        ),
    ):
        for category in FILES_BY_CATEGORY:
            await service._sync_single_source(_source(category), False, entries)

    # Six files across two categories. The per-file path issued one filtered
    # scan per file; the hash map issues one per category and projects only
    # the two columns the diff needs.
    assert len(FILES_BY_CATEGORY) == 2
    assert table.search_calls == 2
    assert table.selected == [["filename", "chunk_hash"]] * 2


@pytest.mark.asyncio
async def test_process_single_file_never_searches_the_table():
    table = _HashScanTable({})
    service = _indexing_service(_repository_for(table))

    result = await service._process_single_file(
        Path("a.htm"),
        _source("guide"),
        {},
        {"a.htm": ["h1", "h2"]},
        None,
        asyncio.Semaphore(10),
    )

    assert result == ["h1", "h2"]
    assert table.search_calls == 0


@pytest.mark.asyncio
async def test_file_fan_out_is_bounded_by_the_window():
    service = _indexing_service()
    files = [Path(f"f{i}.htm") for i in range(200)]
    in_flight = 0
    peak = 0

    async def _tracked(*_args, **_kwargs):
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0.002)
        in_flight -= 1
        return []

    service._process_single_file = _tracked

    results = await service._run_sync_tasks(_source("guide"), files, {}, {})

    assert len(results) == 200
    assert peak > 1
    assert peak <= FILE_WINDOW_SIZE


@pytest.mark.asyncio
async def test_cpu_flushes_four_thousand_chunk_batches():
    repo = MagicMock()
    service = _indexing_service(repo)
    records = [{"chunk_hash": f"h{i}"} for i in range(5000)]

    active = await service._handle_indexing_results([records], set(), "guide")

    sizes = [len(call.args[0]) for call in repo.persist_batch.call_args_list]
    assert sizes == [4096, 904]
    assert len(active) == 5000


@pytest.mark.asyncio
async def test_mps_keeps_the_small_batch_for_stability():
    repo = MagicMock()
    service = _indexing_service(repo, device="mps")
    records = [{"chunk_hash": f"h{i}"} for i in range(300)]

    await service._handle_indexing_results([records], set(), "guide")

    sizes = [len(call.args[0]) for call in repo.persist_batch.call_args_list]
    assert sizes == [256, 44]


def test_container_shutdown_stops_the_indexing_executor():
    indexing_executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)
    container = AppContainer(
        settings=MagicMock(),
        logger=MagicMock(),
        executor=MagicMock(),
        sources=MagicMock(),
        model_runtime=MagicMock(),
        storage_runtime=MagicMock(),
        warmup_service=MagicMock(),
        health_service=MagicMock(),
        search_formatter=MagicMock(),
        toc_formatter=MagicMock(),
        lancedb_repo=MagicMock(),
        source_state_repo=MagicMock(),
        summary_cache_repo=MagicMock(),
        search_service=MagicMock(),
        indexing_service=MagicMock(),
        processor_registry=MagicMock(),
        indexing_executor=indexing_executor,
    )

    container.shutdown()

    with pytest.raises(RuntimeError):
        indexing_executor.submit(lambda: None)
