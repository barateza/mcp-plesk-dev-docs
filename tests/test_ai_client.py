import json
from unittest.mock import MagicMock, patch

import pytest

from plesk_unified.ai_client import DEFAULT_MODELS, AIClient


@pytest.fixture
def ai_client():
    return AIClient(api_key="test_key")


def test_generate_description_empty_text(ai_client):
    assert ai_client.generate_description("") == "File unreadable."
    assert ai_client.generate_description("   ") == "File unreadable."


@patch("plesk_unified.ai_client.requests.post")
def test_generate_description_success_first_model(mock_post, ai_client):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "This is a test description."}}]
    }
    mock_post.return_value = mock_response

    result = ai_client.generate_description("Some text")

    assert result == "This is a test description."
    assert mock_post.call_count == 1
    # Ensure it used the first default model
    call_args = json.loads(mock_post.call_args[1]["data"])
    assert call_args["model"] == DEFAULT_MODELS[0]


@patch("plesk_unified.ai_client.requests.post")
def test_generate_description_fallback(mock_post, ai_client):
    # First model fails (500), second succeeds (200)
    mock_fail = MagicMock()
    mock_fail.status_code = 500

    mock_success = MagicMock()
    mock_success.status_code = 200
    mock_success.json.return_value = {
        "choices": [{"message": {"content": "Fallback description."}}]
    }

    mock_post.side_effect = [mock_fail, mock_success]

    result = ai_client.generate_description("Some text")

    assert result == "Fallback description."
    assert mock_post.call_count == 2

    # Check that second model was used
    import json

    call_args = json.loads(mock_post.call_args_list[1][1]["data"])
    assert call_args["model"] == DEFAULT_MODELS[1]


@patch("plesk_unified.ai_client.requests.post")
def test_generate_description_all_fail(mock_post, ai_client):
    mock_fail = MagicMock()
    mock_fail.status_code = 500
    mock_post.return_value = mock_fail

    result = ai_client.generate_description("Some text")

    assert result == "Description unavailable."
    assert mock_post.call_count == len(DEFAULT_MODELS)


@patch("plesk_unified.ai_client.requests.post")
def test_evaluate_ragas_score_success(mock_post, ai_client):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"choices": [{"message": {"content": "0.85"}}]}
    mock_post.return_value = mock_response

    score = ai_client.evaluate_ragas_score("Judge this.")

    assert score == 0.85
    assert mock_post.call_count == 1


@patch("plesk_unified.ai_client.requests.post")
def test_evaluate_ragas_score_parsing(mock_post, ai_client):
    # Tests parsing float out of text
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "The score is 0.95."}}]
    }
    mock_post.return_value = mock_response

    score = ai_client.evaluate_ragas_score("Judge this.")

    assert score == 0.95


@patch("plesk_unified.ai_client.requests.post")
def test_evaluate_ragas_score_fail(mock_post, ai_client):
    mock_fail = MagicMock()
    mock_fail.status_code = 500
    mock_post.return_value = mock_fail

    score = ai_client.evaluate_ragas_score("Judge this.")

    assert score == 0.0
