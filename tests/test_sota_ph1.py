import pytest
from unittest.mock import MagicMock, AsyncMock
from mcp_plesk_dev_docs.application.services.search_service import SearchService
from mcp_plesk_dev_docs.server.tools.search_tools import SearchTools
from mcp_plesk_dev_docs.domain.models import CategoryEnum
from fastmcp import Context


@pytest.fixture
def search_service_mock():
    mock = MagicMock(spec=SearchService)
    mock.settings = MagicMock()
    mock.settings.plesk_enable_sampling = True
    mock.search_formatter = MagicMock()
    return mock


@pytest.mark.asyncio
async def test_get_file_content_delegation(search_service_mock):
    search_service_mock.get_file_content = AsyncMock(return_value="Full Content")
    tools = SearchTools(search_service_mock)

    res = await tools.get_file_content("test.php", CategoryEnum.PHP_STUBS)
    assert res == "Full Content"
    search_service_mock.get_file_content.assert_called_once_with(
        "test.php", "php-stubs"
    )


@pytest.mark.asyncio
async def test_resolve_references_delegation(search_service_mock):
    search_service_mock.search_raw = AsyncMock(
        return_value=[{"text": "ref", "filename": "f.php"}]
    )
    search_service_mock.search_formatter.format_markdown.return_value = "Formatted Ref"
    tools = SearchTools(search_service_mock)

    res = await tools.resolve_references("symbol", CategoryEnum.PHP_STUBS)
    assert res == "Formatted Ref"
    search_service_mock.search_raw.assert_called_once_with("symbol", "php-stubs")


@pytest.mark.asyncio
async def test_synthesize_answer_with_citations(search_service_mock):
    # Mock context.sample
    ctx = MagicMock(spec=Context)
    ctx.sample = AsyncMock()

    # Mock a sample result
    mock_result = MagicMock()
    mock_result.text = "Answer with [1]."
    ctx.sample.return_value = mock_result

    tools = SearchTools(search_service_mock)
    results = [
        {"filename": "a.php", "text": "content a", "chunk_id": 10},
        {"filename": "b.php", "text": "content b", "chunk_id": 20},
    ]

    answer = await tools._synthesize_answer(ctx, "question", results)

    assert "Answer with [1]." in answer
    assert "Sources:" in answer
    assert "[1] a.php (Chunk ID: 10)" in answer
    assert "[2] b.php (Chunk ID: 20)" in answer

    # Check if prompt contains SOURCE [1]
    args, kwargs = ctx.sample.call_args
    # The message content seems to be converted to a TextContent object by FastMCP?
    # Or our test environment is doing something.
    # Let's just check if 'SOURCE [1]: a.php' is in the string representation
    # if it's not a dict
    msg_content = kwargs["messages"][0].content
    if isinstance(msg_content, dict):
        assert "SOURCE [1]: a.php" in msg_content["text"]
    else:
        # If it's an object with a text attribute
        assert "SOURCE [1]: a.php" in msg_content.text
