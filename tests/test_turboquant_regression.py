from __future__ import annotations

import json
from types import SimpleNamespace

import numpy as np
import pytest
import torch
from safetensors import safe_open
from safetensors.torch import save_file

from mcp_plesk_dev_docs.infrastructure import turboquant_index
from mcp_plesk_dev_docs.infrastructure.parsers import chunking
from mcp_plesk_dev_docs.infrastructure.runtime import storage_runtime
from tq_search import LloydMaxCodebook, TurboQuantMSE, TurboQuantProd

_PROFILE = SimpleNamespace(
    name="full-tq",
    embed_model="fake/embed-model",
    embed_dim=8,
    tq_bits=3,
    use_turboquant=True,
)


def test_turboquant_package_exports():
    assert TurboQuantMSE.__name__ == "TurboQuantMSE"
    assert TurboQuantProd.__name__ == "TurboQuantProd"
    assert LloydMaxCodebook.__name__ == "LloydMaxCodebook"


def test_lloyd_max_codebook_is_symmetric_and_roundtrips():
    codebook = LloydMaxCodebook(d=64, bits=2)

    centroids = codebook.centroids
    assert torch.allclose(centroids, -torch.flip(centroids, dims=[0]), atol=1e-2)

    values = torch.tensor([-0.1, 0.0, 0.1], dtype=torch.float32)
    indices = codebook.quantize(values)
    reconstructed = codebook.dequantize(indices)

    assert indices.shape == values.shape
    assert reconstructed.shape == values.shape
    assert torch.isfinite(reconstructed).all()


def test_turboquant_index_normalizes_and_filters_by_category(monkeypatch):
    captured_inputs: list[torch.Tensor] = []

    class DummyTurboQuantProd:
        def __init__(self, dim: int, bits: int, device: str = "cpu"):
            self.dim = dim
            self.bits = bits
            self.device = device

        def quantize(self, x: torch.Tensor) -> dict[str, torch.Tensor]:
            captured_inputs.append(x.detach().cpu())
            n_rows = x.shape[0]
            scores = torch.arange(n_rows, dtype=torch.float32)
            return {
                "mse_indices": torch.arange(n_rows, dtype=torch.int64).unsqueeze(1),
                "qjl_signs": torch.ones(n_rows, 1, dtype=torch.float32),
                "residual_norm": torch.ones(n_rows, dtype=torch.float32),
                "score": scores,
            }

        def inner_product(
            self, query: torch.Tensor, compressed: dict[str, torch.Tensor]
        ) -> torch.Tensor:
            return compressed["score"]

    monkeypatch.setattr(turboquant_index, "TurboQuantProd", DummyTurboQuantProd)

    index = turboquant_index.TurboQuantIndex(dim=3, bits=3, device="cpu")
    vecs = np.asarray(
        [
            [3.0, 0.0, 0.0],
            [0.0, 4.0, 0.0],
            [0.0, 0.0, 5.0],
        ],
        dtype=np.float32,
    )
    metas = [
        {"filename": "a", "category": "docs"},
        {"filename": "b", "category": "docs"},
        {"filename": "c", "category": "api"},
    ]

    index.add(vecs, metas)

    assert len(captured_inputs) == 1
    norms = torch.linalg.norm(captured_inputs[0], dim=-1)
    assert torch.allclose(norms, torch.ones_like(norms), atol=1e-6)

    results = index.search(
        np.asarray([1.0, 0.0, 0.0], dtype=np.float32),
        category="docs",
    )
    assert [meta["filename"] for meta, _score in results] == ["b", "a"]
    assert all(meta["category"] == "docs" for meta, _score in results)

    assert (
        index.search(
            np.asarray([1.0, 0.0, 0.0], dtype=np.float32),
            category="missing",
        )
        == []
    )


def test_turboquant_index_add_concatenates_once_on_flush(monkeypatch):
    """Batched adds must produce the same tensor as one concat, with one cat."""

    class EchoTurboQuantProd:
        def __init__(self, dim: int, bits: int, device: str = "cpu"):
            self.dim = dim
            self.bits = bits
            self.device = device

        def quantize(self, x: torch.Tensor) -> dict[str, torch.Tensor]:
            return {"packed": x.detach().cpu()}

    monkeypatch.setattr(turboquant_index, "TurboQuantProd", EchoTurboQuantProd)

    real_cat = torch.cat
    concat_sizes: list[int] = []

    def counting_cat(tensors, dim=0, **kwargs):
        concat_sizes.append(len(tensors))
        return real_cat(tensors, dim=dim, **kwargs)

    monkeypatch.setattr(torch, "cat", counting_cat)

    vecs = np.asarray(
        [
            [1.0, 2.0, 3.0, 4.0],
            [4.0, 3.0, 2.0, 1.0],
            [1.0, 0.0, 1.0, 0.0],
            [0.0, 1.0, 0.0, 1.0],
            [2.0, 2.0, 2.0, 2.0],
            [5.0, 1.0, 5.0, 1.0],
        ],
        dtype=np.float32,
    )
    metas = [{"filename": f"f{i}", "category": "docs"} for i in range(6)]

    batched = turboquant_index.TurboQuantIndex(dim=4, bits=3, device="cpu")
    for start in range(0, len(vecs), 2):
        batched.add(vecs[start : start + 2], metas[start : start + 2])

    assert concat_sizes == [], "add() must not concatenate per batch"
    batched.flush()
    assert concat_sizes == [3], "flush() must concatenate all buffered batches once"

    one_shot = turboquant_index.TurboQuantIndex(dim=4, bits=3, device="cpu")
    one_shot.add(vecs, metas)
    one_shot.flush()

    assert torch.equal(
        batched.compressed_db["packed"], one_shot.compressed_db["packed"]
    )
    assert len(batched) == len(metas)


# ---------------------------------------------------------------------------
# TurboQuant cache v2 (safetensors + JSON header)
# ---------------------------------------------------------------------------


class _FakeRuntime:
    def __init__(self, profile: SimpleNamespace):
        self._profile = profile

    def get_profile(self) -> SimpleNamespace:
        return self._profile

    def detect_device(self) -> str:
        return "cpu"


class _FakeQuery:
    def __init__(self, rows: list[dict]):
        self._rows = rows

    def limit(self, _n: int) -> "_FakeQuery":
        return self

    def to_list(self) -> list[dict]:
        return self._rows


class _FakeTable:
    def __init__(self, rows: list[dict], version: int):
        self._rows = rows
        self.version = version

    def search(self) -> _FakeQuery:
        return _FakeQuery(self._rows)


def _make_storage(
    tmp_path, rows: list[dict] | None = None, version: int = 1
) -> tuple[storage_runtime.StorageRuntime, _FakeTable]:
    storage = storage_runtime.StorageRuntime(tmp_path, _FakeRuntime(_PROFILE))
    table = _FakeTable(rows or [], version)
    storage.get_table = lambda create_new=False: table  # type: ignore[method-assign]
    return storage, table


def _docs(count: int = 6) -> list[dict]:
    rng = np.random.default_rng(0)
    vecs = rng.normal(size=(count, _PROFILE.embed_dim)).astype(np.float32)
    return [
        {
            "vector": vecs[index].tolist(),
            "text": f"doc {index}",
            "title": f"Doc {index}",
            "filename": f"f{index}.htm",
            "category": "docs" if index % 2 == 0 else "api",
            "breadcrumb": "root",
            "doctype": "guide",
            "chunk_hash": f"h{index}",
            "chunk_id": index,
        }
        for index in range(count)
    ]


def test_tq_cache_safetensors_roundtrip(tmp_path):
    storage, _table = _make_storage(tmp_path, version=7)
    index = storage._create_tq_index()

    rows = _docs()
    corpus = np.asarray([row["vector"] for row in rows], dtype=np.float32)
    metas = [
        {"filename": row["filename"], "category": row["category"], "text": row["text"]}
        for row in rows
    ]
    index.add(corpus, metas)
    storage.save_tq_index(index)

    path = storage.get_tq_index_path()
    assert path.suffix == ".safetensors"
    assert path.exists()

    with safe_open(str(path), framework="pt", device="cpu") as handle:
        header = json.loads(handle.metadata()["tq_header"])
        assert header == {
            "format": "tq-v2",
            "chunk_version": chunking.CHUNK_VERSION,
            "table_version": 7,
            "model": _PROFILE.embed_model,
            "bits": _PROFILE.tq_bits,
            "dim": _PROFILE.embed_dim,
        }
        assert set(handle.keys()) == set(index.compressed_db)

    loaded = storage.load_tq_index()
    assert loaded is not None
    assert isinstance(loaded, turboquant_index.TurboQuantIndex)
    assert len(loaded) == len(metas)
    assert loaded._meta == metas
    assert loaded._category_to_indices == index._category_to_indices
    for key, tensor in index.compressed_db.items():
        assert torch.equal(loaded.compressed_db[key], tensor)

    query = np.asarray(corpus[0], dtype=np.float32)
    results = loaded.search(query, top_k=2)
    assert len(results) == 2
    assert all(meta in metas for meta, _score in results)


def _tamper_header(path, mutate=None, metadata: bool = True) -> None:
    with safe_open(str(path), framework="pt", device="cpu") as handle:
        header = json.loads(handle.metadata()["tq_header"])
        tensors = {key: handle.get_tensor(key) for key in handle.keys()}

    if metadata:
        mutate(header)
        save_file(tensors, str(path), metadata={"tq_header": json.dumps(header)})
    else:
        save_file(tensors, str(path))


@pytest.mark.parametrize("invalid_header", ["missing", "stale-table-version"])
def test_tq_cache_invalid_header_triggers_rebuild(tmp_path, invalid_header):
    storage, table = _make_storage(tmp_path, rows=_docs(), version=11)

    original_build = storage.build_tq_index_from_table
    builds: list[int] = []

    def counting_build():
        builds.append(table.version)
        return original_build()

    storage.build_tq_index_from_table = counting_build  # type: ignore[method-assign]

    storage.get_tq_index()
    assert builds == [11]

    path = storage.get_tq_index_path()
    if invalid_header == "missing":
        _tamper_header(path, metadata=False)
    else:
        _tamper_header(path, lambda header: header.update(table_version=10))

    storage._tq_index = None
    assert storage.load_tq_index() is None, "a stale header must not be trusted"

    rebuilt = storage.get_tq_index()
    assert builds == [11, 11]
    assert len(rebuilt) == len(_docs())

    with safe_open(str(path), framework="pt", device="cpu") as handle:
        header = json.loads(handle.metadata()["tq_header"])
    assert header["table_version"] == 11


def test_legacy_tqcache_json_is_treated_as_stale(tmp_path):
    storage, _table = _make_storage(tmp_path, rows=_docs(), version=5)
    legacy = storage.get_legacy_tq_index_path()
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text('{"compressed_db": {"score": {"items": {}}}}')

    assert storage.load_tq_index() is None

    index = storage.get_tq_index()
    assert storage.get_tq_index_path().exists()
    assert len(index) == len(_docs())


def test_legacy_pickle_is_never_loaded(tmp_path):
    storage, _table = _make_storage(tmp_path, rows=_docs(), version=5)
    pkl = storage.get_legacy_pickle_path()
    pkl.parent.mkdir(parents=True, exist_ok=True)
    pkl.write_bytes(b"not-a-real-pickle")

    assert storage.load_tq_index() is None


def test_tq_cache_header_does_not_persist_raw_vectors(tmp_path):
    storage, _table = _make_storage(tmp_path, rows=_docs(), version=3)
    storage.get_tq_index()

    with safe_open(
        str(storage.get_tq_index_path()), framework="pt", device="cpu"
    ) as handle:
        payload = json.loads(handle.metadata()["tq_payload"])

    assert payload["meta"]
    assert all("vector" not in meta for meta in payload["meta"])
