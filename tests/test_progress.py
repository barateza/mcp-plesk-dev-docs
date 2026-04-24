import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import concurrent.futures
from plesk_unified.server import warmup_server, refresh_knowledge


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
        patch("plesk_unified.server.get_embedding_model"),
        patch("plesk_unified.server.get_tq_index"),
        patch("plesk_unified.server._get_profile") as mock_get_profile,
        patch("plesk_unified.server._build_doc_url"),
        patch("plesk_unified.server._save_source_state"),
        patch("plesk_unified.server._load_source_state", return_value={}),
        patch("plesk_unified.server.io_utils.ensure_source_exists", return_value=True),
        patch(
            "plesk_unified.server.io_utils.compute_source_fingerprint",
            return_value=("abc", 10),
        ),
        patch("plesk_unified.server.process_source_files", return_value=set()),
        patch("plesk_unified.server.chunking.persist_batch"),
    ):
        mock_profile = MagicMock()
        mock_profile.name = "full-tq"
        mock_profile.embed_model = "test-model"
        mock_profile.reranker_model = "test-reranker"
        mock_profile.use_turboquant = False
        mock_get_profile.return_value = mock_profile
        yield


@pytest.mark.asyncio
async def test_warmup_server_reports_progress(mock_server_dependencies):
    """Verify warmup_server calls ctx.report_progress exactly 4 times."""
    ctx = AsyncMock()
    # Ensure it's not already running
    import plesk_unified.server as server

    server._warmup_state = "idle"

    await warmup_server(ctx=ctx)

    assert ctx.report_progress.call_count == 4
    ctx.report_progress.assert_any_call(current=1, total=4)
    ctx.report_progress.assert_any_call(current=2, total=4)
    ctx.report_progress.assert_any_call(current=3, total=4)
    ctx.report_progress.assert_any_call(current=4, total=4)


@pytest.mark.asyncio
async def test_refresh_knowledge_reports_progress(mock_server_dependencies):
    """Verify refresh_knowledge calls ctx.report_progress exactly 4 times."""
    ctx = AsyncMock()

    await refresh_knowledge(ctx=ctx, target_category="all")

    assert ctx.report_progress.call_count == 4
    ctx.report_progress.assert_any_call(current=1, total=4)
    ctx.report_progress.assert_any_call(current=2, total=4)
    ctx.report_progress.assert_any_call(current=3, total=4)
    ctx.report_progress.assert_any_call(current=4, total=4)


@pytest.mark.asyncio
async def test_warmup_server_no_ctx_works(mock_server_dependencies):
    """Verify warmup_server works without a context object."""
    import plesk_unified.server as server

    server._warmup_state = "idle"
    result = await warmup_server(ctx=None)
    assert "Embedding model ready" in result


@pytest.mark.asyncio
async def test_refresh_knowledge_no_ctx_works(mock_server_dependencies):
    """Verify refresh_knowledge works without a context object."""
    result = await refresh_knowledge(ctx=None, target_category="api")
    assert result == "" or "FTS" in result
