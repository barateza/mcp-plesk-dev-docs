"""TurboQuant: two-stage vector quantization."""

from __future__ import annotations

import math
from typing import Optional, Tuple, cast

import torch
from torch import nn

from .lloyd_max import LloydMaxCodebook


def generate_rotation_matrix(
    d: int, seed: Optional[int] = None, device: str = "cpu"
) -> torch.Tensor:
    """Generate a random orthogonal rotation matrix via QR decomposition."""
    gen = torch.Generator(device="cpu")
    if seed is not None:
        gen.manual_seed(seed)
    G = torch.randn(d, d, generator=gen)
    Q, R = torch.linalg.qr(G)
    diag_sign = torch.sign(torch.diag(R))
    diag_sign[diag_sign == 0] = 1.0
    Q = Q * diag_sign.unsqueeze(0)
    return Q.to(device)


def generate_qjl_matrix(
    d: int, m: Optional[int] = None, seed: Optional[int] = None, device: str = "cpu"
) -> torch.Tensor:
    """
    Generate the random projection matrix S for QJL.
    S has i.i.d. N(0,1) entries, shape (m, d).
    Default m = d (same dimensionality).
    """
    if m is None:
        m = d
    gen = torch.Generator(device="cpu")
    if seed is not None:
        gen.manual_seed(seed)
    S = torch.randn(m, d, generator=gen)
    return S.to(device)


class TurboQuantMSE(nn.Module):
    """Stage 1: MSE-optimal quantizer."""

    def __init__(self, d: int, bits: int, seed: int = 42, device: str = "cpu"):
        super().__init__()
        self.d = d
        self.bits = bits
        self.device = device

        self.register_buffer(
            "Pi", generate_rotation_matrix(d, seed=seed, device=device)
        )
        self.codebook = LloydMaxCodebook(d, bits)
        self.register_buffer("centroids", self.codebook.centroids.to(device))
        self.register_buffer("boundaries", self.codebook.boundaries.to(device))

    def rotate(self, x: torch.Tensor) -> torch.Tensor:
        Pi = cast("torch.Tensor", self.Pi)
        return x @ Pi.T

    def unrotate(self, y: torch.Tensor) -> torch.Tensor:
        Pi = cast("torch.Tensor", self.Pi)
        return y @ Pi

    def quantize(self, x: torch.Tensor) -> torch.Tensor:
        centroids = cast("torch.Tensor", self.centroids)
        y = self.rotate(x)
        diffs = y.unsqueeze(-1) - centroids
        indices = diffs.abs().argmin(dim=-1)
        return indices

    def dequantize(self, indices: torch.Tensor) -> torch.Tensor:
        centroids = cast("torch.Tensor", self.centroids)
        y_hat = centroids[indices]
        return self.unrotate(y_hat)

    def forward(self, x: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        indices = self.quantize(x)
        x_hat = self.dequantize(indices)
        return x_hat, indices


class TurboQuantProd(nn.Module):
    """Stage 1 + Stage 2: Unbiased inner product quantizer."""

    def __init__(
        self,
        d: int,
        bits: int,
        qjl_dim: Optional[int] = None,
        seed: int = 42,
        device: str = "cpu",
    ):
        super().__init__()
        self.d = d
        self.bits = bits
        self.mse_bits = max(bits - 1, 1)
        self.qjl_dim = qjl_dim or d
        self.device = device

        self.mse = TurboQuantMSE(d, self.mse_bits, seed=seed, device=device)
        self.register_buffer(
            "S", generate_qjl_matrix(d, m=self.qjl_dim, seed=seed + 1, device=device)
        )

    def quantize(self, x: torch.Tensor) -> dict:
        x_hat, mse_indices = self.mse(x)
        residual = x - x_hat
        residual_norm = torch.norm(residual, dim=-1, keepdim=True)
        S = cast("torch.Tensor", self.S)
        projected = residual @ S.T
        qjl_signs = torch.sign(projected)
        qjl_signs[qjl_signs == 0] = 1.0

        return {
            "mse_indices": mse_indices,
            "qjl_signs": qjl_signs,
            "residual_norm": residual_norm.squeeze(-1),
        }

    def dequantize(self, compressed: dict) -> torch.Tensor:
        return self.mse.dequantize(compressed["mse_indices"])

    def inner_product(self, y: torch.Tensor, compressed: dict) -> torch.Tensor:
        x_mse = self.mse.dequantize(compressed["mse_indices"])
        term1 = (y * x_mse).sum(dim=-1)

        S = cast("torch.Tensor", self.S)
        y_projected = y @ S.T
        qjl_ip = (y_projected * compressed["qjl_signs"]).sum(dim=-1)

        m = self.qjl_dim
        correction_scale = math.sqrt(math.pi / 2) / m
        term2 = compressed["residual_norm"] * correction_scale * qjl_ip

        return term1 + term2

    def forward(self, x: torch.Tensor) -> dict:
        return self.quantize(x)


class TurboQuantKVCache:
    """KV cache wrapper that uses TurboQuant to compress keys and values."""

    def __init__(
        self,
        d_key: int,
        d_value: int,
        bits: int = 3,
        seed: int = 42,
        device: str = "cpu",
    ):
        self.d_key = d_key
        self.d_value = d_value
        self.bits = bits
        self.device = device

        self.key_quantizer = TurboQuantProd(d_key, bits, seed=seed, device=device)
        self.value_quantizer = TurboQuantMSE(
            d_value, bits, seed=seed + 100, device=device
        )

        self.key_cache = []
        self.value_cache = []

    def append(self, keys: torch.Tensor, values: torch.Tensor):
        orig_shape = keys.shape
        flat_keys = keys.reshape(-1, self.d_key)
        flat_values = values.reshape(-1, self.d_value)

        compressed_keys = self.key_quantizer.quantize(flat_keys)
        value_indices = self.value_quantizer.quantize(flat_values)

        self.key_cache.append(
            {
                "mse_indices": compressed_keys["mse_indices"],
                "qjl_signs": compressed_keys["qjl_signs"],
                "residual_norm": compressed_keys["residual_norm"],
                "shape": orig_shape,
            }
        )
        self.value_cache.append(
            {
                "indices": value_indices,
                "shape": values.shape,
            }
        )

    def attention_scores(self, queries: torch.Tensor) -> torch.Tensor:
        scores = []
        for cached in self.key_cache:
            s = self.key_quantizer.inner_product(queries, cached)
            scores.append(s)
        return torch.cat(scores, dim=-1) if scores else torch.tensor([])

    def get_values(self) -> torch.Tensor:
        values = []
        for cached in self.value_cache:
            v = self.value_quantizer.dequantize(cached["indices"])
            values.append(v)
        return torch.cat(values, dim=0) if values else torch.tensor([])

    def memory_usage_bits(self) -> dict:
        n_keys = (
            sum(c["mse_indices"].numel() for c in self.key_cache)
            if self.key_cache
            else 0
        )
        n_qjl = (
            sum(c["qjl_signs"].numel() for c in self.key_cache) if self.key_cache else 0
        )
        n_norms = (
            sum(c["residual_norm"].numel() for c in self.key_cache)
            if self.key_cache
            else 0
        )
        n_values = (
            sum(c["indices"].numel() for c in self.value_cache)
            if self.value_cache
            else 0
        )

        key_bits = n_keys * self.key_quantizer.mse_bits + n_qjl * 1 + n_norms * 16
        value_bits = n_values * self.bits
        fp16_equivalent = (n_keys + n_values) * 16

        return {
            "key_bits": key_bits,
            "value_bits": value_bits,
            "total_bits": key_bits + value_bits,
            "fp16_bits": fp16_equivalent,
            "compression_ratio": (
                fp16_equivalent / (key_bits + value_bits)
                if (key_bits + value_bits) > 0
                else 0
            ),
        }

    def __len__(self):
        return (
            sum(c["mse_indices"].shape[0] for c in self.key_cache)
            if self.key_cache
            else 0
        )
