import pytest
from unittest.mock import patch

# Access the global mcp instance from the server module
from plesk_unified.server import mcp


@pytest.mark.asyncio
async def test_toc_resources_registered():
    """Verify all 5 TOC resources are registered in mcp.list_resources()."""
    resources = await mcp.list_resources()
    resource_uris = {str(r.uri) for r in resources}
    expected_uris = {
        "plesk://toc/api",
        "plesk://toc/cli",
        "plesk://toc/guide",
        "plesk://toc/js-sdk",
        "plesk://toc/php-stubs",
    }
    for uri in expected_uris:
        assert uri in resource_uris, f"Resource {uri} not found in registered resources"


@pytest.mark.asyncio
async def test_toc_resource_api_returns_markdown():
    """Verify plesk://toc/api returns a formatted Markdown string."""
    mock_toc_map = {
        "api_ref.html": {"title": "API Reference", "breadcrumb": "Reference > API"}
    }
    with (
        patch("plesk_unified.server.get_toc_map_for_source", return_value=mock_toc_map),
        patch(
            "plesk_unified.server._build_doc_url",
            return_value="https://example.com/api_ref",
        ),
    ):
        result = await mcp.read_resource("plesk://toc/api")
        content = (
            result.contents[0].text
            if hasattr(result.contents[0], "text")
            else result.contents[0].content
        )
        assert "# Plesk API Table of Contents" in content
        assert "- [API Reference](https://example.com/api_ref)" in content
        assert "Path: Reference > API" in content


@pytest.mark.asyncio
async def test_toc_resource_cli_returns_markdown():
    """Verify plesk://toc/cli returns a formatted Markdown string."""
    mock_toc_map = {
        "cli_ref.html": {"title": "CLI Reference", "breadcrumb": "Reference > CLI"}
    }
    with (
        patch("plesk_unified.server.get_toc_map_for_source", return_value=mock_toc_map),
        patch(
            "plesk_unified.server._build_doc_url",
            return_value="https://example.com/cli_ref",
        ),
    ):
        result = await mcp.read_resource("plesk://toc/cli")
        content = (
            result.contents[0].text
            if hasattr(result.contents[0], "text")
            else result.contents[0].content
        )
        assert "# Plesk CLI Table of Contents" in content
        assert "- [CLI Reference](https://example.com/cli_ref)" in content
        assert "Path: Reference > CLI" in content


@pytest.mark.asyncio
async def test_toc_resource_no_entries():
    """Verify TOC resource returns a 'no entries' message when empty."""
    with patch("plesk_unified.server.get_toc_map_for_source", return_value={}):
        result = await mcp.read_resource("plesk://toc/api")
        content = (
            result.contents[0].text
            if hasattr(result.contents[0], "text")
            else result.contents[0].content
        )
        assert "No Table of Contents available for api" in content


@pytest.mark.asyncio
async def test_toc_resource_invalid_category():
    """Verify TOC helper handles unknown categories gracefully."""
    from plesk_unified.server import _handle_toc_resource

    result = _handle_toc_resource("unknown")
    assert "Category 'unknown' not found." in result
