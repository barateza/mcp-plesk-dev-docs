import importlib
import json
from unittest.mock import MagicMock

import pytest


def test_get_optimal_device_honors_force_device(monkeypatch):
    monkeypatch.setenv("FORCE_DEVICE", "mps")

    import plesk_unified.platform_utils as platform_utils

    importlib.reload(platform_utils)

    assert platform_utils.get_optimal_device() == "mps"


def test_server_detect_device_caches_result(monkeypatch):
    import plesk_unified.server as server

    calls = {"count": 0}

    def fake_get_optimal_device():
        calls["count"] += 1
        return "cpu"

    monkeypatch.setattr(
        server.platform_utils,
        "get_optimal_device",
        fake_get_optimal_device,
    )
    monkeypatch.setattr(server, "_detected_device", None)

    assert server._detect_device() == "cpu"
    assert server._detect_device() == "cpu"
    assert calls["count"] == 1


def test_warmup_server_preloads_without_indexing(monkeypatch):
    import plesk_unified.server as server

    calls = {
        "embedding": 0,
        "reranker": 0,
        "table": 0,
        "tq_load": 0,
    }

    class DummyProfile:
        name = "full-tq"
        embed_model = "model"
        reranker_model = "reranker"
        use_turboquant = True

    def fake_embedding_model():
        calls["embedding"] += 1
        return MagicMock()

    def fake_reranker():
        calls["reranker"] += 1
        return MagicMock()

    def fake_table(create_new=False):
        calls["table"] += 1
        return MagicMock()

    def fake_tq_index_path():
        return server.Path("/tmp/full-tq.pkl")

    def fake_load_tq_index():
        calls["tq_load"] += 1
        return MagicMock()

    monkeypatch.setattr(server, "_get_profile", lambda: DummyProfile())
    monkeypatch.setattr(server, "get_embedding_model", fake_embedding_model)
    monkeypatch.setattr(server, "get_reranker", fake_reranker)
    monkeypatch.setattr(server, "get_table", fake_table)
    monkeypatch.setattr(server, "_get_tq_index_path", fake_tq_index_path)
    monkeypatch.setattr(server, "_load_tq_index", fake_load_tq_index)
    monkeypatch.setattr(server, "_tq_index", None)

    result = server.warmup_server()

    assert "Warmup started" in result
    assert calls["embedding"] == 1
    assert calls["reranker"] == 1
    assert calls["table"] == 1
    assert calls["tq_load"] == 0


def test_warmup_server_returns_running_when_already_active(monkeypatch):
    import plesk_unified.server as server

    monkeypatch.setattr(server, "_warmup_state", "running")
    result = server.warmup_server()
    assert result == "Warmup already running."


def test_maybe_start_background_warmup_starts_daemon_thread(monkeypatch):
    import plesk_unified.server as server

    started = {"value": False}

    class FakeThread:
        def __init__(self, target, name, daemon):
            self.target = target
            self.name = name
            self.daemon = daemon
            self._alive = False

        def start(self):
            started["value"] = True
            self._alive = True

        def is_alive(self):
            return self._alive

    monkeypatch.setattr(server, "_env_flag", lambda _name: True)
    monkeypatch.setattr(server.threading, "Thread", FakeThread)
    monkeypatch.setattr(server, "_warmup_thread", None)

    server._maybe_start_background_warmup()

    assert started["value"] is True
    assert server._warmup_thread is not None


def test_daemon_health_reports_expected_fields(monkeypatch, tmp_path):
    import plesk_unified.server as server

    class DummyProfile:
        name = "full-tq"
        use_turboquant = True

    class FakeDb:
        def open_table(self, _name):
            return None

    artifact = tmp_path / "full-tq.pkl"
    artifact.write_text("ok")

    monkeypatch.setattr(server, "_get_profile", lambda: DummyProfile())
    monkeypatch.setattr(server, "_detect_device", lambda: "cpu")
    monkeypatch.setattr(server, "_get_tq_index_path", lambda: artifact)
    monkeypatch.setattr(server.lancedb, "connect", lambda _path: FakeDb())
    monkeypatch.setattr(server, "_tq_index", None)
    monkeypatch.setattr(server, "_warmup_state", "ready")
    monkeypatch.setattr(server, "_warmup_error", None)
    monkeypatch.setattr(server, "_warmup_thread", None)
    monkeypatch.setattr(server, "_env_flag", lambda _name: True)

    payload = json.loads(server.daemon_health())

    assert payload["profile"] == "full-tq"
    assert payload["device"] == "cpu"
    assert payload["auto_warmup_enabled"] is True
    assert payload["warmup_state"] == "ready"
    assert payload["table_ready"] is True
    assert payload["turboquant_expected"] is True
    assert payload["turboquant_artifact_exists"] is True
    assert payload["refresh_mode"] == "synchronous-only"


def test_load_toc_map_is_cached(monkeypatch, tmp_path):
    import plesk_unified.io_utils as io_utils

    toc_path = tmp_path / "toc.json"
    toc_path.write_text(json.dumps([{"text": "A", "url": "a.htm"}]))

    io_utils.load_toc_map.cache_clear()

    original_read_text = type(toc_path).read_text
    calls = {"count": 0}

    def wrapped_read_text(self, *args, **kwargs):
        calls["count"] += 1
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(type(toc_path), "read_text", wrapped_read_text, raising=False)

    first = io_utils.load_toc_map(toc_path.parent)
    second = io_utils.load_toc_map(toc_path.parent)

    assert first == second
    assert calls["count"] == 1


# --- Category allowlist tests ---


def _make_dummy_profile(use_turboquant=False):
    class DummyProfile:
        name = "full"
        embed_model = "model"
        reranker_model = "reranker"
        reranker_enabled = False
        tq_top_k = 25

    DummyProfile.use_turboquant = use_turboquant
    return DummyProfile()


def test_search_rejects_invalid_category(monkeypatch):
    import plesk_unified.server as server

    monkeypatch.setattr(server, "_get_profile", lambda: _make_dummy_profile())

    with pytest.raises(ValueError, match="Invalid category"):
        server.search_plesk_unified("some query", category="'; DROP TABLE plesk_knowledge; --")


def test_search_accepts_valid_category(monkeypatch):
    import plesk_unified.server as server

    fake_table = MagicMock()
    fake_search = MagicMock()
    fake_search.where.return_value = fake_search
    fake_search.limit.return_value = fake_search
    fake_search.to_list.return_value = []
    fake_table.search.return_value = fake_search

    monkeypatch.setattr(server, "_get_profile", lambda: _make_dummy_profile())
    monkeypatch.setattr(server, "get_table", lambda: fake_table)

    result = server.search_plesk_unified("some query", category="api")
    assert isinstance(result, str)
    fake_search.where.assert_called_once_with("category = 'api'")


def test_search_with_no_category_is_allowed(monkeypatch):
    import plesk_unified.server as server

    fake_table = MagicMock()
    fake_search = MagicMock()
    fake_search.limit.return_value = fake_search
    fake_search.to_list.return_value = []
    fake_table.search.return_value = fake_search

    monkeypatch.setattr(server, "_get_profile", lambda: _make_dummy_profile())
    monkeypatch.setattr(server, "get_table", lambda: fake_table)

    result = server.search_plesk_unified("some query", category=None)
    assert isinstance(result, str)
    fake_search.where.assert_not_called()


def test_refresh_rejects_invalid_category(monkeypatch):
    import plesk_unified.server as server

    fake_table = MagicMock()
    fake_table.search.return_value.where.return_value.select.return_value.limit.return_value.to_list.return_value = []

    monkeypatch.setattr(server, "_get_profile", lambda: _make_dummy_profile())
    monkeypatch.setattr(server, "get_table", lambda create_new=False: fake_table)

    with pytest.raises(ValueError, match="Invalid category"):
        server.refresh_knowledge(target_category="'; DROP TABLE plesk_knowledge; --")


def test_refresh_accepts_valid_category(monkeypatch):
    import plesk_unified.server as server

    fake_table = MagicMock()
    fake_search = MagicMock()
    fake_search.where.return_value = fake_search
    fake_search.select.return_value = fake_search
    fake_search.limit.return_value = fake_search
    fake_search.to_list.return_value = []
    fake_table.search.return_value = fake_search

    monkeypatch.setattr(server, "_get_profile", lambda: _make_dummy_profile())
    monkeypatch.setattr(server, "get_table", lambda create_new=False: fake_table)
    monkeypatch.setattr(server.io_utils, "ensure_source_exists", lambda _s: False)

    result = server.refresh_knowledge(target_category="cli")
    assert "SKIPPED" in result or "Finished" in result


def test_refresh_with_all_is_allowed(monkeypatch):
    import plesk_unified.server as server

    fake_table = MagicMock()

    monkeypatch.setattr(server, "_get_profile", lambda: _make_dummy_profile())
    monkeypatch.setattr(server, "get_table", lambda create_new=False: fake_table)
    monkeypatch.setattr(server.io_utils, "ensure_source_exists", lambda _s: False)

    result = server.refresh_knowledge(target_category="all")
    assert isinstance(result, str)
