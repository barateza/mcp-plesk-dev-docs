import pytest
from unittest.mock import patch, MagicMock, AsyncMock, ANY
import logging
import json
import concurrent.futures

# New imports from the service-based architecture
from fastmcp import Context
from plesk_unified.server.mcp_app import create_mcp_app
from plesk_unified.application.services.container import AppContainer
from plesk_unified.settings import PleskSettings as Settings
from plesk_unified.types import CategoryEnum
from plesk_unified.types import VALID_CATEGORIES  # FIX: Corrected import path

# New tool imports
from plesk_unified.server.tools.search_tools import search_plesk_unified
from plesk_unified.server.tools.admin_tools import (
    warmup_server,
    daemon_health,
)
from plesk_unified.server.tools.indexing_tools import (
    refresh_knowledge,
)


# Mock lancedb.exceptions if not available
class MockTableNotFoundError(Exception):
    pass


# Helper to simulate executor submission by calling the function immediately
def sync_submit(fn, *args, **kwargs):
    f = concurrent.futures.Future()
    try:
        f.set_result(fn(*args, **kwargs))
    except Exception as e:
        f.set_exception(e)
    return f


@pytest.fixture
async def mock_server_dependencies():
    mock_container = MagicMock(spec=AppContainer)
    mock_ctx = MagicMock(spec=Context)
    mock_ctx.report_progress = AsyncMock()

    # Configure mock_ctx to provide mock_container
    mock_ctx.request_context.lifespan_context = {"container": mock_container}

    # --- Mock settings ---
    mock_container.settings = MagicMock(spec=Settings)
    mock_container.settings.plesk_model_profile = "pro"
    mock_container.settings.plesk_enable_sampling = False
    mock_container.settings.plesk_rerank_candidates = 50
    mock_container.settings.plesk_min_relevance_threshold = None
    mock_container.settings.plesk_daemon_auto_warmup = False
    mock_container.settings.plesk_auto_refresh_on_startup = True

    # --- Mock executor ---
    mock_container.executor = MagicMock(spec=concurrent.futures.ThreadPoolExecutor)
    mock_container.executor.submit.side_effect = sync_submit

    # --- Mock logger ---
    mock_container.logger = MagicMock(spec=logging.Logger)

    # --- Mock LanceDbRepository and its table ---
    mock_container.lancedb_repo = MagicMock()
    mock_table = MagicMock()
    (
        mock_table.search.return_value.where.return_value.limit.return_value.to_list.return_value
    ) = []
    mock_table.create_fts_index.return_value = None
    mock_table.delete.return_value = None
    mock_container.lancedb_repo.get_table.return_value = mock_table

    # --- Mock TurboQuantRepository ---
    mock_container.turboquant_repo = MagicMock()
    mock_container.turboquant_repo.get_tq_index.return_value = None

    # --- Mock SourceStateRepository ---
    mock_container.source_state_repo = MagicMock()
    mock_container.source_state_repo.load_source_state.return_value = None
    mock_container.source_state_repo.save_source_state.return_value = None

    # --- Mock SourceCatalog (sources) ---
    mock_container.sources = MagicMock()
    mock_container.sources.ensure_source_exists.return_value = True
    mock_container.sources.compute_source_fingerprint.return_value = ("abc", 10)

    # --- Mock ModelRuntime ---
    mock_container.model_runtime = MagicMock()
    mock_container.model_runtime.get_embedding_model.return_value = MagicMock(
        spec_set=["__call__"]
    )
    mock_container.model_runtime.get_reranker.return_value = None

    mock_profile = MagicMock()
    mock_profile.name = "pro"
    mock_profile.embed_model = "test-embed-model"
    mock_profile.reranker_enabled = False
    mock_profile.use_turboquant = False
    mock_container.model_runtime.get_profile.return_value = mock_profile

    # --- Mock SearchService ---
    mock_container.search_service = MagicMock()
    mock_container.search_service.search = AsyncMock()
    mock_container.search_service.search.return_value = ([], None)

    # --- Mock IndexingService ---
    mock_container.indexing_service = MagicMock()
    mock_container.indexing_service.refresh_knowledge = AsyncMock()
    mock_container.indexing_service.refresh_knowledge.return_value = (
        "FTS index rebuilt successfully."
    )
    mock_container.indexing_service.get_all_available_categories = MagicMock()
    mock_container.indexing_service.get_all_available_categories.return_value = list(
        VALID_CATEGORIES
    )

    # --- Mock WarmupService ---
    mock_container.warmup_service = MagicMock()
    mock_container.warmup_service.warmup_state = "idle"
    mock_container.warmup_service.warmup_error = None
    mock_container.warmup_service.run_warmup_sequence.return_value = [
        "Mock Warmup complete."
    ]
    mock_container.warmup_service.run_warmup_sequence.side_effect = (
        None  # Reset for specific tests
    )

    # --- Mock HealthService ---
    mock_container.health_service = MagicMock()
    mock_container.health_service.get_health_report.return_value = {
        "warmup_state": "idle",
        "warmup_error": None,
    }

    # --- Mock tool_error_boundary dependencies ---
    with (
        patch("plesk_unified.error_handling.LANCEDB_EXCEPTIONS_AVAILABLE", True),
        patch(
            "plesk_unified.error_handling.lancedb_exc", new=MagicMock()
        ) as mock_lancedb_exc,
    ):
        mock_lancedb_exc.TableNotFoundError = MockTableNotFoundError
        yield mock_ctx, mock_container


# Fixture for common mocks needed for server tools (for schemas)
@pytest.fixture
async def mcp_app_fixture(mock_server_dependencies):
    mock_ctx, mock_container = mock_server_dependencies
    mcp_instance = create_mcp_app(mock_container)
    async with mcp_instance.lifespan():
        yield mcp_instance, mock_container, mock_ctx


def test_category_enum_has_five_values():
    """Tests that CategoryEnum has exactly 5 defined values."""
    assert len(CategoryEnum) == 5
    expected_values = {"guide", "cli", "api", "php-stubs", "js-sdk"}
    assert set(c.value for c in CategoryEnum) == expected_values


@pytest.mark.asyncio
async def test_search_plesk_unified_schema_exposes_category_enum_with_five_values(
    mcp_app_fixture,
):
    """
    Tests that search_plesk_unified tool schema exposes the CategoryEnum
    with its values.
    """
    mcp_instance, _, _ = mcp_app_fixture
    tool = await mcp_instance.get_tool("search_plesk_unified")

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


@pytest.mark.asyncio
async def test_refresh_knowledge_schema_exposes_category_enum_plus_all(
    mcp_app_fixture,
):
    """
    Tests that refresh_knowledge tool schema exposes CategoryEnum values
    plus 'all'.
    """
    mcp_instance, _, _ = mcp_app_fixture
    tool = await mcp_instance.get_tool("refresh_knowledge")

    params = tool.parameters
    target_cat_schema = params["properties"]["category"]

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
    mock_ctx, _ = mock_server_dependencies
    # The validation happens before the tool body, so we expect tool_error_boundary
    # to catch this. The tool itself might not even be called if validation fails.
    # However, since the FastMCP runtime handles this, we just call the tool as usual.
    result = await search_plesk_unified(mock_ctx, query="test", category="invalid-cat")
    assert result.startswith(
        "[ERROR] Invalid argument: Invalid category: 'invalid-cat'."
    )


@pytest.mark.asyncio
async def test_search_plesk_unified_rejects_all_as_category(mock_server_dependencies):
    """
    Tests that search_plesk_unified returns an error string when 'all'
    is passed as category, now that tool_error_boundary intercepts.
    """
    mock_ctx, _ = mock_server_dependencies
    result = await search_plesk_unified(mock_ctx, query="test", category="all")
    assert result.startswith("[ERROR] Invalid argument: Invalid category: 'all'.")


@pytest.mark.asyncio
async def test_refresh_knowledge_accepts_all_as_category(mock_server_dependencies):
    """Tests that refresh_knowledge accepts 'all' as a category."""
    mock_ctx, mock_container = mock_server_dependencies
    # This should not raise an error, and call the service
    try:
        result = await refresh_knowledge(mock_ctx, category="all")
        mock_container.indexing_service.refresh_knowledge.assert_called_once_with(
            progress_callback=mock_ctx.report_progress, category="all", reset_db=False
        )
        assert "FTS index rebuilt successfully." in result
    except Exception as e:
        pytest.fail(f"refresh_knowledge unexpectedly rejected 'all': {e}")


@pytest.mark.asyncio
async def test_refresh_knowledge_accepts_valid_category_string(
    mock_server_dependencies,
):
    """Tests that refresh_knowledge accepts a valid category string."""
    mock_ctx, mock_container = mock_server_dependencies
    try:
        result = await refresh_knowledge(mock_ctx, category="guide")
        mock_container.indexing_service.refresh_knowledge.assert_called_once_with(
            progress_callback=mock_ctx.report_progress, category="guide", reset_db=False
        )
        assert "FTS index rebuilt successfully." in result
    except Exception as e:
        pytest.fail(f"refresh_knowledge unexpectedly rejected 'guide': {e}")


@pytest.mark.asyncio
async def test_refresh_knowledge_rejects_invalid_category_string(
    mock_server_dependencies,
):
    """
    Tests that refresh_knowledge returns an error string for an invalid category string,
    now that tool_error_boundary intercepts.
    """
    mock_ctx, _ = mock_server_dependencies
    result = await refresh_knowledge(mock_ctx, category="bogus")
    assert result.startswith("[ERROR] Invalid argument: Invalid category: 'bogus'.")


# Add a fixture to capture logs for the server logger
@pytest.fixture
def caplog_for_server(caplog):
    caplog.set_level(logging.INFO, logger="plesk_unified")
    yield caplog


@pytest.mark.asyncio
async def test_hardware_degradation_warning_logged_for_embedding_model(
    caplog_for_server, mock_server_dependencies
):
    """
    Tests that a hardware degradation warning is logged when embedding model
    initialization fails on a non-CPU device, and it falls back to CPU.
    """
    mock_ctx, mock_container = mock_server_dependencies

    # Reset mock_container.model_runtime.get_embedding_model side_effect
    # for this specific test
    mock_container.model_runtime.get_embedding_model.side_effect = None
    mock_container.model_runtime.get_embedding_model.reset_mock()

    with (
        patch(
            "plesk_unified.platform_utils.get_optimal_device",
            return_value="cuda",
        ),
        patch(
            "plesk_unified.platform_utils.log_hardware_degradation"
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
            # We need to call get_embedding_model through the model_runtime
            # The warmup_server tool will internally trigger
            # container.warmup_service.run_warmup_sequence
            # which will call container.model_runtime.get_embedding_model.
            # So, we need to mock the entire warmup sequence for this test.

            from plesk_unified.infrastructure.runtime.model_runtime import ModelRuntime

            real_runtime = ModelRuntime()

            mock_profile = MagicMock()
            mock_profile.name = "pro"
            mock_profile.embed_model = "test-embed-model"
            mock_profile.reranker_enabled = False
            mock_profile.use_turboquant = False

            # We need to mock get_profile to return our mock_profile
            real_runtime.get_profile = MagicMock(return_value=mock_profile)

            # Temporarily replace run_warmup_sequence
            def _mock_run_warmup_sequence_for_embedding_test():
                # Call REAL runtime logic
                real_runtime.get_embedding_model()
                return ["Simulated Warmup complete."]

            mock_container.warmup_service.run_warmup_sequence.side_effect = (
                _mock_run_warmup_sequence_for_embedding_test
            )

            # Trigger warmup which will now call get_embedding_model
            await warmup_server(mock_ctx)

            mock_log_degradation.assert_called_once_with("cuda", ANY, "cpu")
            assert "Selected compute device: CUDA" in caplog_for_server.text
            assert (
                "Embedding model initialized on CPU successfully."
                in caplog_for_server.text
            )
            # Check that create was called twice: once for CUDA, once for CPU
            assert mock_hf_reg.create.call_count == 2
            mock_hf_reg.create.assert_any_call(
                name="test-embed-model",
                device="cuda",
                batch_size=16,
                trust_remote_code=True,
            )
            mock_hf_reg.create.assert_any_call(
                name="test-embed-model", device="cpu", trust_remote_code=True
            )


@pytest.mark.asyncio
async def test_warmup_server_reports_running_and_done(
    mock_server_dependencies,
):
    """
    Tests that warmup_server transitions through 'running' and 'ready' states,
    and daemon_health reports correctly.
    """
    mock_ctx, mock_container = mock_server_dependencies

    # Before warmup
    mock_container.health_service.get_health_report.return_value = {
        "warmup_state": "idle",
        "warmup_error": None,
    }
    status_before = json.loads(await daemon_health(mock_ctx))
    assert status_before["warmup_state"] == "idle"

    # Start warmup - it should complete immediately due to mocking
    # mock_container.warmup_service.run_warmup_sequence is already mocked in fixture
    warmup_server_result = await warmup_server(mock_ctx)
    mock_container.warmup_service.run_warmup_sequence.assert_called_once()
    assert "Mock Warmup complete." in warmup_server_result

    # After warmup
    mock_container.health_service.get_health_report.return_value = {
        "warmup_state": "ready",
        "warmup_error": None,
    }
    status_after = json.loads(await daemon_health(mock_ctx))
    assert status_after["warmup_state"] == "ready"
    assert status_after["warmup_error"] is None


@pytest.mark.asyncio
async def test_warmup_server_reports_failed_on_exception(
    mock_server_dependencies, caplog_for_server
):
    """
    Tests that warmup_server reports a 'failed' state and logs the error
    if an exception occurs during the warmup sequence.
    """
    mock_ctx, mock_container = mock_server_dependencies

    # Before warmup
    mock_container.health_service.get_health_report.return_value = {
        "warmup_state": "idle",
        "warmup_error": None,
    }
    status_before = json.loads(await daemon_health(mock_ctx))
    assert status_before["warmup_state"] == "idle"

    # Configure warmup_service to raise an exception
    mock_container.warmup_service.run_warmup_sequence.side_effect = Exception(
        "Warmup failed"
    )

    # Start warmup (will fail)
    warmup_server_result = await warmup_server(mock_ctx)
    assert "Warmup failed: Warmup failed" in warmup_server_result

    # After failed warmup
    mock_container.health_service.get_health_report.return_value = {
        "warmup_state": "failed",
        "warmup_error": "Warmup failed",
    }
    status_after = json.loads(await daemon_health(mock_ctx))
    assert status_after["warmup_state"] == "failed"
    assert status_after["warmup_error"] == "Warmup failed"
    # The caplog_for_server fixture is set to INFO,
    # so it should capture the ERROR log from warmup_server
    assert "Manual warmup failed" in caplog_for_server.text
    assert "Warmup failed" in caplog_for_server.text
