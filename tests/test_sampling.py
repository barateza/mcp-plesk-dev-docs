import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import concurrent.futures
from plesk_unified.server import search_plesk_unified
from plesk_unified.settings import settings


# Helper to create a completed Future
def make_completed_future(result_value):
    f = concurrent.futures.Future()
    f.set_result(result_value)
    return f


# Fixture copied from test_server.py to maintain consistency
@pytest.fixture
def mock_server_dependencies():
    import plesk_unified.server as server

    server._embedding_model = None
    server._warmup_state = "idle"
    server._warmup_thread = None
    server._warmup_error = None
    server._tq_index = None
    server._detected_device = None

    mock_server_executor = MagicMock(spec=concurrent.futures.ThreadPoolExecutor)

    def mock_submit_side_effect(func, *args, **kwargs):
        return make_completed_future(func(*args, **kwargs))

    mock_server_executor.submit.side_effect = mock_submit_side_effect

    with (
        patch("plesk_unified.server._executor", new=mock_server_executor),
        patch("plesk_unified.server.get_table"),
        patch("plesk_unified.server.get_reranker"),
        patch("plesk_unified.server.get_tq_index"),
        patch("plesk_unified.server._get_profile") as mock_get_profile,
        patch("plesk_unified.server._build_doc_url"),
    ):
        mock_profile = MagicMock()
        mock_profile.name = "full-tq"
        mock_profile.use_turboquant = False
        mock_get_profile.return_value = mock_profile
        yield


@pytest.mark.asyncio
async def test_search_plesk_unified_sampling_enabled(mock_server_dependencies):
    """Verify search_plesk_unified calls ctx.sample when sampling is enabled."""
    ctx = AsyncMock()
    # Mock sampling result
    mock_sample_result = MagicMock()
    # In server.py: if hasattr(sample_result.content, "text"):
    # answer = sample_result.content.text
    # But sample_result.content is often the result of ctx.sample.
    # The server.py code says:
    # sample_result = await ctx.sample(...)
    # if sample_result and sample_result.content:
    #     if hasattr(sample_result.content, "text"):
    #         answer = sample_result.content.text

    mock_sample_result.content = MagicMock()
    mock_sample_result.content.text = "Synthesized answer from LLM"
    ctx.sample.return_value = mock_sample_result

    # Mock search results to trigger sampling logic
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

    with (
        patch.object(settings, "plesk_enable_sampling", True),
        patch("plesk_unified.server._get_search_candidates", return_value=mock_results),
        patch("plesk_unified.server._rerank_and_score", side_effect=lambda q, c, r: c),
    ):
        result = await search_plesk_unified(ctx=ctx, query="how to create a domain")

        assert ctx.sample.called
        assert "Synthesized Answer" in result
        assert "Synthesized answer from LLM" in result
        assert "file1.html" in result


@pytest.mark.asyncio
async def test_search_plesk_unified_sampling_disabled(mock_server_dependencies):
    """Verify sampling is NOT called when disabled."""
    ctx = AsyncMock()

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

    with (
        patch.object(settings, "plesk_enable_sampling", False),
        patch("plesk_unified.server._get_search_candidates", return_value=mock_results),
        patch("plesk_unified.server._rerank_and_score", side_effect=lambda q, c, r: c),
    ):
        result = await search_plesk_unified(ctx=ctx, query="how to create a domain")

        assert not ctx.sample.called
        assert "Synthesized Answer" not in result
        assert "file1.html" in result


@pytest.mark.asyncio
async def test_search_plesk_unified_no_results_no_sampling(mock_server_dependencies):
    """Verify sampling is skipped if there are no search results."""
    ctx = AsyncMock()

    with (
        patch.object(settings, "plesk_enable_sampling", True),
        patch("plesk_unified.server._get_search_candidates", return_value=[]),
    ):
        result = await search_plesk_unified(ctx=ctx, query="nonexistent")

        assert not ctx.sample.called
        assert "I could not find a reliable answer." in result


@pytest.mark.asyncio
async def test_search_plesk_unified_sampling_failure_graceful(mock_server_dependencies):
    """Verify search_plesk_unified returns results even if sampling fails."""
    ctx = AsyncMock()
    ctx.sample.side_effect = Exception("Sampling API error")

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

    with (
        patch.object(settings, "plesk_enable_sampling", True),
        patch("plesk_unified.server._get_search_candidates", return_value=mock_results),
        patch("plesk_unified.server._rerank_and_score", side_effect=lambda q, c, r: c),
    ):
        result = await search_plesk_unified(ctx=ctx, query="test query")

        assert ctx.sample.called
        assert "Synthesized Answer" not in result
        assert "file1.html" in result
