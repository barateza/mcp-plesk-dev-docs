from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any

_WORD_RE = re.compile(r"[A-Za-z0-9_./+-]+")
_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "for",
    "from",
    "how",
    "in",
    "is",
    "of",
    "on",
    "or",
    "the",
    "to",
    "via",
    "with",
    "what",
    "which",
    "when",
    "where",
    "who",
    "why",
}


@dataclass(frozen=True)
class SearchResult:
    text: str
    title: str
    score: float
    metadata: dict[str, Any]


@dataclass(frozen=True)
class RoutingDecision:
    engine: str
    pilot_config: StructurePilotConfig | None
    reason: str


@dataclass(frozen=True)
class StructurePilotConfig:
    name: str
    title_weight: float = 2.5
    breadcrumb_weight: float = 1.8
    filename_weight: float = 0.9
    text_weight: float = 0.35
    title_phrase_bonus: float = 1.5
    breadcrumb_phrase_bonus: float = 1.0
    rank_weight: float = 0.5


DEFAULT_PILOT_CONFIG = StructurePilotConfig(name="base")

PILOT_CONFIGS: list[StructurePilotConfig] = [
    DEFAULT_PILOT_CONFIG,
    StructurePilotConfig(
        name="title-focused",
        title_weight=3.0,
        breadcrumb_weight=1.5,
        filename_weight=0.8,
        text_weight=0.25,
        title_phrase_bonus=2.0,
        breadcrumb_phrase_bonus=0.75,
        rank_weight=0.35,
    ),
    StructurePilotConfig(
        name="breadcrumb-focused",
        title_weight=2.2,
        breadcrumb_weight=2.4,
        filename_weight=1.0,
        text_weight=0.2,
        title_phrase_bonus=1.25,
        breadcrumb_phrase_bonus=1.5,
        rank_weight=0.4,
    ),
    StructurePilotConfig(
        name="metadata-heavy",
        title_weight=2.8,
        breadcrumb_weight=2.2,
        filename_weight=1.2,
        text_weight=0.15,
        title_phrase_bonus=1.75,
        breadcrumb_phrase_bonus=1.25,
        rank_weight=0.3,
    ),
]


def tokenize(text: str) -> list[str]:
    tokens = [token.lower() for token in _WORD_RE.findall(text or "")]
    return [token for token in tokens if token not in _STOPWORDS and len(token) > 1]


def bucket_query(query: str) -> str:
    """Classify a query as structural, lookup, or multi-hop for reporting/routing."""
    normalized = (query or "").lower()

    # N-gram markers for compound/multi-hop queries
    multi_hop_markers = (
        " and ",
        " then ",
        " also ",
        "together",
        "combined",
        " followed by ",
        " as well as ",
    )

    structural_markers = (
        "how to",
        "add ",
        "create ",
        "configure ",
        "register ",
        "package ",
        "restart ",
        "install ",
        "set up",
    )
    lookup_markers = (
        "list ",
        "show ",
        "find ",
        "what is",
        "where is",
        "retrieve ",
        "get ",
        "authenticate ",
    )

    if any(marker in normalized for marker in multi_hop_markers):
        return "multi-hop"
    if any(marker in normalized for marker in structural_markers):
        return "structural"
    if any(marker in normalized for marker in lookup_markers):
        return "lookup"
    return "mixed"


def _field_score(
    query_terms: list[str], value: str | None, weight: float, phrase_bonus: float
) -> float:
    if not value:
        return 0.0

    value_lower = value.lower()
    matches = sum(1 for term in query_terms if term in value_lower)
    if matches == 0:
        return 0.0

    phrase_match = (
        phrase_bonus
        if " ".join(query_terms[:2]) in value_lower and len(query_terms) >= 2
        else 0.0
    )
    return weight * (1.0 + math.log1p(matches) + phrase_match)


def structure_pilot_score(
    query: str,
    result: dict[str, Any],
    rank: int,
    total: int,
    config: StructurePilotConfig = DEFAULT_PILOT_CONFIG,
) -> float:
    """Compute a PageIndex-inspired score from title and breadcrumb structure."""
    query_terms = tokenize(query)
    if not query_terms:
        return 0.0

    title = result.get("title", "")
    breadcrumb = result.get("breadcrumb", "")
    filename = result.get("filename", "")
    text = result.get("text", "")

    base_rank_bonus = 0.0
    if total > 1:
        base_rank_bonus = (total - rank) / (total - 1)

    score = 0.0
    score += _field_score(
        query_terms, title, config.title_weight, config.title_phrase_bonus
    )
    score += _field_score(
        query_terms,
        breadcrumb,
        config.breadcrumb_weight,
        config.breadcrumb_phrase_bonus,
    )
    score += _field_score(query_terms, filename, config.filename_weight, 0.0)
    score += _field_score(query_terms, text, config.text_weight, 0.0)
    score += base_rank_bonus * config.rank_weight

    normalized_query = " ".join(query_terms)
    if normalized_query and normalized_query in (title or "").lower():
        score += config.title_phrase_bonus
    if normalized_query and normalized_query in (breadcrumb or "").lower():
        score += config.breadcrumb_phrase_bonus

    return score


def rerank_with_structure(
    query: str,
    results: list[dict[str, Any]],
    config: StructurePilotConfig = DEFAULT_PILOT_CONFIG,
) -> list[dict[str, Any]]:
    """Return results sorted by a structure-aware pilot score."""
    total = len(results)
    scored = []
    for rank, result in enumerate(results, start=1):
        enriched = dict(result)
        enriched["_pilot_bucket"] = bucket_query(query)
        enriched["_pilot_config"] = config.name
        enriched["_pilot_score"] = structure_pilot_score(
            query, enriched, rank, total, config=config
        )
        scored.append(enriched)

    scored.sort(
        key=lambda item: (
            item.get("_pilot_score", 0.0),
            item.get("_score_tq", item.get("_distance", item.get("_score", 0.0))),
        ),
        reverse=True,
    )
    return scored


def get_pilot_configs() -> list[StructurePilotConfig]:
    return list(PILOT_CONFIGS)


def get_pilot_config_by_name(name: str) -> StructurePilotConfig:
    by_name = {cfg.name: cfg for cfg in PILOT_CONFIGS}
    return by_name.get(name, DEFAULT_PILOT_CONFIG)


def list_routing_policies() -> dict[str, str]:
    return {
        "baseline-only": "Always use baseline retrieval for every query.",
        "adaptive": (
            "Route multi-hop and targeted structural intents to pageindex-pilot; "
            "keep lookup and generic intents on baseline."
        ),
        "aggressive": "Always use pageindex-pilot with breadcrumb-focused config.",
    }


def route_query(
    query: str,
    bucket: str,
    routing_policy: str = "baseline-only",
) -> RoutingDecision:
    """Select retrieval engine per-query based on policy and intent markers."""
    normalized_policy = (routing_policy or "baseline-only").strip().lower()
    normalized_bucket = (bucket or bucket_query(query)).strip().lower()
    query_lower = (query or "").lower()

    if normalized_policy == "baseline-only":
        return RoutingDecision(
            engine="baseline",
            pilot_config=None,
            reason="policy-baseline-only",
        )

    if normalized_policy == "aggressive":
        return RoutingDecision(
            engine="pageindex-pilot",
            pilot_config=get_pilot_config_by_name("breadcrumb-focused"),
            reason="policy-aggressive",
        )

    if normalized_policy != "adaptive":
        return RoutingDecision(
            engine="baseline",
            pilot_config=None,
            reason="policy-unknown-fallback",
        )

    multi_hop_markers = (
        " and ",
        " then ",
        " also ",
        "together",
        "combined",
    )
    structural_markers = (
        "how to",
        "add ",
        "create ",
        "where is",
        "which section",
        "which page",
        "how do i",
    )

    if normalized_bucket == "multi-hop" or any(
        m in query_lower for m in multi_hop_markers
    ):
        return RoutingDecision(
            engine="pageindex-pilot",
            pilot_config=get_pilot_config_by_name("breadcrumb-focused"),
            reason="adaptive-multi-hop",
        )

    if normalized_bucket == "structural" and any(
        m in query_lower for m in structural_markers
    ):
        return RoutingDecision(
            engine="pageindex-pilot",
            pilot_config=get_pilot_config_by_name("base"),
            reason="adaptive-structural",
        )

    return RoutingDecision(
        engine="baseline",
        pilot_config=None,
        reason="adaptive-baseline",
    )
