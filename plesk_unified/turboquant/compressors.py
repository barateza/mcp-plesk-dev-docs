"""TurboQuant KV cache helpers."""

from __future__ import annotations

import math

import torch


# ---------------------------------------------------------------------------
# Closed-form Gaussian integration helpers (replaces scipy.integrate.quad)
# ---------------------------------------------------------------------------


def _gauss_pdf(x: float, sigma: float) -> float:
    return math.exp(-0.5 * (x / sigma) ** 2) / (sigma * math.sqrt(2.0 * math.pi))


def _gauss_cdf(x: float, sigma: float) -> float:
    return 0.5 * (1.0 + math.erf(x / (sigma * math.sqrt(2.0))))


def _int_pdf(a: float, b: float, sigma: float) -> float:
    return _gauss_cdf(b, sigma) - _gauss_cdf(a, sigma)


def _int_x_pdf(a: float, b: float, sigma: float) -> float:
    return sigma * sigma * (_gauss_pdf(a, sigma) - _gauss_pdf(b, sigma))


class TurboQuantCompressorV2:
    """Compressed key store with direct inner-product scoring."""

    def __init__(self, head_dim: int, bits: int, seed: int, device: str = "cpu"):
        self.head_dim = head_dim
        self.bits = bits
        self.mse_bits = max(bits - 1, 1)
        self.device = device

        gen = torch.Generator(device="cpu")
        gen.manual_seed(seed)
        G = torch.randn(head_dim, head_dim, generator=gen)
        Q, R = torch.linalg.qr(G)
        diag_sign = torch.sign(torch.diag(R))
        diag_sign[diag_sign == 0] = 1.0
        self.Pi = (Q * diag_sign.unsqueeze(0)).to(device)

        self.centroids = self._solve_codebook(head_dim, self.mse_bits).to(device)

        gen2 = torch.Generator(device="cpu")
        gen2.manual_seed(seed + 10000)
        self.S = torch.randn(head_dim, head_dim, generator=gen2).to(device)

        self.PiT = self.Pi.T.contiguous()

    def _solve_codebook(self, d: int, bits: int) -> torch.Tensor:
        n_levels = 2**bits
        sigma = 1.0 / math.sqrt(d)

        lo, hi = -3.5 * sigma, 3.5 * sigma
        centroids = [lo + (hi - lo) * (i + 0.5) / n_levels for i in range(n_levels)]

        for _ in range(200):
            boundaries = [
                (centroids[i] + centroids[i + 1]) / 2.0 for i in range(n_levels - 1)
            ]
            edges = [lo * 3] + boundaries + [hi * 3]
            new_centroids = []
            for i in range(n_levels):
                a, b = edges[i], edges[i + 1]
                num = _int_x_pdf(a, b, sigma)
                den = _int_pdf(a, b, sigma)
                new_centroids.append(num / den if den > 1e-15 else centroids[i])
            if (
                max(abs(new_centroids[i] - centroids[i]) for i in range(n_levels))
                < 1e-10
            ):
                break
            centroids = new_centroids

        return torch.tensor(centroids, dtype=torch.float32)

    @torch.no_grad()
    def compress(self, states: torch.Tensor) -> dict:
        B, H, S, D = states.shape
        flat = states.reshape(-1, D).float()

        vec_norms = torch.norm(flat, dim=-1, keepdim=True)
        flat_norm = flat / (vec_norms + 1e-8)

        rotated = flat_norm @ self.Pi.T
        diffs = rotated.unsqueeze(-1) - self.centroids
        indices = diffs.abs().argmin(dim=-1).to(torch.uint8)

        reconstructed_rotated = self.centroids[indices.long()]
        k_mse = (reconstructed_rotated @ self.Pi) * vec_norms

        residual = flat - k_mse
        residual_norm = torch.norm(residual, dim=-1)

        projected = residual @ self.S.T
        signs = (projected >= 0).to(torch.int8) * 2 - 1

        return {
            "k_mse": k_mse.to(torch.float16).reshape(B, H, S, D),
            "qjl_signs": signs.reshape(B, H, S, D),
            "residual_norm": residual_norm.to(torch.float16).reshape(B, H, S),
            "shape": (B, H, S, D),
        }

    @torch.no_grad()
    def asymmetric_attention_scores(
        self, queries: torch.Tensor, compressed: dict
    ) -> torch.Tensor:
        k_mse = compressed["k_mse"].float()
        signs = compressed["qjl_signs"].float()
        r_norm = compressed["residual_norm"].float()

        term1 = torch.matmul(queries.float(), k_mse.transpose(-2, -1))
        q_projected = torch.matmul(queries.float(), self.S.T)
        qjl_ip = torch.matmul(q_projected, signs.transpose(-2, -1))

        m = self.S.shape[0]
        correction_scale = math.sqrt(math.pi / 2) / m
        term2 = correction_scale * qjl_ip * r_norm.unsqueeze(-2)

        return term1 + term2


class TurboQuantCompressorMSE:
    """MSE-only compressor for values."""

    def __init__(self, head_dim: int, bits: int, seed: int, device: str = "cpu"):
        self.head_dim = head_dim
        self.bits = bits
        self.device = device

        gen = torch.Generator(device="cpu")
        gen.manual_seed(seed)
        G = torch.randn(head_dim, head_dim, generator=gen)
        Q, R = torch.linalg.qr(G)
        diag_sign = torch.sign(torch.diag(R))
        diag_sign[diag_sign == 0] = 1.0
        self.Pi = (Q * diag_sign.unsqueeze(0)).to(device)
        self.centroids = self._solve_codebook(head_dim, bits).to(device)

    def _solve_codebook(self, d, bits):
        n_levels = 2**bits
        sigma = 1.0 / math.sqrt(d)

        lo, hi = -3.5 * sigma, 3.5 * sigma
        centroids = [lo + (hi - lo) * (i + 0.5) / n_levels for i in range(n_levels)]
        for _ in range(200):
            boundaries = [
                (centroids[i] + centroids[i + 1]) / 2.0 for i in range(n_levels - 1)
            ]
            edges = [lo * 3] + boundaries + [hi * 3]
            new_c = []
            for i in range(n_levels):
                a, b = edges[i], edges[i + 1]
                num = _int_x_pdf(a, b, sigma)
                den = _int_pdf(a, b, sigma)
                new_c.append(num / den if den > 1e-15 else centroids[i])
            if max(abs(new_c[i] - centroids[i]) for i in range(n_levels)) < 1e-10:
                break
            centroids = new_c
        return torch.tensor(centroids, dtype=torch.float32)

    @torch.no_grad()
    def compress(self, states: torch.Tensor) -> dict:
        B, H, S, D = states.shape
        flat = states.reshape(-1, D).float()
        vec_norms = torch.norm(flat, dim=-1, keepdim=True)
        flat_norm = flat / (vec_norms + 1e-8)
        rotated = flat_norm @ self.Pi.T
        diffs = rotated.unsqueeze(-1) - self.centroids
        indices = diffs.abs().argmin(dim=-1).to(torch.uint8)
        return {
            "indices": indices,
            "vec_norms": vec_norms.squeeze(-1).to(torch.float16),
            "shape": (B, H, S, D),
        }

    @torch.no_grad()
    def decompress(self, compressed: dict) -> torch.Tensor:
        B, H, S, D = compressed["shape"]
        indices = compressed["indices"].long()
        reconstructed = self.centroids[indices] @ self.Pi
        vec_norms = compressed["vec_norms"].float().unsqueeze(-1)
        return (reconstructed * vec_norms).reshape(B, H, S, D)
