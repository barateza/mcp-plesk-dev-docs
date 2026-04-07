import importlib
import json
from unittest.mock import MagicMock


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
