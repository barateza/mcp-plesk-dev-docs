import pytest
from unittest.mock import patch, MagicMock
from mcp_plesk_dev_docs.server.error_handling import (
    _classify_error,
    tool_error_boundary,
)
import logging
import asyncio


# Mock lancedb.exceptions if not available
class MockTableNotFoundError(Exception):
    pass


@pytest.fixture(autouse=True)
def mock_lancedb_exceptions():
    """Mocks lancedb.exceptions for consistent testing."""
    with (
        patch(
            "mcp_plesk_dev_docs.server.error_handling.LANCEDB_EXCEPTIONS_AVAILABLE",
            True,
        ),
        patch(
            "mcp_plesk_dev_docs.server.error_handling.lancedb_exc", new=MagicMock()
        ) as mock_lancedb_exc,
    ):
        mock_lancedb_exc.TableNotFoundError = MockTableNotFoundError
        yield


# Test cases for _classify_error directly (for specific error messages)
def test_classify_error_lancedb_table_not_found():
    """Tests classification of LanceDB TableNotFoundError."""
    exc = MockTableNotFoundError("Table 'plesk_knowledge' not found")
    result = _classify_error(exc)
    assert result == (
        "[ERROR] Knowledge base not indexed. "
        "Call refresh_knowledge(reset_db=True) first."
    )


def test_classify_error_runtime_model_not_loaded():
    """Tests classification of RuntimeError containing 'model'."""
    exc = RuntimeError("Embedding model could not be initialized.")
    result = _classify_error(exc)
    assert result == "[ERROR] Embedding model not loaded. Call warmup_server first."


def test_classify_error_permission_error():
    """Tests classification of PermissionError."""
    exc = PermissionError("Permission denied: '/etc/passwd'")
    result = _classify_error(exc)
    assert result == "[ERROR] Path traversal detected. Operation rejected."


def test_classify_error_lancedb_connection_error():
    """Tests classification of generic LanceDB connection error."""
    # This specifically tests the `lancedb` or `database` keyword in the message
    exc = ConnectionError("Failed to connect to lancedb server.")
    result = _classify_error(exc)
    assert result == (
        "[ERROR] Database unavailable. Check storage/lancedb/ path. "
        "Call daemon_health for details."
    )


def test_classify_error_generic_runtime_error():
    """Tests classification of a generic RuntimeError not matching specific patterns."""
    exc = RuntimeError("Something unexpected happened.")
    result = _classify_error(exc)
    assert result == (
        "[ERROR] Unexpected server error. "
        "Call daemon_health to check server state, then retry."
    )


# Test cases for tool_error_boundary (decorator behavior)
def test_tool_error_boundary_returns_error_string_for_lancedb_table_not_found():
    """
    Tests that tool_error_boundary catches LanceDB TableNotFoundError
    and returns the correct error string without traceback.
    """

    @tool_error_boundary
    def bad_tool():
        raise MockTableNotFoundError("Table 'plesk_knowledge' not found")

    with patch.object(
        logging.getLogger("mcp_plesk_dev_docs"), "error"
    ) as mock_logger_error:
        result = bad_tool()
        assert result == (
            "[ERROR] Knowledge base not indexed. "
            "Call refresh_knowledge(reset_db=True) first."
        )
        mock_logger_error.assert_called_once()
        # Verify no traceback in the returned string
        assert "traceback" not in result.lower()
        assert (
            "lancedb.exceptions" not in result.lower()
        )  # ensure original exception details are not exposed


def test_tool_error_boundary_returns_error_string_for_runtime_model_error():
    """
    Tests that tool_error_boundary catches RuntimeError containing 'model'
    and returns the correct error string without traceback.
    """

    @tool_error_boundary
    def bad_tool():
        raise RuntimeError("Embedding model could not be initialized.")

    with patch.object(
        logging.getLogger("mcp_plesk_dev_docs"), "error"
    ) as mock_logger_error:
        result = bad_tool()
        assert result == "[ERROR] Embedding model not loaded. Call warmup_server first."
        mock_logger_error.assert_called_once()
        assert "traceback" not in result.lower()


def test_tool_error_boundary_returns_error_string_for_permission_error():
    """
    Tests that tool_error_boundary catches PermissionError
    and returns the correct error string without traceback.
    """

    @tool_error_boundary
    def bad_tool():
        raise PermissionError("Permission denied: '/etc/passwd'")

    with patch.object(
        logging.getLogger("mcp_plesk_dev_docs"), "error"
    ) as mock_logger_error:
        result = bad_tool()
        assert result == "[ERROR] Path traversal detected. Operation rejected."
        mock_logger_error.assert_called_once()
        assert "traceback" not in result.lower()


def test_tool_error_boundary_returns_error_string_for_generic_exception():
    """
    Tests that tool_error_boundary catches a generic exception
    and returns the correct error string without traceback.
    """

    @tool_error_boundary
    def bad_tool():
        raise ValueError("Some unexpected value.")

    with patch.object(
        logging.getLogger("mcp_plesk_dev_docs"), "error"
    ) as mock_logger_error:
        result = bad_tool()
        assert result == (
            "[ERROR] Unexpected server error. "
            "Call daemon_health to check server state, then retry."
        )
        mock_logger_error.assert_called_once()
        assert "traceback" not in result.lower()


def test_tool_error_boundary_preserves_return_value_on_success():
    """
    Tests that tool_error_boundary returns the original function's result on success.
    """

    @tool_error_boundary
    def good_tool():
        return "Success!"

    result = good_tool()
    assert result == "Success!"


@pytest.mark.asyncio
async def test_tool_error_boundary_async_function_returns_error_string():
    """Tests that tool_error_boundary works for async functions."""

    @tool_error_boundary
    async def async_bad_tool():
        raise RuntimeError("Async model error.")

    with patch.object(
        logging.getLogger("mcp_plesk_dev_docs"), "error"
    ) as mock_logger_error:
        result = await async_bad_tool()
        assert result == "[ERROR] Embedding model not loaded. Call warmup_server first."
        mock_logger_error.assert_called_once()
        assert "traceback" not in result.lower()


@pytest.mark.asyncio
async def test_tool_error_boundary_async_function_preserves_return_value_on_success():
    """
    Tests that tool_error_boundary works for async functions
    and preserves return value.
    """

    @tool_error_boundary
    async def async_good_tool():
        await asyncio.sleep(0.01)  # Simulate async work
        return "Async Success!"

    result = await async_good_tool()
    assert result == "Async Success!"
