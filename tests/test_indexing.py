import pytest
import time
import asyncio
import threading
from unittest.mock import MagicMock, AsyncMock
import concurrent.futures

# New imports from the service-based architecture
from fastmcp import Context
from plesk_unified.application.services.container import AppContainer
from plesk_unified.settings import PleskSettings as Settings

# New tool imports
from plesk_unified.server.tools.indexing_tools import (
    trigger_index_sync,
)
from plesk_unified.indexing import (
    JobRegistry,
)  # Assuming this is still the core JobRegistry


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
    mock_container.settings.plesk_model_profile = "full-tq"

    # --- Mock executor ---
    mock_container.executor = MagicMock(spec=concurrent.futures.ThreadPoolExecutor)
    mock_container.executor.submit.side_effect = make_completed_future

    # --- Mock logger ---
    mock_container.logger = MagicMock()

    # --- Mock LanceDbRepository and its table ---
    mock_container.lancedb_repo = MagicMock()
    mock_table = MagicMock()
    mock_table.create_fts_index.return_value = None
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
    mock_profile.name = "full-tq"
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
    mock_container.indexing_service.create_fts_index.return_value = None
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
