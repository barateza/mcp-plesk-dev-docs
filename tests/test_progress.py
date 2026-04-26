import pytest
import concurrent.futures
from unittest.mock import AsyncMock, MagicMock
from plesk_unified.server.tools import warmup_server as tool_warmup_server
from plesk_unified.server.tools import refresh_knowledge as tool_refresh_knowledge
from plesk_unified.types import CategoryEnum
from fastmcp import Context


# Helper to simulate executor submission by calling the function immediately
def sync_submit(fn, *args, **kwargs):
    f = concurrent.futures.Future()
    try:
        f.set_result(fn(*args, **kwargs))
    except Exception as e:
        f.set_exception(e)
    return f


# Fixture to set up a mock AppContainer and AsyncMock ctx for progress testing
@pytest.fixture
def mock_ctx_and_container():
    mock_ctx = MagicMock(spec=Context)
    mock_ctx.report_progress = AsyncMock()

    # Mock container and its services
    mock_container = MagicMock()
    mock_container.settings = MagicMock()
    mock_container.warmup_service = MagicMock()
    mock_container.indexing_service = MagicMock()
    mock_container.indexing_service.refresh_knowledge = AsyncMock()
    mock_container.executor = MagicMock()
    mock_container.executor.submit.side_effect = sync_submit

    # Inject container into lifespan context
    mock_ctx.request_context.lifespan_context = {"container": mock_container}

    return mock_ctx, mock_container


@pytest.mark.asyncio
async def test_warmup_server_reports_progress(mock_ctx_and_container):
    """Verify warmup_server calls ctx.report_progress."""
    mock_ctx, mock_container = mock_ctx_and_container

    mock_container.warmup_service.begin_warmup.return_value = True
    mock_container.warmup_service.run_warmup_sequence.return_value = [
        "Part 1",
        "Part 2",
    ]

    result = await tool_warmup_server(mock_ctx)

    assert "Part 1\nPart 2" in result
    assert mock_ctx.report_progress.call_count >= 2
    mock_ctx.report_progress.assert_any_call(1, 4)
    mock_ctx.report_progress.assert_any_call(4, 4)


@pytest.mark.asyncio
async def test_refresh_knowledge_delegates_to_service(mock_ctx_and_container):
    """Verify refresh_knowledge calls indexing_service."""
    mock_ctx, mock_container = mock_ctx_and_container

    mock_container.indexing_service.refresh_knowledge.return_value = "Refresh report"

    result = await tool_refresh_knowledge(mock_ctx, category=CategoryEnum.API)

    assert result == "Refresh report"
    mock_container.indexing_service.refresh_knowledge.assert_called_once_with(
        progress_callback=mock_ctx.report_progress, category="api", reset_db=False
    )
