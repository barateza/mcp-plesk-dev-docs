import pytest
from unittest.mock import patch, MagicMock, ANY
from plesk_unified.server import (
    search_plesk_unified,
    refresh_knowledge,
    _validate_category,  # noqa: F401 - Imported for clarity, not directly tested in this file
    VALID_CATEGORIES,
    mcp,  # Assuming mcp object is directly available for schema inspection
    warmup_server,
    daemon_health,  # Import the actual function to test its internal logic
)
from plesk_unified.types import CategoryEnum, CategoryOrAll  # noqa: F401 - Imported for clarity, not directly tested in this file
import logging
import json
import asyncio
import re  # For parsing tool_code_for_ai
import concurrent.futures  # Needed for MockConcurrentFuture


# Mock lancedb.exceptions if not available
class MockTableNotFoundError(Exception):
    pass


# Helper to create a completed Future
def make_completed_future(result_value):
    f = concurrent.futures.Future()
    f.set_result(result_value)
    return f


# Fixture for common mocks needed for server tools
@pytest.fixture
def mock_server_dependencies():
    # --- FIX: Reset global server state in the target module for each test ---
    import plesk_unified.server as server

    server._embedding_model = None
    server._warmup_state = "idle"
    server._warmup_thread = None
    server._warmup_error = None
    server._tq_index = None
    server._detected_device = None

    # Create a mock_executor instance outside the patch context manager
    mock_server_executor = MagicMock(spec=concurrent.futures.ThreadPoolExecutor)

    def mock_submit_side_effect(func, *args, **kwargs):
        return make_completed_future(func(*args, **kwargs))

    mock_server_executor.submit.side_effect = mock_submit_side_effect

    with (
        # Patch server._executor with our specially configured mock
        patch("plesk_unified.server._executor", new=mock_server_executor),
        patch("plesk_unified.server.get_table"),
        patch("plesk_unified.server.get_reranker"),
        patch("plesk_unified.server.get_tq_index"),
        patch("plesk_unified.server._get_profile") as mock_get_profile,
        patch("plesk_unified.server._build_doc_url"),
        patch("plesk_unified.server._save_source_state"),
        patch("plesk_unified.server._load_source_state"),
        patch("plesk_unified.server.io_utils.ensure_source_exists", return_value=True),
        patch(
            "plesk_unified.server.io_utils.compute_source_fingerprint",
            return_value=("abc", 10),
        ),
        patch("plesk_unified.server.process_source_files", return_value=set()),
        patch("plesk_unified.server.chunking.persist_batch"),
    ):  # Mock this to prevent actual DB ops
        mock_profile = MagicMock()
        mock_profile.name = "full-tq"
        mock_profile.reranker_enabled = False
        mock_profile.use_turboquant = False
        mock_profile.embed_model = (
            "test-embed-model"  # Needed for hardware degradation test
        )
        mock_get_profile.return_value = mock_profile

        mock_table = MagicMock()
        (
            mock_table.search.return_value.where.return_value.limit.return_value.to_list.return_value
        ) = []
        mock_table.create_fts_index.return_value = None  # Mock FTS index creation
        mock_table.delete.return_value = None  # Mock delete operation

        # --- FIX: Mock lancedb.exceptions for tool_error_boundary in test_server.py ---
        with (
            patch("plesk_unified.error_handling.LANCEDB_EXCEPTIONS_AVAILABLE", True),
            patch(
                "plesk_unified.error_handling.lancedb_exc", new=MagicMock()
            ) as mock_lancedb_exc,
        ):
            mock_lancedb_exc.TableNotFoundError = MockTableNotFoundError

            # Patch get_table to return the mocked table
            with patch("plesk_unified.server.get_table", return_value=mock_table):
                yield


def _extract_enum_from_tool_code(tool_code: str, param_name: str) -> list[str] | None:
    """
    Parses the tool_code_for_ai string to find the enum values for a given parameter.
    This is a fragile approach as it relies on string formatting.
    """
    # Regex to find a parameter definition and its enum values
    # It looks for "param_name: Literal[..." or "param_name: CategoryEnum"
    # and then tries to extract the enum values.
    # This might need to be refined based on the actual output format.
    match = re.search(rf"{param_name}: (?:Literal\[([^\]]+)\]|CategoryEnum)", tool_code)
    if match:
        if match.group(1):  # Matched Literal[...]
            enum_str = match.group(1)
            # Clean up and split by comma
            enum_values = [v.strip().strip("'\"") for v in enum_str.split(",")]
            # Filter out 'NoneType' or 'None' if present due to Optional/Union
            return [v for v in enum_values if v not in ("None", "NoneType")]
        else:  # Matched CategoryEnum
            return sorted(
                [c.value for c in CategoryEnum]
            )  # Fallback to actual enum values

    # For refresh_knowledge, the type is
    # CategoryOrAll = Union[CategoryEnum, Literal["all"]]
    # This might appear as CategoryEnum | Literal["all"] in tool_code_for_ai
    match_union = re.search(
        rf"{param_name}: (?:CategoryEnum \| Literal\[['\"]all['\"]\])", tool_code
    )
    if match_union:
        return sorted([c.value for c in CategoryEnum] + ["all"])

    return None


def test_category_enum_has_five_values():
    """Tests that CategoryEnum has exactly 5 defined values."""
    assert len(CategoryEnum) == 5
    expected_values = {"guide", "cli", "api", "php-stubs", "js-sdk"}
    assert set(c.value for c in CategoryEnum) == expected_values


def test_search_plesk_unified_schema_exposes_category_enum_with_five_values(
    mock_server_dependencies,
):
    """
    Tests that search_plesk_unified tool schema exposes the CategoryEnum
    with its values.
    """
    tool = asyncio.run(mcp.get_tool("search_plesk_unified"))

    # Check if the parameter definition for 'category' contains the enum values
    params = tool.parameters
    category_schema = params["properties"]["category"]

    # Resolve $ref if present
    if "$ref" in category_schema["anyOf"][0]:
        ref = category_schema["anyOf"][0]["$ref"]
        def_name = ref.split("/")[-1]
        enum_values = params["$defs"][def_name]["enum"]
    else:
        enum_values = category_schema["anyOf"][0]["enum"]

    assert set(enum_values) == set(VALID_CATEGORIES)
    assert len(enum_values) == 5


def test_refresh_knowledge_schema_exposes_category_enum_plus_all(
    mock_server_dependencies,
):
    """
    Tests that refresh_knowledge tool schema exposes CategoryEnum values
    plus 'all'.
    """
    tool = asyncio.run(mcp.get_tool("refresh_knowledge"))

    params = tool.parameters
    target_cat_schema = params["properties"]["target_category"]

    # Resolve $ref for the first part of anyOf
    ref = target_cat_schema["anyOf"][0]["$ref"]
    def_name = ref.split("/")[-1]
    enum_values = params["$defs"][def_name]["enum"]

    # The second part should be Literal['all'] (const: 'all' in JSON Schema)
    all_const = target_cat_schema["anyOf"][1]["const"]

    expected_enum = set(VALID_CATEGORIES) | {all_const}
    assert set(enum_values) | {all_const} == expected_enum
    assert len(enum_values) == 5


@pytest.mark.asyncio
async def test_search_plesk_unified_rejects_invalid_category_string(
    mock_server_dependencies,
):
    """
    Tests that search_plesk_unified returns an error string for an
    invalid category string, now that tool_error_boundary intercepts.
    """
    result = await search_plesk_unified(query="test", category="invalid-cat")
    assert result.startswith(
        "[ERROR] Invalid argument: Invalid category: 'invalid-cat'."
    )


@pytest.mark.asyncio
async def test_search_plesk_unified_rejects_all_as_category(mock_server_dependencies):
    """
    Tests that search_plesk_unified returns an error string when 'all'
    is passed as category, now that tool_error_boundary intercepts.
    """
    result = await search_plesk_unified(query="test", category="all")
    assert result.startswith("[ERROR] Invalid argument: Invalid category: 'all'.")


@pytest.mark.asyncio
async def test_refresh_knowledge_accepts_all_as_category(mock_server_dependencies):
    """Tests that refresh_knowledge accepts 'all' as a category."""
    # This should not raise an error
    try:
        result = await refresh_knowledge(target_category="all")
        assert (
            "FTS index rebuilt successfully." in result
        )  # Check for a known success string
    except ValueError as e:
        pytest.fail(f"refresh_knowledge unexpectedly rejected 'all': {e}")


@pytest.mark.asyncio
async def test_refresh_knowledge_accepts_valid_category_string(
    mock_server_dependencies,
):
    """Tests that refresh_knowledge accepts a valid category string."""
    try:
        result = await refresh_knowledge(target_category="guide")
        assert "FTS index rebuilt successfully." in result
    except ValueError as e:
        pytest.fail(f"refresh_knowledge unexpectedly rejected 'guide': {e}")


@pytest.mark.asyncio
async def test_refresh_knowledge_rejects_invalid_category_string(
    mock_server_dependencies,
):
    """
    Tests that refresh_knowledge returns an error string for an invalid category string,
    now that tool_error_boundary intercepts.
    """
    result = await refresh_knowledge(target_category="bogus")
    assert result.startswith("[ERROR] Invalid argument: Invalid category: 'bogus'.")


# Add a fixture to capture logs for the server logger
@pytest.fixture
def caplog_for_server(caplog):
    caplog.set_level(
        logging.INFO, logger="plesk_unified"
    )  # Set to INFO or DEBUG to capture warnings too
    yield caplog


@pytest.mark.asyncio
async def test_hardware_degradation_warning_logged_for_embedding_model(
    caplog_for_server, mock_server_dependencies
):
    """
    Tests that a hardware degradation warning is logged when embedding model
    initialization fails on a non-CPU device, and it falls back to CPU.
    """
    # Reset global _embedding_model state for re-initialization
    import plesk_unified.server as server

    server._embedding_model = None
    server._detected_device = None

    with (
        patch(
            "plesk_unified.server.platform_utils.get_optimal_device",
            return_value="cuda",
        ),
        patch(
            "plesk_unified.server.platform_utils.log_hardware_degradation"
        ) as mock_log_degradation,
    ):
        # Mock the embedding registry's create method to fail on first attempt (cuda)
        # and succeed on the second (cpu fallback)
        mock_hf_reg = MagicMock()
        mock_hf_reg.create.side_effect = [
            # First call (device="cuda") fails
            RuntimeError("Simulated CUDA driver error: out of memory"),
            # Second call (device="cpu") succeeds
            MagicMock(
                spec_set=["__call__"]
            ),  # Needs to be callable, but actual behavior doesn't matter
        ]
        with patch(
            "lancedb.embeddings.get_registry",
            return_value=MagicMock(get=lambda x: mock_hf_reg),
        ):
            # The actual function we are testing
            # Call get_embedding_model again to trigger the logic.
            # The fixture already mocks it, so we need to get real function.
            # Use `plesk_unified.server.get_embedding_model` directly
            # to bypass fixture mock.
            from plesk_unified.server import get_embedding_model

            get_embedding_model()

            mock_log_degradation.assert_called_once_with("cuda", ANY, "cpu")
            assert "Selected compute device: CUDA" in caplog_for_server.text
            assert (
                "Embedding model initialized on CPU successfully."
                in caplog_for_server.text
            )
            assert (
                server._embedding_model is not None
            )  # Ensure it got initialized on CPU finally
            # Check that create was called twice: once for CUDA, once for CPU
            assert mock_hf_reg.create.call_count == 2
            mock_hf_reg.create.assert_any_call(name="test-embed-model", device="cuda")
            mock_hf_reg.create.assert_any_call(name="test-embed-model", device="cpu")


# JobRegistry related tests (interpreting as warmup state transitions)
@patch(
    "plesk_unified.server._run_warmup_sequence", return_value=["Mock Warmup complete."]
)
@patch(
    "plesk_unified.server._warmup_state", "idle"
)  # Ensure warmup state is idle before test
@pytest.mark.asyncio
async def test_warmup_server_reports_running_and_done(
    mock_run_warmup_sequence, mock_server_dependencies
):
    """
    Tests that warmup_server transitions through 'running' and 'ready' states,
    and daemon_health reports correctly.
    """
    # Before warmup
    status_before = json.loads(await daemon_health())
    assert status_before["warmup_state"] == "idle"

    # Start warmup - it should complete immediately due to mocking
    warmup_server_result = await warmup_server()
    assert "Mock Warmup complete." in warmup_server_result  # Check the mocked output

    # After warmup
    status_after = json.loads(await daemon_health())
    assert status_after["warmup_state"] == "ready"
    assert status_after["warmup_error"] is None


@patch(
    "plesk_unified.server._run_warmup_sequence", side_effect=Exception("Warmup failed")
)
@patch(
    "plesk_unified.server._warmup_state", "idle"
)  # Ensure warmup state is idle before test
@pytest.mark.asyncio
async def test_warmup_server_reports_failed_on_exception(
    mock_run_warmup_sequence, mock_server_dependencies, caplog_for_server
):
    """
    Tests that warmup_server reports a 'failed' state and logs the error
    if an exception occurs during the warmup sequence.
    """
    # Before warmup
    status_before = json.loads(await daemon_health())
    assert status_before["warmup_state"] == "idle"

    # Start warmup (will fail)
    warmup_server_result = await warmup_server()
    assert "[ERROR] Unexpected server error" in warmup_server_result

    # After failed warmup
    status_after = json.loads(await daemon_health())
    assert status_after["warmup_state"] == "failed"
    assert status_after["warmup_error"] == "Warmup failed"
    # The caplog_for_server fixture is set to INFO,
    # so it should capture the ERROR log from tool_error_boundary
    assert "Tool warmup_server failed" in caplog_for_server.text
    assert (
        "Manual warmup failed." in caplog_for_server.text
    )  # Check log for the exception
