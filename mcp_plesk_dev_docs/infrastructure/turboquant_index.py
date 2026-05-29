"""TurboQuantIndex loading strategy."""

from __future__ import annotations

import numpy as np
import torch

from tq_search import TurboQuantProd


class TurboQuantIndex:
    def __init__(self, dim: int, bits: int = 3, device: str = "cpu"):
        self.dim = dim
        self.bits = bits
        self.device = device
        self.quantizer = TurboQuantProd(dim, bits, device=device)

        # Batched tensors for compressed vectors.
        self.compressed_db: dict[str, torch.Tensor] | None = None
        self._meta: list[dict] = []
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
                index = start_idx + offset
                self._category_to_indices.setdefault(category, []).append(index)

    def search(
        self, query_vec: np.ndarray, top_k: int = 25, category: str | None = None
    ):
        if self.compressed_db is None:
            return []

        # 1. Lazily move the compressed database to the target device once
        first_val = next(iter(self.compressed_db.values()))
        if str(first_val.device) != self.device:
            self.compressed_db = {
                k: v.to(self.device) for k, v in self.compressed_db.items()
            }

        selected_indices: list[int]
        if category:
            selected_indices = self._category_to_indices.get(category, [])
            if not selected_indices:
                return []
        else:
            selected_indices = list(range(len(self._meta)))

        # 2. L2-Normalize the query
        norm = np.linalg.norm(query_vec)
        query_normalized = query_vec / max(norm, 1e-12)

        # 3. Prepare query as a batched tensor (1, dim) directly on target device
        q = torch.from_numpy(query_normalized).to(self.device).unsqueeze(0)

        # 4. Slice candidates only if we are actually filtering a subset
        if category and len(selected_indices) < len(self._meta):
            selected_tensor = torch.as_tensor(
                selected_indices, dtype=torch.long, device=self.device
            )
            db_on_device = {
                k: v.index_select(0, selected_tensor)
                for k, v in self.compressed_db.items()
            }
        else:
            db_on_device = self.compressed_db

        # 5. Perform a SINGLE batched inner product calculation
        with torch.no_grad():
            scores = self.quantizer.inner_product(q, db_on_device).squeeze(0)

        # 6. Sort and return
        scores_np = scores.cpu().numpy()
        idx = np.argsort(-scores_np)[:top_k]

        return [(self._meta[selected_indices[i]], float(scores_np[i])) for i in idx]
