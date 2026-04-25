import pytest
from unittest.mock import AsyncMock, MagicMock
from plesk_unified.server.mcp_app import create_mcp_app
from plesk_unified.application.services.container import AppContainer
from plesk_unified.server.resources import get_toc_resource


@pytest.fixture
def mock_app_container():
    mock_container = MagicMock(spec=AppContainer)
    mock_container.toc_formatter = MagicMock()
    return mock_container


@pytest.fixture
def mcp_app(mock_app_container):
    return create_mcp_app(mock_app_container)


@pytest.mark.asyncio
async def test_toc_resources_registered(mcp_app):
    """Verify TOC resource is registered in FastMCP instance."""
    templates = await mcp_app.list_resource_templates()
    for t in templates:
        print(f"Registered template: {t.uri_template}")
    uris = {t.uri_template for t in templates}
    # FastMCP uses URI templates, so it might just have plesk://toc/{category}
    assert any("plesk://toc/" in uri for uri in uris)


@pytest.mark.asyncio
async def test_toc_resource_calls_formatter(mock_app_container):
    """Verify get_toc_resource calls toc_formatter.to_json."""
    mock_ctx = AsyncMock()
    mock_ctx.request_context.lifespan_context = {"container": mock_app_container}

    mock_app_container.toc_formatter.to_json.return_value = '{"toc": []}'

    result = await get_toc_resource("guide", mock_ctx)

    assert result == '{"toc": []}'
    mock_app_container.toc_formatter.to_json.assert_called_once_with("guide")


@pytest.mark.asyncio
async def test_toc_resource_invalid_category(mock_app_container):
    """Verify TOC helper handles unknown categories gracefully."""
    mock_ctx = AsyncMock()
    mock_ctx.request_context.lifespan_context = {"container": mock_app_container}

    # toc_formatter.to_json might raise ValueError for invalid category
    mock_app_container.toc_formatter.to_json.side_effect = ValueError(
        "Invalid category: 'unknown'"
    )

    # get_toc_resource is decorated with @tool_error_boundary
    result = await get_toc_resource("unknown", mock_ctx)
    assert "[ERROR] Invalid argument: Invalid category: 'unknown'" in result
