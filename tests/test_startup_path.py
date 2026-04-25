import pytest
import concurrent.futures
from unittest.mock import AsyncMock, MagicMock, patch
from plesk_unified.server.tools import warmup_server as tool_warmup_server
from plesk_unified.server.tools import daemon_health as tool_daemon_health
from plesk_unified.server.lifecycle import (
    maybe_start_background_warmup,
    maybe_refresh_changed_sources,
)
from fastmcp import Context


# Helper to simulate executor submission by calling the function immediately
def sync_submit(fn, *args, **kwargs):
    f = concurrent.futures.Future()
    try:
        f.set_result(fn(*args, **kwargs))
    except Exception as e:
        f.set_exception(e)
    return f


@pytest.fixture
def mock_ctx_and_container():
    mock_ctx = AsyncMock(spec=Context)
    mock_container = MagicMock()
    mock_container.settings = MagicMock()
    mock_container.warmup_service = MagicMock()
    mock_container.indexing_service = AsyncMock()
    mock_container.health_service = MagicMock()
    mock_container.executor = MagicMock()
    mock_container.executor.submit.side_effect = sync_submit

    mock_ctx.request_context.lifespan_context = {"container": mock_container}
    return mock_ctx, mock_container


@pytest.mark.asyncio
async def test_warmup_server_tool(mock_ctx_and_container):
    mock_ctx, mock_container = mock_ctx_and_container
    mock_container.warmup_service.begin_warmup.return_value = True
    mock_container.warmup_service.run_warmup_sequence.return_value = ["OK"]

    result = await tool_warmup_server(mock_ctx)
    assert "OK" in result
    mock_container.warmup_service.run_warmup_sequence.assert_called_once()


@pytest.mark.asyncio
async def test_daemon_health_tool(mock_ctx_and_container):
    mock_ctx, mock_container = mock_ctx_and_container
    mock_container.health_service.get_health_report.return_value = {"status": "ok"}

    result = await tool_daemon_health(mock_ctx)
    assert '"status": "ok"' in result


@pytest.mark.asyncio
async def test_lifecycle_maybe_start_background_warmup(mock_ctx_and_container):
    _, mock_container = mock_ctx_and_container
    maybe_start_background_warmup(mock_container)
    mock_container.warmup_service.maybe_start_background_warmup.assert_called_once()


@pytest.mark.asyncio
async def test_lifecycle_maybe_refresh_changed_sources_calls_service(
    mock_ctx_and_container,
):
    _, mock_container = mock_ctx_and_container
    mock_container.settings.plesk_auto_refresh_on_startup = True

    # In pytest-asyncio, there IS a running loop, so create_task will be used.
    with patch("asyncio.create_task") as mock_create_task:
        maybe_refresh_changed_sources(mock_container)
        mock_create_task.assert_called_once()
