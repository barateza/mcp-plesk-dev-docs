import pytest
from unittest.mock import AsyncMock, MagicMock
import concurrent.futures

# New imports from the service-based architecture
from fastmcp import Context
from plesk_unified.application.services.container import AppContainer
from plesk_unified.settings import PleskSettings as Settings
from plesk_unified.application.services.search_service import SearchService

# New tool import
from plesk_unified.server.tools.search_tools import search_plesk_unified


# Helper to create a completed Future
def make_completed_future(result_value):
    f = concurrent.futures.Future()
    f.set_result(result_value)
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
    mock_container.settings.plesk_model_profile = "full-tq"
    mock_container.settings.plesk_enable_sampling = False  # Default to disabled
    mock_container.settings.plesk_rerank_candidates = 50
    mock_container.settings.plesk_min_relevance_threshold = None

    # --- Mock executor (needed by SearchService indirectly) ---
    mock_container.executor = MagicMock(spec=concurrent.futures.ThreadPoolExecutor)
    mock_container.executor.submit.side_effect = make_completed_future

    # --- Mock logger ---
    mock_container.logger = MagicMock()

    # --- Mock ModelRuntime ---
    mock_container.model_runtime = MagicMock()
    mock_profile = MagicMock()
    mock_profile.name = "full-tq"
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
        turboquant_repo=MagicMock(),
        search_formatter=MagicMock(),
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
async def test_search_plesk_unified_sampling_enabled(mock_search_sampling_dependencies):
    """Verify search_plesk_unified calls ctx.sample when sampling is enabled."""
    mock_ctx, mock_container = mock_search_sampling_dependencies

    # Configure settings to enable sampling
    mock_container.settings.plesk_enable_sampling = True

    # Mock sampling result
    mock_sample_result = MagicMock()
    mock_sample_result.content = MagicMock()
    mock_sample_result.content.text = "Synthesized answer from LLM"
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

    result = await search_plesk_unified(ctx=mock_ctx, query="how to create a domain")

    mock_ctx.sample.assert_called_once()
    assert "Synthesized Answer" in result
    assert "Synthesized answer from LLM" in result
    assert "file1.html" in result
    assert mock_container.search_service.search_formatter.format_markdown.called


@pytest.mark.asyncio
async def test_search_plesk_unified_sampling_disabled(
    mock_search_sampling_dependencies,
):
    """Verify sampling is NOT called when disabled."""
    mock_ctx, mock_container = mock_search_sampling_dependencies

    # Configure settings to disable sampling (default, but explicit for clarity)
    mock_container.settings.plesk_enable_sampling = False

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

    result = await search_plesk_unified(ctx=mock_ctx, query="how to create a domain")

    mock_ctx.sample.assert_not_called()
    assert "Synthesized Answer" not in result
    assert "file1.html" in result
    assert mock_container.search_service.search_formatter.format_markdown.called


@pytest.mark.asyncio
async def test_search_plesk_unified_no_results_no_sampling(
    mock_search_sampling_dependencies,
):
    """Verify sampling is skipped if there are no search results."""
    mock_ctx, mock_container = mock_search_sampling_dependencies

    # Configure settings to enable sampling
    mock_container.settings.plesk_enable_sampling = True

    # Mock SearchService internal methods to return no search results
    mock_container.search_service._get_search_candidates.return_value = []
    mock_container.search_service._rerank_and_score.return_value = []
    mock_container.search_service._apply_relevance_gate.return_value = (
        "I could not find a reliable answer."
    )

    result = await search_plesk_unified(ctx=mock_ctx, query="nonexistent")

    mock_ctx.sample.assert_not_called()
    assert "I could not find a reliable answer." in result


@pytest.mark.asyncio
async def test_search_plesk_unified_sampling_failure_graceful(
    mock_search_sampling_dependencies,
):
    """Verify search_plesk_unified returns results even if sampling fails."""
    mock_ctx, mock_container = mock_search_sampling_dependencies

    # Configure settings to enable sampling
    mock_container.settings.plesk_enable_sampling = True

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

    result = await search_plesk_unified(ctx=mock_ctx, query="test query")

    mock_ctx.sample.assert_called_once()
    assert "Synthesized Answer" not in result  # Because sampling failed
    assert "file1.html" in result
    assert mock_container.search_service.search_formatter.format_markdown.called
