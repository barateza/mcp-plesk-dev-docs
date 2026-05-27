"""
Unit tests for search-pipeline helper functions.
"""

from unittest.mock import MagicMock
import pytest
import concurrent.futures
from pathlib import Path

# New imports
from mcp_plesk_dev_docs.settings import PleskSettings as Settings
from mcp_plesk_dev_docs.application.services.search_service import SearchService
from mcp_plesk_dev_docs.config.sources import SourceCatalog
from mcp_plesk_dev_docs.domain.models import SourceDefinition
from mcp_plesk_dev_docs.domain.models import CategoryEnum
from mcp_plesk_dev_docs.formatting.search_formatter import SearchFormatter


# Helper to create a completed Future
def make_completed_future(result_value):
    f = concurrent.futures.Future()
    f.set_result(result_value)
    return f


@pytest.fixture
def search_service_fixture():
    mock_settings = MagicMock(spec=Settings)
    mock_settings.plesk_enable_sampling = False
    mock_settings.plesk_rerank_candidates = 50
    mock_settings.plesk_min_relevance_threshold = (
        None  # Default to None for flexibility
    )

    mock_model_runtime = MagicMock()
    mock_profile = MagicMock()
    mock_profile.name = "medium"
    mock_profile.use_turboquant = False
    mock_profile.reranker_enabled = False
    mock_profile.tq_top_k = 25
    mock_model_runtime.get_profile.return_value = mock_profile
    mock_model_runtime.get_reranker.return_value = None

    mock_storage_runtime = MagicMock()
    mock_lancedb_repo = MagicMock()
    mock_turboquant_repo = MagicMock()
    mock_search_formatter = MagicMock(spec=SearchFormatter)
    mock_search_formatter.format_markdown.return_value = "Formatted results."

    # Need a mock SourceCatalog for SearchFormatter
    mock_source_catalog = MagicMock(spec=SourceCatalog)
    mock_search_formatter.source_catalog = mock_source_catalog

    mock_executor = MagicMock(spec=concurrent.futures.ThreadPoolExecutor)
    mock_executor.submit.side_effect = lambda fn, *args, **kwargs: (
        make_completed_future(fn(*args, **kwargs))
    )

    search_service = SearchService(
        mock_settings,
        mock_model_runtime,
        mock_storage_runtime,
        mock_lancedb_repo,
        mock_turboquant_repo,
        mock_search_formatter,
        mock_executor,
    )
    return (
        search_service,
        mock_settings,
        mock_model_runtime,
        mock_lancedb_repo,
        mock_search_formatter,
    )


# ---------------------------------------------------------------------------
# _sigmoid
# ---------------------------------------------------------------------------


def test_sigmoid_zero_maps_to_half(search_service_fixture):
    search_service, _, _, _, _ = search_service_fixture
    assert search_service._sigmoid(0.0) == pytest.approx(0.5)


def test_sigmoid_large_positive_approaches_one(search_service_fixture):
    search_service, _, _, _, _ = search_service_fixture
    assert search_service._sigmoid(10.0) > 0.99


def test_sigmoid_large_negative_approaches_zero(search_service_fixture):
    search_service, _, _, _, _ = search_service_fixture
    assert search_service._sigmoid(-10.0) < 0.01


def test_sigmoid_output_in_unit_interval(search_service_fixture):
    search_service, _, _, _, _ = search_service_fixture
    for x in (-100.0, -1.0, 0.0, 1.0, 100.0):
        v = search_service._sigmoid(x)
        assert 0.0 <= v <= 1.0, f"_sigmoid({x}) = {v} out of [0, 1]"


# ---------------------------------------------------------------------------
# _rerank_and_score
# ---------------------------------------------------------------------------


def test_rerank_and_score_returns_candidates_unchanged_without_reranker(
    search_service_fixture,
):
    search_service, _, _, _, _ = search_service_fixture
    candidates = [{"text": "a"}, {"text": "b"}]
    assert (
        search_service._rerank_and_score("q", candidates, reranker=None) is candidates
    )


def test_rerank_and_score_returns_empty_list_for_empty_input(search_service_fixture):
    search_service, _, _, _, _ = search_service_fixture
    assert search_service._rerank_and_score("q", [], reranker=None) == []


def test_rerank_and_score_sorts_descending_by_sigmoid_of_logits(
    search_service_fixture,
):
    search_service, _, _, _, _ = search_service_fixture
    reranker = MagicMock()
    # Second candidate has the highest logit → should rank first after reranking
    reranker.predict.return_value = [-2.0, 3.0, 0.0]
    candidates = [
        {"text": "low relevance", "title": "A"},
        {"text": "high relevance", "title": "B"},
        {"text": "mid relevance", "title": "C"},
    ]
    result = search_service._rerank_and_score("q", candidates, reranker)

    assert result[0]["title"] == "B"
    assert result[-1]["title"] == "A"


def test_rerank_and_score_attaches_relevance_scores_in_unit_interval(
    search_service_fixture,
):
    search_service, _, _, _, _ = search_service_fixture
    reranker = MagicMock()
    reranker.predict.return_value = [0.0, 5.0]
    candidates = [{"text": "x"}, {"text": "y"}]
    result = search_service._rerank_and_score("q", candidates, reranker)

    for r in result:
        assert "_relevance" in r
        assert 0.0 <= r["_relevance"] <= 1.0


# ---------------------------------------------------------------------------
# _deduplicate_by_filename
# ---------------------------------------------------------------------------


def test_deduplicate_keeps_first_occurrence_of_each_filename(search_service_fixture):
    search_service, _, _, _, _ = search_service_fixture
    items = [
        {"filename": "a.htm", "_relevance": 0.9},
        {"filename": "b.htm", "_relevance": 0.8},
        {"filename": "a.htm", "_relevance": 0.3},  # duplicate, lower rank
    ]
    result = search_service._deduplicate_by_filename(items)

    assert len(result) == 2
    # First occurrence of "a.htm" (relevance 0.9) must be retained
    a_entry = next(r for r in result if r["filename"] == "a.htm")
    assert a_entry["_relevance"] == 0.9


def test_deduplicate_does_not_alter_list_without_duplicates(search_service_fixture):
    search_service, _, _, _, _ = search_service_fixture
    items = [
        {"filename": "a.htm", "_relevance": 0.9},
        {"filename": "b.htm", "_relevance": 0.7},
    ]
    assert search_service._deduplicate_by_filename(items) == items


def test_deduplicate_handles_empty_input(search_service_fixture):
    search_service, _, _, _, _ = search_service_fixture
    assert search_service._deduplicate_by_filename([]) == []


# ---------------------------------------------------------------------------
# SourceDefinition (formerly _build_doc_url / CATEGORY_DOC_BASE_URLS related)
# ---------------------------------------------------------------------------


def test_source_definition_build_doc_url_guide_category():
    source_def = SourceDefinition(
        category=CategoryEnum.GUIDE,
        path=Path("."),
        source_type="html",
        zip_url="https://docs.plesk.com/en-US/obsidian/zip/extensions-guide.zip",
    )
    url = source_def.build_doc_url("77178.htm")
    assert url == "https://docs.plesk.com/en-US/obsidian/extensions-guide/77178.htm"


def test_source_definition_build_doc_url_api_category():
    source_def = SourceDefinition(
        category=CategoryEnum.API,
        path=Path("."),
        source_type="html",
        zip_url="https://docs.plesk.com/en-US/obsidian/zip/api-rpc.zip",
    )
    url = source_def.build_doc_url("45023.htm")
    assert url == "https://docs.plesk.com/en-US/obsidian/api-rpc/45023.htm"


def test_source_definition_build_doc_url_cli_category():
    source_def = SourceDefinition(
        category=CategoryEnum.CLI,
        path=Path("."),
        source_type="html",
        zip_url="https://docs.plesk.com/en-US/obsidian/zip/cli-linux.zip",
    )
    url = source_def.build_doc_url("server.htm")
    assert url == "https://docs.plesk.com/en-US/obsidian/cli-linux/server.htm"


def test_source_definition_build_doc_url_returns_none_for_php_stubs():
    source_def = SourceDefinition(
        category=CategoryEnum.PHP_STUBS,
        path=Path("."),
        source_type="php",
        repo_url="https://github.com/plesk/pm-api-stubs.git",  # No zip_url
    )
    assert source_def.build_doc_url("ConfigDefaults.php") is None


def test_source_definition_build_doc_url_returns_none_for_js_sdk():
    source_def = SourceDefinition(
        category=CategoryEnum.JS_SDK,
        path=Path("."),
        source_type="js",
        repo_url="https://github.com/plesk/plesk-ext-sdk.git",  # No zip_url
    )
    assert source_def.build_doc_url("Button.js") is None


def test_source_definition_build_doc_url_returns_none_for_empty_filename():
    source_def = SourceDefinition(
        category=CategoryEnum.GUIDE,
        path=Path("."),
        source_type="html",
        zip_url="https://docs.plesk.com/en-US/obsidian/zip/extensions-guide.zip",
    )
    assert source_def.build_doc_url("") is None


def test_source_definition_doc_base_url_ends_with_slash():
    source_def = SourceDefinition(
        category=CategoryEnum.GUIDE,
        path=Path("."),
        source_type="html",
        zip_url="https://docs.plesk.com/en-US/obsidian/zip/extensions-guide.zip",
    )
    assert source_def.doc_base_url.endswith("/")


def test_source_definition_doc_base_url_does_not_contain_zip():
    source_def = SourceDefinition(
        category=CategoryEnum.GUIDE,
        path=Path("."),
        source_type="html",
        zip_url="https://docs.plesk.com/en-US/obsidian/zip/extensions-guide.zip",
    )
    assert "/zip/" not in source_def.doc_base_url
    assert ".zip" not in source_def.doc_base_url


def test_source_catalog_default_covers_all_html_sources():
    # This tests the SourceCatalog.default method directly
    # and implicitly the SourceDefinition's doc_base_url property.
    mock_kb_dir = Path("/tmp/mock_kb")  # Dummy path
    source_catalog = SourceCatalog.default(mock_kb_dir)

    html_source_defs = [s for s in source_catalog.all() if s.source_type == "html"]
    html_cats = {s.category.value for s in html_source_defs}

    expected_html_cats = {"api", "cli", "guide"}  # Based on SourceCatalog.default
    assert html_cats == expected_html_cats

    for src_def in html_source_defs:
        assert src_def.doc_base_url is not None
        assert src_def.doc_base_url.endswith("/")
        assert "/zip/" not in src_def.doc_base_url
        assert ".zip" not in src_def.doc_base_url


# ---------------------------------------------------------------------------
# SearchService.search integration tests (formerly legacy_server.search_mcp_plesk_dev_docs)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_returns_fallback_when_top_relevance_is_low(
    search_service_fixture,
):
    (
        search_service,
        mock_settings,
        mock_model_runtime,
        mock_lancedb_repo,
        mock_search_formatter,
    ) = search_service_fixture

    class DummyProfile:
        name = "medium"
        use_turboquant = False
        reranker_enabled = False
        tq_top_k = 25
        rerank_candidates = 50

    mock_model_runtime.get_profile.return_value = DummyProfile()
    mock_settings.plesk_min_relevance_threshold = 0.55

    # Mock _get_search_candidates to return a low-relevance result
    search_service._get_search_candidates = MagicMock(
        return_value=[
            {
                "title": "Weak Result",
                "filename": "a.htm",
                "category": "guide",
                "breadcrumb": "",
                "text": "content",
                "_distance": 5.0,
            }
        ]
    )
    # Mock _rerank_and_score to simulate a low relevance score after reranking
    search_service._rerank_and_score = MagicMock(
        return_value=[
            {
                "title": "Weak Result",
                "filename": "a.htm",
                "category": "guide",
                "breadcrumb": "",
                "text": "content",
                "_distance": 5.0,
                "_relevance": 0.4,  # Below threshold
            }
        ]
    )
    search_service._deduplicate_by_filename = MagicMock(
        side_effect=lambda x, *args, **kwargs: x
    )
    search_service._expand_context_with_neighbors = MagicMock(side_effect=lambda x: x)

    results, error_msg = await search_service.search("query")
    assert error_msg == "I could not find a reliable answer."
    assert results == []
    search_service._get_search_candidates.assert_called_once()
    search_service._rerank_and_score.assert_called_once()
    search_service._deduplicate_by_filename.assert_called_once()
    mock_search_formatter.format_markdown.assert_not_called()  # Short-circuited


@pytest.mark.asyncio
async def test_search_returns_results_when_relevance_is_high(search_service_fixture):
    (
        search_service,
        mock_settings,
        mock_model_runtime,
        mock_lancedb_repo,
        mock_search_formatter,
    ) = search_service_fixture

    class DummyProfile:
        name = "medium"
        use_turboquant = False
        reranker_enabled = False
        tq_top_k = 25
        rerank_candidates = 50

    mock_model_runtime.get_profile.return_value = DummyProfile()
    mock_settings.plesk_min_relevance_threshold = 0.55

    # Mock _get_search_candidates to return a high-relevance result
    search_service._get_search_candidates = MagicMock(
        return_value=[
            {
                "title": "Strong Result",
                "filename": "a.htm",
                "category": "guide",
                "breadcrumb": "Path",
                "text": "content",
                "_distance": 0.1,
            }
        ]
    )
    # Mock _rerank_and_score to simulate a high relevance score after reranking
    search_service._rerank_and_score = MagicMock(
        return_value=[
            {
                "title": "Strong Result",
                "filename": "a.htm",
                "category": "guide",
                "breadcrumb": "Path",
                "text": "content",
                "_distance": 0.1,
                "_relevance": 0.8,  # Above threshold
            }
        ]
    )
    search_service._deduplicate_by_filename = MagicMock(
        side_effect=lambda x, *args, **kwargs: x
    )
    search_service._expand_context_with_neighbors = MagicMock(side_effect=lambda x: x)

    results, error_msg = await search_service.search("query")
    assert error_msg is None
    assert len(results) == 1
    assert results[0]["title"] == "Strong Result"

    search_service._get_search_candidates.assert_called_once()
    search_service._rerank_and_score.assert_called_once()
    search_service._deduplicate_by_filename.assert_called_once()
