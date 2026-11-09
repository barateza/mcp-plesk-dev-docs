import asyncio
import concurrent.futures
import inspect
import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

# New imports from the service-based architecture
from fastmcp import Context
from mcp_plesk_dev_docs.application.services.container import AppContainer
from mcp_plesk_dev_docs.settings import PleskSettings as Settings
from mcp_plesk_dev_docs.application.services.search_service import SearchService
from mcp_plesk_dev_docs.domain.models import CategoryEnum
from mcp_plesk_dev_docs.formatting.search_formatter import DEFAULT_SNIPPET_CHARS
import mcp_plesk_dev_docs.infrastructure.parsers.chunking

# New tool imports
from mcp_plesk_dev_docs.server.tools.search_tools import (
    SearchTools,
    search_mcp_plesk_dev_docs,
)
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


from mcp.types import TextContent


def markdown_text(result) -> str:
    """Return the markdown text block of a search ToolResult."""
    return "\n".join(
        block.text for block in result.content if isinstance(block, TextContent)
    )


def search_service_of(mock_ctx):
    """Return the mocked SearchService behind the mock context."""
    return mock_ctx.request_context.lifespan_context["container"].search_service


def _search_results(count: int, body: str = "Paragraph body. ") -> list:
    return [
        {
            "filename": f"doc{i}.htm",
            "text": f"Chunk {i}. {body}",
            "category": "guide",
            "title": f"Title {i}",
            "_relevance": 0.9 - i * 0.01,
            "chunk_id": i,
        }
        for i in range(count)
    ]


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
    # Synthesis is opt-in per call; the deprecated server-wide flag stays off.
    mock_container.settings.plesk_enable_sampling = False
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
        assert isinstance(results[1], str)

        assert "result content" in markdown_text(results[0])
        assert "SKIPPED cli" in results[1]
        assert "result content" in markdown_text(results[2])

        # Verify that underlying services were called
        search_service_mock.search.assert_called()
        mock_ctx.request_context.lifespan_context[
            "container"
        ].indexing_service.refresh_knowledge.assert_called_with(
            progress_callback=mock_ctx.report_progress, category="cli", reset_db=False
        )

    except Exception as e:
        pytest.fail(f"Concurrent calls failed or deadlocked: {e}")


@pytest.mark.asyncio
async def test_search_limit_defaults_to_five(mock_all_ml_and_io_calls):
    """The default call caps the payload at five deduplicated results."""
    mock_ctx = mock_all_ml_and_io_calls
    search_service = search_service_of(mock_ctx)
    search_service.search.return_value = (_search_results(9), None)

    result = await search_mcp_plesk_dev_docs(mock_ctx, query="q")

    formatted = search_service.search_formatter.format_markdown.call_args[0][0]
    assert len(formatted) == 5
    assert len(result.structured_content["results"]) == 5


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("requested", "expected"),
    [(0, 1), (-4, 1), (1, 1), (5, 5), (10, 10), (99, 10)],
)
async def test_search_limit_is_clamped(mock_all_ml_and_io_calls, requested, expected):
    """Out-of-range limits are clamped into the documented 1..10 window."""
    mock_ctx = mock_all_ml_and_io_calls
    search_service = search_service_of(mock_ctx)
    search_service.search.return_value = (_search_results(20), None)

    result = await search_mcp_plesk_dev_docs(mock_ctx, query="q", limit=requested)

    formatted = search_service.search_formatter.format_markdown.call_args[0][0]
    assert len(formatted) == expected
    assert len(result.structured_content["results"]) == expected


@pytest.mark.asyncio
async def test_search_returns_structured_results(mock_all_ml_and_io_calls):
    """Every documented field is present in structuredContent."""
    mock_ctx = mock_all_ml_and_io_calls
    search_service = search_service_of(mock_ctx)
    search_service.search.return_value = (_search_results(3), None)
    search_service.search_formatter.source_catalog.by_category.return_value = None

    result = await search_mcp_plesk_dev_docs(mock_ctx, query="q", limit=3)

    rows = result.structured_content["results"]
    assert [row["filename"] for row in rows] == [
        "doc0.htm",
        "doc1.htm",
        "doc2.htm",
    ]
    assert rows[0]["category"] == "guide"
    assert rows[0]["title"] == "Title 0"
    assert rows[0]["chunk_id"] == 0
    assert rows[0]["url"] is None
    assert rows[0]["score"] == pytest.approx(0.9)
    assert rows[0]["snippet"].startswith("Chunk 0.")
    # Synthesis is opt-in per call (issue #88): the field is present and null
    # unless the caller passes synthesize=True.
    assert result.structured_content["synthesized"] is None
    assert result.is_error is False
    assert "Chunk 0." in markdown_text(result)


@pytest.mark.asyncio
async def test_search_snippet_is_truncated_per_result(mock_all_ml_and_io_calls):
    """The structured snippet honours the ~800 character budget."""
    mock_ctx = mock_all_ml_and_io_calls
    search_service = search_service_of(mock_ctx)
    search_service.search.return_value = (
        _search_results(1, body="Sentence body. " * 300),
        None,
    )

    result = await search_mcp_plesk_dev_docs(mock_ctx, query="q", limit=1)

    snippet = result.structured_content["results"][0]["snippet"]
    assert len(snippet) <= 800
    assert snippet.endswith("…")


# ---------------------------------------------------------------------------
# FTS-only references (issue #95) and projected get_file_content (issue #96)
# ---------------------------------------------------------------------------


@pytest.fixture
def build_search_service():
    """Return a factory for a real SearchService with a mocked repository.

    The tests below exercise the real service logic (executor hop, FTS
    filtering, text assembly) instead of the MagicMock the shared fixture wires
    into the container, which would leave the code under test unexecuted.
    """
    services = []

    def _build(repo):
        settings = MagicMock(spec=Settings)
        settings.plesk_enable_fts = True
        settings.plesk_query_cache_enabled = False
        settings.plesk_query_cache_size = 8
        settings.plesk_rerank_candidates = 50
        settings.plesk_min_relevance_threshold = None

        model_runtime = MagicMock()
        model_runtime.get_reranker.return_value = MagicMock()

        executor = MagicMock(spec=concurrent.futures.ThreadPoolExecutor)
        executor.submit.side_effect = sync_submit

        service = SearchService(
            settings, model_runtime, MagicMock(), repo, MagicMock(), executor
        )
        services.append(service)
        return service, model_runtime

    yield _build

    for service in services:
        service.shutdown()


def _file_content_query(table):
    """Return the terminal `.to_list()` mock of the projected query chain."""
    where = table.search.return_value.where.return_value
    return where.select.return_value.limit.return_value


@pytest.mark.asyncio
async def test_resolve_references_never_touches_the_vector_path(build_search_service):
    """#95: resolve_references is FTS-only — no vector leg, no reranker."""
    repo = MagicMock()
    repo.search_fts.return_value = [
        {"filename": "ApiCli.php", "chunk_id": 3, "text": "Wraps pm_ApiCli."},
        {"filename": "guide.htm", "chunk_id": 7, "text": "Mentions pm_ApiCli."},
    ]
    service, model_runtime = build_search_service(repo)
    service._get_vector_candidates = MagicMock()

    text = await SearchTools(service).resolve_references(
        "pm_ApiCli", CategoryEnum.PHP_STUBS
    )

    repo.search_fts.assert_called_once_with(
        "pm_ApiCli", limit=10, filter_expr="category = 'php-stubs'"
    )
    service._get_vector_candidates.assert_not_called()
    repo.search_vector.assert_not_called()
    repo.get_neighbors.assert_not_called()
    model_runtime.get_reranker.assert_not_called()
    assert text.index("ApiCli.php") < text.index("guide.htm")
    assert "**`ApiCli.php`** (chunk 3)" in text


@pytest.mark.asyncio
async def test_resolve_references_keeps_fts_order_and_bounds_each_hit(
    build_search_service,
):
    """#95: FTS order is preserved and every hit is one bounded line."""
    long_text = "Sentence mentioning pm_ApiCli. " * 200
    repo = MagicMock()
    repo.search_fts.return_value = [
        {"filename": "b.htm", "chunk_id": 2, "text": long_text},
        {"filename": "b.htm", "chunk_id": 2, "text": long_text},  # duplicate row
        {"filename": "a.htm", "chunk_id": 1, "text": "short"},
    ]
    service, _ = build_search_service(repo)

    text = await SearchTools(service).resolve_references(
        "pm_ApiCli", CategoryEnum.GUIDE
    )

    hits = [line for line in text.splitlines() if line.startswith("- ")]
    assert [line.split("**")[1] for line in hits] == ["`b.htm`", "`a.htm`"]
    for line in hits:
        snippet = line.split(": ", 1)[1]
        assert "\n" not in snippet
        assert len(snippet) <= DEFAULT_SNIPPET_CHARS
    assert len(text) < 2 * DEFAULT_SNIPPET_CHARS + 200


@pytest.mark.asyncio
async def test_resolve_references_reports_an_empty_fts_set_without_fallback(
    build_search_service,
):
    """#95: an empty FTS set is reported, never answered from the vector leg."""
    repo = MagicMock()
    repo.search_fts.return_value = []
    service, model_runtime = build_search_service(repo)
    service._get_vector_candidates = MagicMock()

    text = await SearchTools(service).resolve_references("nope", CategoryEnum.GUIDE)

    assert text == "No references found for 'nope' in guide."
    service._get_vector_candidates.assert_not_called()
    repo.search_vector.assert_not_called()
    model_runtime.get_reranker.assert_not_called()


@pytest.mark.asyncio
async def test_search_fts_only_returns_raw_rows_in_order(build_search_service):
    """#95: the service returns raw FTS rows, in FTS order, without the pipeline."""
    repo = MagicMock()
    repo.search_fts.return_value = [
        {"filename": "b.htm", "chunk_id": 1, "_score": 0.9},
        {"filename": "a.htm", "chunk_id": 2, "_score": 0.5},
    ]
    service, model_runtime = build_search_service(repo)
    service._get_vector_candidates = MagicMock()

    rows = await service.search_fts_only("symbol", category="api", limit=3)

    assert [row["filename"] for row in rows] == ["b.htm", "a.htm"]
    repo.search_fts.assert_called_once_with(
        "symbol", limit=3, filter_expr="category = 'api'"
    )
    repo.search_vector.assert_not_called()
    repo.get_neighbors.assert_not_called()
    service._get_vector_candidates.assert_not_called()
    model_runtime.get_reranker.assert_not_called()


@pytest.mark.asyncio
async def test_search_fts_only_blank_query_skips_the_repository(build_search_service):
    repo = MagicMock()
    service, _ = build_search_service(repo)

    assert await service.search_fts_only("   ", category="api") == []
    repo.search_fts.assert_not_called()


@pytest.mark.asyncio
async def test_get_file_content_uses_a_vectorless_projected_query(
    build_search_service,
):
    """#96: filter-only query and a projection without the vector column."""
    table = MagicMock()
    _file_content_query(table).to_list.return_value = [
        {"text": "Second chunk.", "chunk_id": 1, "filename": "doc.htm"},
        {"text": "First chunk.", "chunk_id": 0, "filename": "doc.htm"},
    ]
    repo = MagicMock()
    repo.get_table.return_value = table
    service, _ = build_search_service(repo)

    text = await SearchTools(service).get_file_content("doc.htm", CategoryEnum.CLI)

    table.search.assert_called_once_with(None)
    table.search.return_value.where.assert_called_once_with(
        "filename = 'doc.htm' AND category = 'cli'"
    )
    where = table.search.return_value.where.return_value
    where.select.assert_called_once_with(["text", "chunk_id", "filename"])
    where.select.return_value.limit.assert_called_once_with(1000)
    assert text == "First chunk.\n\nSecond chunk."


@pytest.mark.asyncio
async def test_get_file_content_missing_file_message_is_unchanged(
    build_search_service,
):
    table = MagicMock()
    _file_content_query(table).to_list.return_value = []
    repo = MagicMock()
    repo.get_table.return_value = table
    service, _ = build_search_service(repo)

    text = await SearchTools(service).get_file_content("gone.htm", CategoryEnum.GUIDE)

    assert text == "File 'gone.htm' not found in category 'guide'."


@pytest.mark.asyncio
async def test_get_file_content_warns_and_flags_truncation(
    build_search_service, caplog
):
    """#96: hitting the chunk cap warns in the log and in the returned text."""
    caplog.set_level(logging.WARNING, logger="mcp_plesk_dev_docs")
    table = MagicMock()
    _file_content_query(table).to_list.return_value = [
        {"text": f"chunk {i}", "chunk_id": i, "filename": "big.htm"}
        for i in range(1000)
    ]
    repo = MagicMock()
    repo.get_table.return_value = table
    service, _ = build_search_service(repo)

    text = await SearchTools(service).get_file_content("big.htm", CategoryEnum.GUIDE)

    assert "[TRUNCATED]" in text
    assert "only the first 1000" in text
    warnings = [
        record.getMessage()
        for record in caplog.records
        if record.levelno == logging.WARNING and "truncated" in record.getMessage()
    ]
    assert len(warnings) == 1
    assert "big.htm" in warnings[0]
    assert "guide" in warnings[0]
    assert "1000" in warnings[0]
