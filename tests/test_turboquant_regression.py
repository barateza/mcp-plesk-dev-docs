from __future__ import annotations

import numpy as np
import torch

from mcp_plesk_dev_docs.infrastructure import turboquant_index
from tq_search import LloydMaxCodebook, TurboQuantMSE, TurboQuantProd


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
