"""Markdown rendering for search results with a bounded snippet budget."""

from typing import Any, List, Optional

ELLIPSIS = "…"
DEFAULT_SNIPPET_CHARS = 800

# Natural places to end a snippet: paragraph breaks and sentence terminators
# (Latin punctuation followed by a break, plus the CJK full stops). The match
# closest to the budget wins.
_SENTENCE_BOUNDARIES = (
    "\n\n",
    ". ",
    "! ",
    "? ",
    ".\n",
    "!\n",
    "?\n",
    "。",
    "！",
    "？",
)


def format_snippet(text: str, max_chars: int = DEFAULT_SNIPPET_CHARS) -> str:
    """Return at most ``max_chars`` characters of ``text``, cut on a boundary.

    The cut lands on the last sentence or paragraph boundary inside the budget,
    so a snippet does not stop mid-sentence. When no boundary is close enough,
    the cut falls back to the last word and finally to a hard cut. Truncated
    text ends with ``…`` so a reader knows the rest is in the source document.
    """
    if max_chars <= 0 or len(text) <= max_chars:
        return text

    # Leave one character for the ellipsis so the result respects the budget.
    window = text[: max_chars - 1]
    floor = max_chars // 2

    cut = -1
    for boundary in _SENTENCE_BOUNDARIES:
        index = window.rfind(boundary)
        if index >= 0:
            cut = max(cut, index + len(boundary))

    if cut <= floor:
        # No usable boundary: cut on the last word that still uses most of the
        # budget, then fall back to a hard cut.
        cut = -1
        for index in range(len(window) - 1, floor, -1):
            if window[index].isspace():
                cut = index
                break
    if cut <= 0:
        cut = len(window)

    return window[:cut].rstrip() + ELLIPSIS


def build_doc_url(source_catalog: Any, category: str, filename: str) -> Optional[str]:
    """Return the public documentation URL for a result, or ``None``.

    The catalog is optional (embedders and tests may not provide one), and some
    sources (PHP stubs, JS SDK) legitimately have no public URL, so a missing or
    non-string value degrades to ``None`` instead of failing the search.
    """
    if not category or not filename or source_catalog is None:
        return None

    source = source_catalog.by_category(category)
    if source is None:
        return None

    url = source.build_doc_url(filename)
    return url if isinstance(url, str) else None


class SearchFormatter:
    def __init__(self, source_catalog: Any):
        self.source_catalog = source_catalog

    def doc_url(self, category: str, filename: str) -> Optional[str]:
        """URL of the source document, when the catalog knows one."""
        return build_doc_url(self.source_catalog, category, filename)

    def format_markdown(
        self, results: List[dict[str, Any]], max_chars: int = DEFAULT_SNIPPET_CHARS
    ) -> str:
        """Convert result dicts into rich Markdown result cards.

        Each card keeps the header, the metadata line and the documentation URL;
        only the body is bounded, so `get_file_content` remains the escalation
        path for the full text.
        """
        formatted_results = []
        for r in results:
            relevance = r.get("_relevance", 0.0)
            category = r.get("category", "")
            filename = r.get("filename", "")

            doc_url = self.doc_url(category, filename)

            header = f"### [{category.upper()}] {r.get('title') or 'Untitled'}"

            meta_parts = []
            if filename:
                meta_parts.append(f"**File:** `{filename}`")
            if r.get("breadcrumb"):
                meta_parts.append(f"**Path:** {r['breadcrumb']}")
            meta_parts.append(f"**Score:** {relevance:.4f}")
            meta_line = " | ".join(meta_parts)

            url_section = f"\n**Documentation:** {doc_url}\n" if doc_url else ""

            body = format_snippet(r.get("text", ""), max_chars)

            formatted_results.append(
                f"{header}\n{meta_line}\n{url_section}\n{body}\n\n---\n"
            )
        return "\n".join(formatted_results)
