import pytest
import inspect
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from plesk_unified import server
import concurrent.futures  # Needed for MockConcurrentFuture


# Helper to create a completed Future
def make_completed_future(result_value):
    f = concurrent.futures.Future()
    f.set_result(result_value)
    return f


@pytest.fixture(autouse=True)
def mock_all_ml_and_io_calls():
    """
    Mock all ML model calls and I/O operations for fast, isolated tests.
    """
    mock_server_executor = MagicMock(spec=concurrent.futures.ThreadPoolExecutor)

    def mock_submit_side_effect(func, *args, **kwargs):
        return make_completed_future(func(*args, **kwargs))

    mock_server_executor.submit.side_effect = mock_submit_side_effect

    with (
        # Patch server._executor with our specially configured mock
        patch("plesk_unified.server._executor", new=mock_server_executor),
        # Mock embedding model
        patch(
            "plesk_unified.server.get_embedding_model", new_callable=AsyncMock
        ) as mock_embed_model,
        # Mock LanceDB
        patch("plesk_unified.server.get_table") as mock_get_table,
        # Mock reranker
        patch(
            "plesk_unified.server.get_reranker", new_callable=AsyncMock
        ) as mock_reranker,
        # Mock TurboQuant
        patch(
            "plesk_unified.server.get_tq_index", new_callable=AsyncMock
        ) as mock_tq_index,
        # Mock external I/O utilities
        patch("plesk_unified.server.io_utils.ensure_source_exists", return_value=True),
        patch(
            "plesk_unified.server.io_utils.compute_source_fingerprint",
            return_value=("mock_fingerprint", 1),
        ),
        patch("plesk_unified.server.io_utils.load_toc_map", return_value={}),
        patch(
            "plesk_unified.server.io_utils.collect_files_for_source", return_value=[]
        ),
        patch(
            "plesk_unified.server.platform_utils.get_optimal_device", return_value="cpu"
        ),
        # Mock _get_profile which is called by many functions
        patch("plesk_unified.server._get_profile") as mock_get_profile,
        # Mock source state saving/loading to ensure "SKIPPED" for refresh_knowledge
        patch(
            "plesk_unified.server._load_source_state",
            return_value={
                "version": 1,
                "sources": {
                    "cli": {
                        # Matching fingerprint and chunk_version for "cli" category
                        "fingerprint": "mock_fingerprint",
                        "chunk_version": server.chunking.CHUNK_VERSION,
                        # Use actual CHUNK_VERSION
                        "file_count": 1,
                        "indexed_at": "2023-01-01T00:00:00Z",
                    }
                },
            },
        ),
        patch("plesk_unified.server._save_source_state"),
        # Mock AIClient for summary generation
        patch("plesk_unified.server.AIClient", new_callable=MagicMock),
    ):
        # Configure mock_embed_model to return a mock vector
        mock_embed_model.return_value.compute_query_embeddings.return_value = [
            [0.1] * 384
        ]

        # Configure mock_get_table
        mock_table = MagicMock()
        search_mock = (
            mock_table.search.return_value.where.return_value.limit.return_value
        )
        search_mock.to_list.return_value = []
        mock_table.create_fts_index.return_value = None
        mock_table.delete.return_value = None
        mock_get_table.return_value = mock_table

        # Configure mock_get_profile
        mock_profile = MagicMock()
        mock_profile.name = "test_profile"
        mock_profile.embed_model = "test_model"
        mock_profile.reranker_enabled = False  # Disable reranker by default
        mock_profile.use_turboquant = False  # Disable tq by default
        mock_get_profile.return_value = mock_profile

        # Clear any cached model instances
        server._embedding_model = None
        server._reranker = None
        server._tq_index = None
        server._active_profile = None
        server._detected_device = None
        server._warmup_state = "idle"
        server._warmup_error = None
        server._warmup_thread = None

        yield {
            "mock_embed_model": mock_embed_model,
            "mock_get_table": mock_get_table,
            "mock_reranker": mock_reranker,
            "mock_tq_index": mock_tq_index,
        }


# List of tool handlers to inspect
TOOL_HANDLERS = [
    server.warmup_server,
    server.daemon_health,
    server.list_model_profiles,
    server.refresh_knowledge,
    server.trigger_index_sync,
    server.check_sync_status,
    server.requantize_knowledge,
    server.search_plesk_unified,
]


@pytest.mark.asyncio
async def test_all_tool_handlers_are_async_functions():
    """Assert all 8 identified tool handlers are async def functions."""
    for handler in TOOL_HANDLERS:
        assert inspect.iscoroutinefunction(handler), (
            f"Tool handler {handler.__name__} is not an async function. "
            "Please ensure it is defined with `async def`."
        )


@pytest.mark.asyncio
async def test_concurrent_calls_via_asyncio_gather_complete_without_deadlock(
    mock_all_ml_and_io_calls,
):
    """
    Test that 3 concurrent calls to search_plesk_unified and refresh_knowledge
    via asyncio.gather complete without deadlock.
    """

    async def mock_search_task():
        return await server.search_plesk_unified(query="test query")

    async def mock_refresh_task():
        return await server.refresh_knowledge(target_category="cli")

    tasks = [
        mock_search_task(),
        mock_refresh_task(),
        mock_search_task(),
    ]

    try:
        results = await asyncio.gather(*tasks, return_exceptions=False)
        assert len(results) == 3
        assert isinstance(results[0], str)
        assert isinstance(results[1], str)
        assert isinstance(results[2], str)

        assert "I could not find a reliable answer." in results[0]
        assert "SKIPPED cli" in results[1]

        assert mock_all_ml_and_io_calls["mock_get_table"].called

    except Exception as e:
        pytest.fail(f"Concurrent calls failed or deadlocked: {e}")
