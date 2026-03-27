from __future__ import annotations

"""TurboQuantIndex loading strategy.

It first attempts to import ``turboquant`` from an installed package so
``pip install turboquant`` is supported. When that package is unavailable it
loads the vendored copy under ``tonbistudio-turboquant-pytorch/`` (MIT licensed).
Maintaining this fallback lets us switch to a published package in the future
without code changes.
"""

import importlib.util
import sys
from pathlib import Path

import numpy as np
import torch

try:
    from turboquant import TurboQuantProd
except ModuleNotFoundError:
    local_turboquant = Path(__file__).resolve().parents[1] / "tonbistudio-turboquant-pytorch"
    spec = importlib.util.spec_from_file_location(
        "turboquant",
        local_turboquant / "turboquant.py",
        submodule_search_locations=[str(local_turboquant)],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["turboquant"] = module
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    from turboquant import TurboQuantProd


class TurboQuantIndex:
    def __init__(self, dim: int, bits: int = 3, device: str = "cpu"):
        self.dim = dim
        self.bits = bits
        self.device = device
        self.quantizer = TurboQuantProd(dim, bits, device=device)

        # Will hold a single dict of batched tensors: {"mse_indices": Tensor, "qjl_signs": Tensor, "residual_norm": Tensor}
        self.compressed_db = None
        self._meta = []
        self._category_to_indices: dict[str, list[int]] = {}

    def add(self, vecs: np.ndarray, metas: list[dict]) -> None:
        # 1. L2-Normalize the input vectors (Critical for TurboQuant accuracy)
        norms = np.linalg.norm(vecs, axis=-1, keepdims=True)
        vecs_normalized = vecs / np.maximum(norms, 1e-12)

        # 2. Quantize the entire batch at once
        x = torch.from_numpy(vecs_normalized).to(self.device)
        compressed = self.quantizer.quantize(x)

        # 3. Store or append to the batched tensors in CPU memory
        if self.compressed_db is None:
            self.compressed_db = {k: v.cpu() for k, v in compressed.items()}
        else:
            for k in self.compressed_db:
                self.compressed_db[k] = torch.cat(
                    [self.compressed_db[k], compressed[k].cpu()], dim=0
                )

        start_idx = len(self._meta)
        self._meta.extend(metas)
        for offset, meta in enumerate(metas):
            category = meta.get("category")
            if isinstance(category, str) and category:
                self._category_to_indices.setdefault(category, []).append(start_idx + offset)

    def search(self, query_vec: np.ndarray, top_k: int = 25, category: str | None = None):
        if self.compressed_db is None:
            return []

        selected_indices: list[int]
        if category:
            selected_indices = self._category_to_indices.get(category, [])
            if not selected_indices:
                return []
        else:
            selected_indices = list(range(len(self._meta)))

        # 1. L2-Normalize the query
        norm = np.linalg.norm(query_vec)
        query_normalized = query_vec / max(norm, 1e-12)

        # 2. Prepare query as a batched tensor (1, dim)
        q = torch.from_numpy(query_normalized).to(self.device).unsqueeze(0)

        # 3. Slice candidates (optionally category-filtered) and move to the target device
        selected_tensor = torch.as_tensor(selected_indices, dtype=torch.long)
        db_on_device = {
            k: v.index_select(0, selected_tensor).to(self.device)
            for k, v in self.compressed_db.items()
        }

        # 4. Perform a SINGLE batched inner product calculation
        with torch.no_grad():
            scores = self.quantizer.inner_product(q, db_on_device).squeeze(0)  # Returns shape (N,)

        # 5. Sort and return
        scores_np = scores.cpu().numpy()
        idx = np.argsort(-scores_np)[:top_k]

        return [
            (self._meta[selected_indices[i]], float(scores_np[i]))
            for i in idx
        ]
