from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Literal, Optional, Union


class CategoryEnum(str, Enum):
    """Supported Plesk documentation categories."""

    GUIDE = "guide"
    CLI = "cli"
    API = "api"
    PHP_STUBS = "php-stubs"
    JS_SDK = "js-sdk"


VALID_CATEGORIES: frozenset[str] = frozenset(c.value for c in CategoryEnum)


def validate_category(category: str, allow_all: bool = False) -> None:
    """Validate that a category string is valid."""
    if allow_all and category == "all":
        return
    if category not in VALID_CATEGORIES:
        raise ValueError(f"Invalid category: '{category}'")


# Type alias for refresh_knowledge which accepts a specific category or "all"
CategoryOrAll = Union[CategoryEnum, Literal["all"]]


# ---------------------------------------------------------------------------
# Model Profile definitions (static data — resolution logic is in
# application/services/profile_service.py)
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
    rerank_candidates: int = 35
    relevance_gate: float = 0.55
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
        rerank_candidates=35,
        relevance_gate=0.50,
    ),
    "medium": ModelProfile(
        name="medium",
        embed_model="BAAI/bge-base-en-v1.5",
        embed_dim=768,
        reranker_model="cross-encoder/ms-marco-MiniLM-L4-v2",
        reranker_enabled=True,
        description="~600 MB total. Good quality with moderate memory use.",
        approx_ram_mb=600,
        rerank_candidates=35,
        relevance_gate=0.55,
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
        relevance_gate=0.60,
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
        relevance_gate=0.60,
        tq_bits=4,
        tq_top_k=25,
    ),
}

DEFAULT_PROFILE = "full-tq"


@dataclass(frozen=True)
class SourceDefinition:
    category: CategoryEnum
    path: Path
    source_type: str  # "html", "php", "js"
    repo_url: Optional[str] = None
    zip_url: Optional[str] = None

    @property
    def doc_base_url(self) -> Optional[str]:
        if not self.zip_url:
            return None
        # Pattern: https://.../zip/<name>.zip  →  https://.../<name>/
        return self.zip_url.replace("/zip/", "/").removesuffix(".zip") + "/"

    def build_doc_url(self, filename: str) -> Optional[str]:
        base = self.doc_base_url
        if base and filename:
            return base + filename
        return None
