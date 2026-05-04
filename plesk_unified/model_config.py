"""
Model profile configuration for mcp-plesk-unified.

Profiles let you trade RAM/VRAM footprint against retrieval quality.
Select a profile via the PLESK_MODEL_PROFILE environment variable.

  PLESK_MODEL_PROFILE=light    ~200 MB total  (M2 MacBook Air, memory-constrained)
  PLESK_MODEL_PROFILE=full     ~1.8 GB total  (RTX 4070 Super, max quality)
  PLESK_MODEL_PROFILE=medium   ~600 MB total  (balanced middle ground)

You can also override individual components without changing the profile:
    PLESK_EMBED_MODEL=BAAI/bge-base-en-v1.5
    PLESK_RERANKER_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2
    PLESK_RERANKER_ENABLED=false
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from plesk_unified.platform_utils import get_optimal_device, get_platform_info
from plesk_unified.settings import settings

logger = logging.getLogger("plesk_unified")

# ---------------------------------------------------------------------------
# Profile definitions
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ModelProfile:
    name: str
    embed_model: str
    embed_dim: int  # must match LanceDB vector column dimension
    reranker_model: str | None
    reranker_enabled: bool
    description: str
    approx_ram_mb: int
    use_turboquant: bool = False
    tq_bits: int = 5
    tq_top_k: int = 25


_PROFILES: dict[str, ModelProfile] = {
    "light": ModelProfile(
        name="light",
        embed_model="BAAI/bge-small-en-v1.5",
        embed_dim=384,
        reranker_model="cross-encoder/ms-marco-MiniLM-L4-v2",
        reranker_enabled=True,
        description=(
            "~200 MB total. Ideal for M2 MacBook Air or any memory-constrained host."
        ),
        approx_ram_mb=200,
    ),
    "medium": ModelProfile(
        name="medium",
        embed_model="BAAI/bge-base-en-v1.5",
        embed_dim=768,
        reranker_model="cross-encoder/ms-marco-MiniLM-L4-v2",
        reranker_enabled=True,
        description="~600 MB total. Good quality with moderate memory use.",
        approx_ram_mb=600,
    ),
    "full": ModelProfile(
        name="full",
        embed_model="BAAI/bge-m3",
        embed_dim=1024,
        reranker_model="BAAI/bge-reranker-base",
        reranker_enabled=True,
        description=(
            "~1.8 GB total. Maximum quality. Recommended for RTX 4070 Super / CUDA."
        ),
        approx_ram_mb=1800,
    ),
    "full-tq": ModelProfile(
        name="full-tq",
        embed_model="BAAI/bge-m3",
        embed_dim=1024,
        reranker_model="BAAI/bge-reranker-base",
        reranker_enabled=True,
        description=(
            "TurboQuant 4-bit profile with category-aware retrieval. "
            "Quality parity target with significantly lower latency."
        ),
        approx_ram_mb=1300,
        use_turboquant=True,
        tq_bits=4,
        tq_top_k=25,
    ),
}

DEFAULT_PROFILE = "full-tq"


# ---------------------------------------------------------------------------
# Resolution logic (env vars  profile  individual overrides)
# ---------------------------------------------------------------------------


def get_active_profile() -> ModelProfile:
    """
    Resolve the active model profile from environment variables.

        Priority (highest to lowest):
            1. PLESK_EMBED_MODEL / PLESK_RERANKER_MODEL  (per-component overrides)
            2. PLESK_MODEL_PROFILE                        (named profile)
            3. Compiled-in default ("full-tq")
    """
    profile_name = settings.plesk_model_profile
    profile_name = profile_name.lower().strip()

    if profile_name not in _PROFILES:
        logger.warning(
            "Unknown PLESK_MODEL_PROFILE=%r. Valid options: %s. Falling back to '%s'.",
            profile_name,
            ", ".join(_PROFILES),
            DEFAULT_PROFILE,
        )
        profile_name = DEFAULT_PROFILE

    base = _PROFILES[profile_name]

    # Apply per-component overrides on top of the profile
    embed_model = (settings.plesk_embed_model or base.embed_model).strip()

    # Handle reranker_model specifically to allow empty string as "none"
    if settings.plesk_reranker_model is not None:
        reranker_model = settings.plesk_reranker_model.strip() or None
    else:
        reranker_model = base.reranker_model

    if settings.plesk_reranker_enabled is False:
        reranker_enabled = False
    elif settings.plesk_reranker_enabled is True:
        reranker_enabled = True
    else:
        reranker_enabled = base.reranker_enabled

    # Determine vector dimension  if the embed model changed, the user must
    # also set PLESK_EMBED_DIM or we fall back to the profile default with a warning.
    embed_dim = base.embed_dim
    if embed_model != base.embed_model:
        if settings.plesk_embed_dim:
            embed_dim = settings.plesk_embed_dim
        else:
            logger.warning(
                "PLESK_EMBED_MODEL overridden to %r but PLESK_EMBED_DIM not set. "
                "Using profile default dim=%d. Set PLESK_EMBED_DIM if the model "
                "uses a different dimension, then delete storage/lancedb and reindex.",
                embed_model,
                embed_dim,
            )

    active = ModelProfile(
        name=profile_name,
        embed_model=embed_model,
        embed_dim=embed_dim,
        reranker_model=reranker_model,
        reranker_enabled=reranker_enabled and (reranker_model is not None),
        description=base.description,
        approx_ram_mb=base.approx_ram_mb,
        use_turboquant=base.use_turboquant,
        tq_bits=base.tq_bits,
        tq_top_k=base.tq_top_k,
    )

    # VRAM Auto-tuning check
    device = get_optimal_device()
    if device == "cuda":
        info = get_platform_info()
        free_vram = info.get("vram_free_mb")
        if free_vram and active.approx_ram_mb > free_vram:
            logger.warning(
                "VRAM Auto-Tune: Profile '%s' requires ~%d MB but only %d MB is free. "
                "Consider switching to a lighter profile (e.g., 'medium' or 'light') "
                "to avoid Out-Of-Memory (OOM) errors.",
                active.name,
                active.approx_ram_mb,
                free_vram,
            )

    logger.info(
        "Active model profile: %s | embed=%s (dim=%d) | reranker=%s "
        "(enabled=%s) | ~%d MB",
        active.name,
        active.embed_model,
        active.embed_dim,
        active.reranker_model,
        active.reranker_enabled,
        active.approx_ram_mb,
    )

    return active


def list_profiles() -> dict[str, dict]:
    """Return a serialisable summary of all built-in profiles."""
    return {
        name: {
            "embed_model": p.embed_model,
            "embed_dim": p.embed_dim,
            "reranker_model": p.reranker_model,
            "reranker_enabled": p.reranker_enabled,
            "approx_ram_mb": p.approx_ram_mb,
            "use_turboquant": p.use_turboquant,
            "tq_bits": p.tq_bits,
            "tq_top_k": p.tq_top_k,
            "description": p.description,
        }
        for name, p in _PROFILES.items()
    }
