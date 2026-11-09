import pytest
from unittest.mock import AsyncMock, MagicMock
import concurrent.futures

# New imports from the service-based architecture
from fastmcp import Context
from mcp_plesk_dev_docs.application.services.container import AppContainer
from mcp_plesk_dev_docs.settings import PleskSettings as Settings
from mcp_plesk_dev_docs.application.services.search_service import SearchService

# New tool import
from mcp_plesk_dev_docs.server.tools.search_tools import search_mcp_plesk_dev_docs
from mcp.types import TextContent


def markdown_text(result) -> str:
    """Return the markdown text block of a search ToolResult."""
    return "\n".join(
        block.text for block in result.content if isinstance(block, TextContent)
    )


# Helper to simulate executor submission
def sync_submit(fn, *args, **kwargs):
    f = concurrent.futures.Future()
    f.set_result(fn(*args, **kwargs))
    return f


@pytest.fixture
async def mock_search_sampling_dependencies():
    mock_container = MagicMock(spec=AppContainer)
    mock_ctx = MagicMock(spec=Context)
    mock_ctx.sample = AsyncMock()
    mock_ctx.report_progress = AsyncMock()

    # Configure mock_ctx to provide mock_container
    mock_ctx.request_context.lifespan_context = {"container": mock_container}

    # --- Mock settings ---
    mock_container.settings = MagicMock(spec=Settings)
    mock_container.settings.plesk_model_profile = "pro"
    # Deprecated server-wide flag; synthesis is opt-in per call.
    mock_container.settings.plesk_enable_sampling = False
    mock_container.settings.plesk_rerank_candidates = 50
    mock_container.settings.plesk_min_relevance_threshold = None

    # --- Mock executor ---
    mock_container.executor = MagicMock(spec=concurrent.futures.ThreadPoolExecutor)
    mock_container.executor.submit.side_effect = sync_submit

    # --- Mock logger ---
    mock_container.logger = MagicMock()

    # --- Mock ModelRuntime ---
    mock_container.model_runtime = MagicMock()
    mock_profile = MagicMock()
    mock_profile.name = "pro"
    mock_profile.use_turboquant = False
    mock_profile.tq_top_k = 25
    mock_container.model_runtime.get_profile.return_value = mock_profile
    mock_container.model_runtime.get_embedding_model.return_value = MagicMock()

    # --- Use REAL SearchService but mock its internal components ---
    search_service = SearchService(
        settings=mock_container.settings,
        model_runtime=mock_container.model_runtime,
        storage_runtime=MagicMock(),
        lancedb_repo=MagicMock(),
        search_formatter=MagicMock(),
        executor=mock_container.executor,
    )
    # Mock internal methods that perform heavy lifting
    search_service._get_search_candidates = MagicMock()
    search_service._rerank_and_score = MagicMock()
    search_service._deduplicate_by_filename = MagicMock(
        side_effect=lambda x, *args, **kwargs: x
    )
    search_service._apply_relevance_gate = MagicMock(return_value=None)
    search_service._expand_context_with_neighbors = MagicMock(side_effect=lambda x: x)
    search_service.search_formatter.format_markdown.return_value = (
        "Formatted results containing file1.html."
    )

    mock_container.search_service = search_service

    yield mock_ctx, mock_container


@pytest.mark.asyncio
async def test_search_mcp_plesk_dev_docs_synthesize_opt_in(
    mock_search_sampling_dependencies,
):
    """Verify ctx.sample runs only when the caller passes synthesize=True."""
    mock_ctx, mock_container = mock_search_sampling_dependencies

    # Mock sampling result
    mock_sample_result = MagicMock()
    mock_sample_result.text = "Synthesized answer from LLM"
    mock_ctx.sample.return_value = mock_sample_result

    # Mock SearchService internal methods to provide search results
    mock_results = [
        {
            "text": "Chunk 1 content",
            "filename": "file1.html",
            "_relevance": 0.9,
            "category": "guide",
            "title": "Introduction",
            "breadcrumb": "Docs > Intro",
        }
    ]
    mock_container.search_service._get_search_candidates.return_value = mock_results
    mock_container.search_service._rerank_and_score.return_value = (
        mock_results  # Assume reranking doesn't change order
    )

    result = await search_mcp_plesk_dev_docs(
        ctx=mock_ctx, query="how to create a domain", synthesize=True
    )
    text = markdown_text(result)

    mock_ctx.sample.assert_called_once()
    assert "Synthesized Answer" in text
    assert "Synthesized answer from LLM" in text
    assert "file1.html" in text
    assert mock_container.search_service.search_formatter.format_markdown.called


@pytest.mark.asyncio
async def test_search_mcp_plesk_dev_docs_synthesize_disabled_by_default(
    mock_search_sampling_dependencies,
):
    """Verify synthesis is not called unless the caller opts in per call."""
    mock_ctx, mock_container = mock_search_sampling_dependencies

    # The deprecated server-wide flag must not force a sampling round-trip.
    mock_container.settings.plesk_enable_sampling = True

    # Mock SearchService internal methods to provide search results
    mock_results = [
        {
            "text": "Chunk 1 content",
            "filename": "file1.html",
            "_relevance": 0.9,
            "category": "guide",
            "title": "Introduction",
            "breadcrumb": "Docs > Intro",
        }
    ]
    mock_container.search_service._get_search_candidates.return_value = mock_results
    mock_container.search_service._rerank_and_score.return_value = mock_results

    result = await search_mcp_plesk_dev_docs(
        ctx=mock_ctx, query="how to create a domain"
    )
    text = markdown_text(result)

    mock_ctx.sample.assert_not_called()
    assert "Synthesized Answer" not in text
    assert "file1.html" in text
    assert mock_container.search_service.search_formatter.format_markdown.called


@pytest.mark.asyncio
async def test_search_mcp_plesk_dev_docs_no_results_no_sampling(
    mock_search_sampling_dependencies,
):
    """Verify synthesis is skipped if there are no search results."""
    mock_ctx, mock_container = mock_search_sampling_dependencies

    # Mock SearchService internal methods to return no search results
    mock_container.search_service._get_search_candidates.return_value = []
    mock_container.search_service._rerank_and_score.return_value = []
    mock_container.search_service._apply_relevance_gate.return_value = (
        "I could not find a reliable answer."
    )

    result = await search_mcp_plesk_dev_docs(
        ctx=mock_ctx, query="nonexistent", synthesize=True
    )
    text = markdown_text(result)

    mock_ctx.sample.assert_not_called()
    assert "I could not find a reliable answer." in text


@pytest.mark.asyncio
async def test_search_mcp_plesk_dev_docs_sampling_failure_graceful(
    mock_search_sampling_dependencies,
):
    """Verify synthesize=True still returns results when sampling fails."""
    mock_ctx, mock_container = mock_search_sampling_dependencies

    mock_ctx.sample.side_effect = Exception("Sampling API error")

    # Mock SearchService internal methods to provide search results
    mock_results = [
        {
            "text": "Chunk 1 content",
            "filename": "file1.html",
            "_relevance": 0.9,
            "category": "guide",
            "title": "Introduction",
            "breadcrumb": "Docs > Intro",
        }
    ]
    mock_container.search_service._get_search_candidates.return_value = mock_results
    mock_container.search_service._rerank_and_score.return_value = mock_results

    result = await search_mcp_plesk_dev_docs(
        ctx=mock_ctx, query="test query", synthesize=True
    )
    text = markdown_text(result)

    mock_ctx.sample.assert_called_once()
    assert "Synthesized Answer" not in text  # Because sampling failed
    assert "file1.html" in text
    assert mock_container.search_service.search_formatter.format_markdown.called
