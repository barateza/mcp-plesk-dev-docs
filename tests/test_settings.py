import os
import pytest
from pydantic import ValidationError
from unittest.mock import patch
from plesk_unified.settings import PleskSettings


@pytest.fixture(autouse=True)
def cleanup_plesk_env_vars():
    """
    Fixture to clear Plesk-specific environment variables before each test
    and restore them afterward.
    """
    original_env_vars = {}
    plesk_keys = [
        "LOG_LEVEL",
        "LOG_FILE",
        "LOG_HANDLER",
        "PLESK_MODEL_PROFILE",
        "PLESK_EMBED_MODEL",
        "PLESK_RERANKER_MODEL",
        "PLESK_RERANKER_ENABLED",
        "PLESK_EMBED_DIM",
        "PLESK_DAEMON_AUTO_WARMUP",
        "PLESK_AUTO_REFRESH_ON_STARTUP",
        "PLESK_INDEX_SUMMARIES",
        "PLESK_RERANK_CANDIDATES",
        "PLESK_MIN_RELEVANCE_THRESHOLD",
        "OPENROUTER_API_KEY",
        "FORCE_DEVICE",
        "PLESK_HTML_LLM_TABLE_NORMALIZE",
        "TQDM_DISABLE",
        "TRANSFORMERS_VERBOSITY",
    ]
    # Store original values and then delete them
    for key in plesk_keys:
        if key in os.environ:
            original_env_vars[key] = os.environ[key]
            del os.environ[key]

    yield  # Run the test

    # Restore original environment variables
    for key, value in original_env_vars.items():
        os.environ[key] = value
    # Clean up any variables set by the test itself that weren't there originally
    for key in plesk_keys:
        if key not in original_env_vars and key in os.environ:
            del os.environ[key]


def test_settings_loads_defaults_when_env_absent(cleanup_plesk_env_vars):
    """
    Tests that settings load with default values
    when no relevant environment variables are set.
    """
    settings = PleskSettings(_env_file=None)

    assert settings.log_level == "INFO"
    assert settings.plesk_model_profile == "pro"
    assert settings.plesk_daemon_auto_warmup is False
    assert settings.openrouter_api_key == ""
    assert settings.tqdm_disable is True
    assert settings.plesk_auto_refresh_on_startup is True
    assert settings.plesk_index_summaries is False
    assert settings.plesk_rerank_candidates == 50
    assert settings.plesk_html_llm_table_normalize is False


def test_settings_parses_valid_env_vars(cleanup_plesk_env_vars):
    """Tests that settings correctly parse valid environment variables."""
    with patch.dict(
        os.environ,
        {
            "LOG_LEVEL": "DEBUG",
            "PLESK_MODEL_PROFILE": "local",
            "PLESK_DAEMON_AUTO_WARMUP": "True",
            "OPENROUTER_API_KEY": "sk-12345",
            "TQDM_DISABLE": "False",
            "PLESK_EMBED_DIM": "768",
            "PLESK_MIN_RELEVANCE_THRESHOLD": "0.75",
        },
    ):
        settings = PleskSettings(_env_file=None)
        assert settings.log_level == "DEBUG"
        assert settings.plesk_model_profile == "local"
        assert settings.plesk_daemon_auto_warmup is True
        assert settings.openrouter_api_key == "sk-12345"
        assert settings.tqdm_disable is False
        assert settings.plesk_embed_dim == 768
        assert settings.plesk_min_relevance_threshold == 0.75


def test_invalid_log_level_raises_validation_error(cleanup_plesk_env_vars):
    """Tests that an invalid LOG_LEVEL raises a ValidationError."""
    with (
        patch.dict(os.environ, {"LOG_LEVEL": "VERBOSE"}),
        pytest.raises(ValidationError) as excinfo,
    ):
        PleskSettings(_env_file=None)
    assert "log_level" in str(excinfo.value)
    # --- FIX: Updated assertion for Pydantic v2 error message ---
    assert "Input should be 'DEBUG', 'INFO', 'WARNING', 'ERROR' or 'CRITICAL'" in str(
        excinfo.value
    )


def test_log_level_case_insensitivity_not_supported_by_pydantic_literal(
    cleanup_plesk_env_vars,
):
    """
    Tests that pydantic Literal types are case-sensitive by default,
    so 'info' is not valid if 'INFO' is specified.
    """
    with (
        patch.dict(os.environ, {"LOG_LEVEL": "info"}),
        pytest.raises(ValidationError) as excinfo,
    ):
        PleskSettings(_env_file=None)
    assert "log_level" in str(excinfo.value)
    # --- FIX: Updated assertion for Pydantic v2 error message ---
    assert "Input should be 'DEBUG', 'INFO', 'WARNING', 'ERROR' or 'CRITICAL'" in str(
        excinfo.value
    )


def test_effective_log_file_returns_explicit_path(cleanup_plesk_env_vars):
    """Tests that effective_log_file returns the explicit log_file if set."""
    with patch.dict(os.environ, {"LOG_FILE": "/var/log/plesk.log"}):
        settings = PleskSettings(_env_file=None)
        assert settings.effective_log_file == "/var/log/plesk.log"


def test_effective_log_file_generates_default_path_and_creates_dir(
    cleanup_plesk_env_vars,
):
    """
    Tests that effective_log_file generates a default path when not explicitly set
    and ensures the parent directory is created.
    """
    # Ensure LOG_FILE is not set in environ for this test
    if "LOG_FILE" in os.environ:
        del os.environ["LOG_FILE"]

    with patch("pathlib.Path.mkdir") as mock_mkdir:
        settings = PleskSettings(_env_file=None)
        log_file_path = settings.effective_log_file

        # Check that it attempts to create a directory
        # and returns a path ending with plesk_unified.log
        expected_path_segment = os.path.join("storage", "logs", "plesk_unified.log")
        assert log_file_path.endswith(expected_path_segment)
        assert (
            expected_path_segment in log_file_path
        )  # Ensure the full segment is there

        mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)
