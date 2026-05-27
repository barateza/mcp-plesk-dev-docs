from typing import Any, List


class SearchFormatter:
    def __init__(self, source_catalog: Any):
        self.source_catalog = source_catalog

    def format_markdown(self, results: List[dict[str, Any]]) -> str:
        """Convert result dicts into rich Markdown result cards."""
        formatted_results = []
        for r in results:
            relevance = r.get("_relevance", 0.0)
            category = r.get("category", "")
            filename = r.get("filename", "")

            source = self.source_catalog.by_category(category)
            doc_url = source.build_doc_url(filename) if source else None

            header = f"### [{category.upper()}] {r.get('title', 'Untitled')}"

            meta_parts = []
            if filename:
                meta_parts.append(f"**File:** `{filename}`")
            if r.get("breadcrumb"):
                meta_parts.append(f"**Path:** {r['breadcrumb']}")
            meta_parts.append(f"**Score:** {relevance:.4f}")
            meta_line = " | ".join(meta_parts)

            url_section = f"\n**Documentation:** {doc_url}\n" if doc_url else ""

            formatted_results.append(
                f"{header}\n{meta_line}\n{url_section}\n{r.get('text', '')}\n\n---\n"
            )
        return "\n".join(formatted_results)
