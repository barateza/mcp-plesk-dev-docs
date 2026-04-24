import pytest
import time
import asyncio
import threading
from unittest.mock import MagicMock, patch, AsyncMock
from plesk_unified.indexing import JobRegistry
from plesk_unified.server import trigger_index_sync
import concurrent.futures


# Helper to create a completed Future
def make_completed_future(result_value):
    f = concurrent.futures.Future()
    f.set_result(result_value)
    return f


# Fixture to provide a fresh JobRegistry for each test
@pytest.fixture
def job_registry_instance():
    return JobRegistry()


@pytest.fixture(autouse=True)
def mock_server_dependencies_for_indexing():
    """
    Mock dependencies needed for trigger_index_sync and check_sync_status.
    Specifically, we want to mock `refresh_knowledge` which is called by `job_wrapper`.
    """
    mock_server_executor = MagicMock(spec=concurrent.futures.ThreadPoolExecutor)

    def mock_submit_side_effect(func, *args, **kwargs):
        return make_completed_future(func(*args, **kwargs))

    mock_server_executor.submit.side_effect = mock_submit_side_effect

    with (
        patch("plesk_unified.server._executor", new=mock_server_executor),
        patch(
            "plesk_unified.server.refresh_knowledge", new_callable=AsyncMock
        ) as mock_refresh_knowledge,
        patch(
            "plesk_unified.server._get_profile"
        ) as mock_get_profile,  # Needed by refresh_knowledge
        patch("plesk_unified.server._load_source_state", return_value={"sources": {}}),
        patch("plesk_unified.server._save_source_state"),
        patch(
            "plesk_unified.server.get_table"
        ) as mock_get_table,  # Needed by refresh_knowledge
        patch(
            "plesk_unified.server._build_tq_index_from_table", new_callable=MagicMock
        ),  # Needed by refresh_knowledge
    ):
        # Configure mock_refresh_knowledge to simulate completion quickly by default
        mock_refresh_knowledge.return_value = "Mock refresh completed successfully."

        # Configure mock_get_profile
        mock_profile = MagicMock()
        mock_profile.name = "test_profile"
        mock_profile.use_turboquant = False
        mock_get_profile.return_value = mock_profile

        # Configure mock_get_table
        mock_table = MagicMock()
        mock_table.create_fts_index.return_value = None
        mock_get_table.return_value = mock_table

        yield mock_refresh_knowledge


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
    job_registry_instance, mock_server_dependencies_for_indexing
):
    """
    Tests that 10 concurrent job submissions via trigger_index_sync
    are thread-safe and all complete successfully.
    """
    num_jobs = 10
    # Patch global registry to use our instance
    with patch("plesk_unified.server.job_registry", job_registry_instance):

        async def submit_and_check():
            result = await trigger_index_sync(category="cli")
            job_id = result["job_id"]

            # Poll for completion
            status = {"status": "queued"}
            for _ in range(500):
                status = job_registry_instance.get_status(job_id)
                if status["status"] == "completed":
                    break
                if status["status"] == "failed":
                    pytest.fail(
                        f"Job {job_id} failed unexpectedly: {status.get('error')}"
                    )
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
