"""Unit tests for search-pipeline helper functions in plesk_unified.server."""

from unittest.mock import MagicMock
import pytest
import concurrent.futures


# Helper to create a completed Future
def make_completed_future(result_value):
    f = concurrent.futures.Future()
    f.set_result(result_value)
    return f


# ---------------------------------------------------------------------------
# _sigmoid
# ---------------------------------------------------------------------------


def test_sigmoid_zero_maps_to_half():
    from plesk_unified.server import _sigmoid

    assert _sigmoid(0.0) == pytest.approx(0.5)


def test_sigmoid_large_positive_approaches_one():
    from plesk_unified.server import _sigmoid

    assert _sigmoid(10.0) > 0.99


def test_sigmoid_large_negative_approaches_zero():
    from plesk_unified.server import _sigmoid

    assert _sigmoid(-10.0) < 0.01


def test_sigmoid_output_in_unit_interval():
    from plesk_unified.server import _sigmoid

    for x in (-100.0, -1.0, 0.0, 1.0, 100.0):
        v = _sigmoid(x)
        assert 0.0 <= v <= 1.0, f"_sigmoid({x}) = {v} out of [0, 1]"


# ---------------------------------------------------------------------------
# _rerank_and_score
# ---------------------------------------------------------------------------


def test_rerank_and_score_returns_candidates_unchanged_without_reranker():
    from plesk_unified.server import _rerank_and_score

    candidates = [{"text": "a"}, {"text": "b"}]
    assert _rerank_and_score("q", candidates, reranker=None) is candidates


def test_rerank_and_score_returns_empty_list_for_empty_input():
    from plesk_unified.server import _rerank_and_score

    assert _rerank_and_score("q", [], reranker=None) == []


def test_rerank_and_score_sorts_descending_by_sigmoid_of_logits():
    from plesk_unified.server import _rerank_and_score

    reranker = MagicMock()
    # Second candidate has the highest logit → should rank first after reranking
    reranker.predict.return_value = [-2.0, 3.0, 0.0]
    candidates = [
        {"text": "low relevance", "title": "A"},
        {"text": "high relevance", "title": "B"},
        {"text": "mid relevance", "title": "C"},
    ]
    result = _rerank_and_score("q", candidates, reranker)

    assert result[0]["title"] == "B"
    assert result[-1]["title"] == "A"


def test_rerank_and_score_attaches_relevance_scores_in_unit_interval():
    from plesk_unified.server import _rerank_and_score

    reranker = MagicMock()
    reranker.predict.return_value = [0.0, 5.0]
    candidates = [{"text": "x"}, {"text": "y"}]
    result = _rerank_and_score("q", candidates, reranker)

    for r in result:
        assert "_relevance" in r
        assert 0.0 <= r["_relevance"] <= 1.0


# ---------------------------------------------------------------------------
# _deduplicate_by_filename
# ---------------------------------------------------------------------------


def test_deduplicate_keeps_first_occurrence_of_each_filename():
    from plesk_unified.server import _deduplicate_by_filename

    items = [
        {"filename": "a.htm", "_relevance": 0.9},
        {"filename": "b.htm", "_relevance": 0.8},
        {"filename": "a.htm", "_relevance": 0.3},  # duplicate, lower rank
    ]
    result = _deduplicate_by_filename(items)

    assert len(result) == 2
    # First occurrence of "a.htm" (relevance 0.9) must be retained
    a_entry = next(r for r in result if r["filename"] == "a.htm")
    assert a_entry["_relevance"] == 0.9


def test_deduplicate_does_not_alter_list_without_duplicates():
    from plesk_unified.server import _deduplicate_by_filename

    items = [
        {"filename": "a.htm", "_relevance": 0.9},
        {"filename": "b.htm", "_relevance": 0.7},
    ]
    assert _deduplicate_by_filename(items) == items


def test_deduplicate_handles_empty_input():
    from plesk_unified.server import _deduplicate_by_filename

    assert _deduplicate_by_filename([]) == []


# ---------------------------------------------------------------------------
# _build_doc_url / CATEGORY_DOC_BASE_URLS
# ---------------------------------------------------------------------------


def test_build_doc_url_guide_category():
    from plesk_unified.server import _build_doc_url

    url = _build_doc_url("guide", "77178.htm")
    assert url == "https://docs.plesk.com/en-US/obsidian/extensions-guide/77178.htm"


def test_build_doc_url_api_category():
    from plesk_unified.server import _build_doc_url

    url = _build_doc_url("api", "45023.htm")
    assert url == "https://docs.plesk.com/en-US/obsidian/api-rpc/45023.htm"


def test_build_doc_url_cli_category():
    from plesk_unified.server import _build_doc_url

    url = _build_doc_url("cli", "server.htm")
    assert url == "https://docs.plesk.com/en-US/obsidian/cli-linux/server.htm"


def test_build_doc_url_returns_none_for_php_stubs():
    from plesk_unified.server import _build_doc_url

    assert _build_doc_url("php-stubs", "ConfigDefaults.php") is None


def test_build_doc_url_returns_none_for_js_sdk():
    from plesk_unified.server import _build_doc_url

    assert _build_doc_url("js-sdk", "Button.js") is None


def test_build_doc_url_returns_none_for_empty_filename():
    from plesk_unified.server import _build_doc_url

    assert _build_doc_url("guide", "") is None


def test_category_doc_base_urls_covers_all_html_sources():
    from plesk_unified.server import CATEGORY_DOC_BASE_URLS, SOURCES

    html_cats = {src["cat"] for src in SOURCES if src.get("zip_url")}
    assert html_cats == set(CATEGORY_DOC_BASE_URLS.keys())


def test_category_doc_base_urls_end_with_slash():
    from plesk_unified.server import CATEGORY_DOC_BASE_URLS

    for cat, url in CATEGORY_DOC_BASE_URLS.items():
        assert url.endswith("/"), f"Base URL for '{cat}' does not end with '/': {url}"


def test_category_doc_base_urls_do_not_contain_zip():
    from plesk_unified.server import CATEGORY_DOC_BASE_URLS

    for cat, url in CATEGORY_DOC_BASE_URLS.items():
        assert "/zip/" not in url, f"Base URL for '{cat}' still contains '/zip/': {url}"
        assert ".zip" not in url, f"Base URL for '{cat}' still contains '.zip': {url}"


@pytest.mark.asyncio
async def test_search_returns_fallback_when_top_relevance_is_low(monkeypatch):
    import plesk_unified.server as server

    class DummyProfile:
        name = "medium"
        use_turboquant = False
        reranker_enabled = False
        tq_top_k = 25

    fake_table = MagicMock()
    fake_search = MagicMock()
    fake_search.limit.return_value = fake_search
    fake_search.to_list.return_value = [
        {
            "title": "Weak Result",
            "filename": "a.htm",
            "category": "guide",
            "breadcrumb": "",
            "text": "content",
            "_distance": 5.0,
        }
    ]
    fake_table.search.return_value = fake_search

    monkeypatch.setenv("PLESK_MIN_RELEVANCE_THRESHOLD", "0.55")
    monkeypatch.setattr(server, "_get_profile", lambda: DummyProfile())
    monkeypatch.setattr(server, "get_reranker", lambda: None)
    monkeypatch.setattr(server, "get_table", lambda create_new=False: fake_table)
    mock_executor = MagicMock(spec=concurrent.futures.ThreadPoolExecutor)
    mock_executor.submit.side_effect = lambda f, *args, **kwargs: make_completed_future(
        f(*args, **kwargs)
    )
    monkeypatch.setattr(server, "_executor", mock_executor)  # Mock the executor

    result = await server.search_plesk_unified("query")
    assert result == "I could not find a reliable answer."


@pytest.mark.asyncio
async def test_search_returns_results_when_relevance_is_high(monkeypatch):
    import plesk_unified.server as server

    class DummyProfile:
        name = "medium"
        use_turboquant = False
        reranker_enabled = False
        tq_top_k = 25

    fake_table = MagicMock()
    fake_search = MagicMock()
    fake_search.limit.return_value = fake_search
    fake_search.to_list.return_value = [
        {
            "title": "Strong Result",
            "filename": "a.htm",
            "category": "guide",
            "breadcrumb": "Path",
            "text": "content",
            "_distance": 0.1,
        }
    ]
    fake_table.search.return_value = fake_search

    monkeypatch.setenv("PLESK_MIN_RELEVANCE_THRESHOLD", "0.55")
    monkeypatch.setattr(server, "_get_profile", lambda: DummyProfile())
    monkeypatch.setattr(server, "get_reranker", lambda: None)
    monkeypatch.setattr(server, "get_table", lambda create_new=False: fake_table)
    mock_executor = MagicMock(spec=concurrent.futures.ThreadPoolExecutor)
    mock_executor.submit.side_effect = lambda f, *args, **kwargs: make_completed_future(
        f(*args, **kwargs)
    )
    monkeypatch.setattr(server, "_executor", mock_executor)  # Mock the executor

    result = await server.search_plesk_unified("query")
    assert "Strong Result" in result
