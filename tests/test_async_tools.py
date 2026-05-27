import pytest
import inspect
import asyncio
from unittest.mock import MagicMock, AsyncMock
import concurrent.futures

# New imports from the service-based architecture
from fastmcp import Context
from mcp_plesk_dev_docs.application.services.container import AppContainer
from mcp_plesk_dev_docs.settings import PleskSettings as Settings
import mcp_plesk_dev_docs.infrastructure.parsers.chunking

# New tool imports
from mcp_plesk_dev_docs.server.tools.search_tools import search_mcp_plesk_dev_docs
from mcp_plesk_dev_docs.server.tools.admin_tools import (
    warmup_server,
    daemon_health,
    list_model_profiles,
)
from mcp_plesk_dev_docs.server.tools.indexing_tools import (
    refresh_knowledge,
    trigger_index_sync,
    check_sync_status,
    requantize_knowledge,
)


# Helper to simulate executor submission by calling the function immediately
def sync_submit(fn, *args, **kwargs):
    f = concurrent.futures.Future()
    try:
        f.set_result(fn(*args, **kwargs))
    except Exception as e:
        f.set_exception(e)
    return f


@pytest.fixture(autouse=True)
async def mock_all_ml_and_io_calls():
    """
    Mock all ML model calls and I/O operations for fast, isolated tests.
    This fixture provides a mock Context and AppContainer.
    """
    mock_container = MagicMock(spec=AppContainer)
    mock_ctx = MagicMock(spec=Context)
    mock_ctx.sample = AsyncMock()
    mock_ctx.report_progress = AsyncMock()

    # Configure mock_ctx to provide mock_container
    mock_ctx.request_context.lifespan_context = {"container": mock_container}

    # --- Mock settings ---
    mock_container.settings = MagicMock(spec=Settings)
    mock_container.settings.plesk_model_profile = "test_profile"
    mock_container.settings.plesk_enable_sampling = (
        True  # Assume sampling is enabled for search
    )
    mock_container.settings.plesk_rerank_candidates = 50
    mock_container.settings.plesk_min_relevance_threshold = None

    # --- Mock executor ---
    mock_container.executor = MagicMock(spec=concurrent.futures.ThreadPoolExecutor)
    mock_container.executor.submit.side_effect = sync_submit

    # --- Mock logger ---
    mock_container.logger = MagicMock()

    # --- Mock LanceDbRepository and its table ---
    mock_container.lancedb_repo = MagicMock()
    mock_table = MagicMock()
    search_mock = mock_table.search.return_value.where.return_value.limit.return_value
    search_mock.to_list.return_value = []  # Default: no search results
    mock_table.create_fts_index.return_value = None
    mock_table.delete.return_value = None
    mock_container.lancedb_repo.get_table.return_value = mock_table

    # --- Mock TurboQuantRepository ---
    mock_container.turboquant_repo = MagicMock()
    mock_container.turboquant_repo.get_tq_index.return_value = None

    # --- Mock SourceStateRepository ---
    mock_container.source_state_repo = MagicMock()
    mock_container.source_state_repo.load.return_value = {
        "version": 1,
        "sources": {
            "cli": {
                # Matching fingerprint and chunk_version for "cli" category
                "fingerprint": "mock_fingerprint",
                "chunk_version": (
                    mcp_plesk_dev_docs.infrastructure.parsers.chunking.CHUNK_VERSION
                ),
                "file_count": 1,
                "indexed_at": "2023-01-01T00:00:00Z",
            }
        },
    }
    mock_container.source_state_repo.save.return_value = None

    # --- Mock SourceCatalog (sources) ---
    mock_container.sources = MagicMock()
    mock_container.sources.ensure_source_exists.return_value = True
    mock_container.sources.compute_source_fingerprint.return_value = (
        "mock_fingerprint",
        1,
    )
    mock_container.sources.by_category.return_value = MagicMock()
    mock_container.sources.by_category.return_value.zip_url = (
        "http://example.com/zip/cli.zip"
    )
    mock_container.sources.by_category.return_value.build_doc_url.return_value = (
        "http://example.com/cli/file.html"
    )

    # --- Mock ModelRuntime ---
    mock_container.model_runtime = MagicMock()
    mock_profile = MagicMock()
    mock_profile.name = "test_profile"
    mock_profile.embed_model = "test_model"
    mock_profile.reranker_enabled = False
    mock_profile.use_turboquant = False
    mock_container.model_runtime.get_profile.return_value = mock_profile
    mock_container.model_runtime.get_embedding_model.return_value = MagicMock()
    model_mock = mock_container.model_runtime.get_embedding_model.return_value
    model_mock.compute_query_embeddings.return_value = [[0.1] * 384]
    mock_container.model_runtime.get_reranker.return_value = (
        MagicMock()
    )  # Assume reranker is always present

    # --- Mock SearchService ---
    mock_container.search_service = MagicMock()
    mock_container.search_service.search = AsyncMock()
    mock_container.search_service.search_formatter = MagicMock()
    mock_container.search_service.search_formatter.format_markdown.side_effect = (
        lambda x: f"Formatted: {x[0]['text']}" if x else ""
    )
    mock_container.search_service.search.return_value = (
        [{"text": "Search result from mocked service.", "filename": "doc.htm"}],
        None,
    )

    # --- Mock IndexingService ---
    mock_container.indexing_service = MagicMock()
    mock_container.indexing_service.refresh_knowledge = AsyncMock()
    # refresh_knowledge result for "cli" should return SKIPPED
    mock_container.indexing_service.refresh_knowledge.return_value = "SKIPPED cli"

    # --- Mock WarmupService ---
    mock_container.warmup_service = MagicMock()
    mock_container.warmup_service.warmup_state = "idle"
    mock_container.warmup_service.warmup_error = None
    mock_container.warmup_service.run_warmup_sequence.return_value = [
        "Mock Warmup complete."
    ]

    # --- Mock HealthService ---
    mock_container.health_service = MagicMock()
    mock_container.health_service.get_health_report.return_value = {
        "warmup_state": "idle",
        "warmup_error": None,
    }

    # --- Mock JobService (holds JobRegistry) ---
    mock_job_registry = MagicMock()  # JobRegistry for concurrent tasks
    mock_job_registry.submit_job.side_effect = lambda f, *args, **kwargs: "mock_job_id"
    mock_job_registry.get_status.return_value = {
        "status": "completed"
    }  # Default completed
    mock_container.job_service = MagicMock()
    mock_container.job_service.job_registry = mock_job_registry

    # Mock AIClient for summary generation
    mock_container.ai_client = MagicMock()

    yield mock_ctx


# List of tool handlers to inspect
TOOL_HANDLERS = [
    warmup_server,
    daemon_health,
    list_model_profiles,
    refresh_knowledge,
    trigger_index_sync,
    check_sync_status,
    requantize_knowledge,
    search_mcp_plesk_dev_docs,
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
    mock_all_ml_and_io_calls: AsyncMock,  # Type hint for clarity
):
    """
    Test that 3 concurrent calls to search_mcp_plesk_dev_docs and refresh_knowledge
    via asyncio.gather complete without deadlock.
    """
    mock_ctx = mock_all_ml_and_io_calls
    # Use SearchService mock from fixture
    search_service_mock = mock_ctx.request_context.lifespan_context[
        "container"
    ].search_service
    search_service_mock.search.return_value = (
        [
            {
                "filename": "doc.htm",
                "text": "result content",
                "category": "guide",
                "_relevance": 0.9,
            }
        ],
        None,
    )
    # Indexing service already configured to return "SKIPPED cli"

    async def mock_search_task():
        return await search_mcp_plesk_dev_docs(mock_ctx, query="test query")

    async def mock_refresh_task():
        return await refresh_knowledge(mock_ctx, category="cli")

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

        assert "result content" in results[0]
        assert "SKIPPED cli" in results[1]
        assert "result content" in results[2]

        # Verify that underlying services were called
        search_service_mock.search.assert_called()
        mock_ctx.request_context.lifespan_context[
            "container"
        ].indexing_service.refresh_knowledge.assert_called_with(
            progress_callback=mock_ctx.report_progress, category="cli", reset_db=False
        )

    except Exception as e:
        pytest.fail(f"Concurrent calls failed or deadlocked: {e}")
