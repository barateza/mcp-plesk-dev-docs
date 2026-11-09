"""Tests for the bounded query-result cache.

Covers the LRU itself (hit, miss, eviction) and the SearchService wiring:
table-version invalidation, profile switch, explicit invalidation, the disabled
flag, a missing table, and the shallow-copy contract for cache hits.
"""

import logging
from unittest.mock import MagicMock

import pytest

from mcp_plesk_dev_docs.application.services.query_cache import QueryCache
from mcp_plesk_dev_docs.application.services.search_service import SearchService
from mcp_plesk_dev_docs.settings import PleskSettings as Settings

CANDIDATE = {"filename": "a.htm", "text": "content", "_relevance": 0.9}


class _Profile:
    """Minimal profile stub shaped like the real ModelProfile."""

    use_turboquant = False
    reranker_enabled = False
    tq_top_k = 25
    rerank_candidates = 50
    relevance_gate = 0.0

    def __init__(self, name: str = "pro") -> None:
        self.name = name


def _make_service(*, cache_enabled: bool = True, cache_size: int = 8):
    settings = MagicMock(spec=Settings)
    settings.plesk_query_cache_enabled = cache_enabled
    settings.plesk_query_cache_size = cache_size

    model_runtime = MagicMock()
    model_runtime.get_profile.return_value = _Profile()
    model_runtime.get_reranker.return_value = None

    repo = MagicMock()
    repo.get_table.return_value.version = 1

    service = SearchService(
        settings=settings,
        model_runtime=model_runtime,
        storage_runtime=MagicMock(),
        lancedb_repo=repo,
        search_formatter=MagicMock(),
        executor=MagicMock(),
    )
    service._get_search_candidates = MagicMock(return_value=[dict(CANDIDATE)])
    service._rerank_and_score = MagicMock(side_effect=lambda q, c, r: c)
    service._deduplicate_by_filename = MagicMock(side_effect=lambda x, *a, **k: x)
    service._expand_context_with_neighbors = MagicMock(side_effect=lambda x: x)
    return service, model_runtime, repo


# ---------------------------------------------------------------------------
# QueryCache
# ---------------------------------------------------------------------------


def test_get_miss_returns_none_and_counts_miss():
    cache = QueryCache(maxsize=4)

    assert cache.get("missing") is None
    assert cache.stats() == {"hits": 0, "misses": 1, "entries": 0}


def test_set_then_get_returns_value_and_counts_hit():
    cache = QueryCache(maxsize=4)

    cache.set("key", [{"filename": "a.htm"}])

    assert cache.get("key") == [{"filename": "a.htm"}]
    assert cache.stats() == {"hits": 1, "misses": 0, "entries": 1}


def test_lru_evicts_least_recently_used_entry():
    cache = QueryCache(maxsize=2)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.get("a")  # Touch "a" so "b" becomes the least recently used entry.

    cache.set("c", 3)

    assert cache.get("a") == 1
    assert cache.get("b") is None
    assert cache.get("c") == 3
    assert cache.stats()["entries"] == 2


def test_clear_drops_entries_but_keeps_counters():
    cache = QueryCache(maxsize=2)
    cache.set("a", 1)
    cache.get("a")

    cache.clear()

    assert cache.stats() == {"hits": 1, "misses": 0, "entries": 0}


def test_maxsize_must_be_positive():
    with pytest.raises(ValueError):
        QueryCache(maxsize=0)


# ---------------------------------------------------------------------------
# SearchService wiring
# ---------------------------------------------------------------------------


def test_repeat_query_hits_cache_without_rerunning_pipeline():
    service, _, _ = _make_service()

    first = service._search_core("How to reset a password", None)
    second = service._search_core("How to reset a password", None)

    assert second == first
    assert service._get_search_candidates.call_count == 1
    assert service._query_cache.stats() == {"hits": 1, "misses": 1, "entries": 1}


def test_cache_hit_returns_a_shallow_copy_of_the_list():
    service, _, _ = _make_service()
    first = service._search_core("query", None)

    first.append({"filename": "injected.htm"})
    second = service._search_core("query", None)

    assert len(second) == 1


def test_table_version_change_invalidates_cache():
    service, _, repo = _make_service()
    service._search_core("query", None)

    repo.get_table.return_value.version = 2
    service._search_core("query", None)

    assert service._get_search_candidates.call_count == 2


def test_profile_change_invalidates_cache():
    service, model_runtime, _ = _make_service()
    service._search_core("query", None)

    model_runtime.get_profile.return_value = _Profile("turbo")
    service._search_core("query", None)

    assert service._get_search_candidates.call_count == 2


def test_invalidate_drops_cached_results():
    service, _, _ = _make_service()
    service._search_core("query", None)

    service.invalidate()
    service._search_core("query", None)

    assert service._get_search_candidates.call_count == 2


def test_disabled_cache_always_recomputes():
    service, _, _ = _make_service(cache_enabled=False)

    service._search_core("query", None)
    service._search_core("query", None)

    assert service._query_cache is None
    assert service._get_search_candidates.call_count == 2


def test_missing_table_skips_caching_without_raising():
    service, _, repo = _make_service()
    repo.get_table.side_effect = RuntimeError("table not found")

    assert service._search_core("query", None)
    assert service._search_core("query", None)
    assert service._get_search_candidates.call_count == 2


def test_cache_hit_and_miss_are_logged(caplog):
    service, _, _ = _make_service()

    with caplog.at_level(logging.INFO, logger="mcp_plesk_dev_docs"):
        service._search_core("query", None)
        service._search_core("query", None)

    assert "cache=miss" in caplog.text
    assert "cache=hit" in caplog.text
