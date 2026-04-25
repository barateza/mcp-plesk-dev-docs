import json
from typing import Any, Dict
from plesk_unified import io_utils


class TocFormatter:
    def __init__(self, source_catalog: Any):
        self.source_catalog = source_catalog

    def to_json(self, category: str) -> str:
        """Return the Table of Contents for a category as a JSON string."""
        source = self.source_catalog.by_category(category)
        if not source:
            return json.dumps({"error": f"Category '{category}' not found."})

        if source.source_type == "html":
            toc_map = io_utils.load_toc_map(source.path)
            return json.dumps(toc_map, indent=2)

        return json.dumps({})

    def format_markdown(self, category: str, toc_map: Dict[str, Any]) -> str:
        """Helper to load and format TOC as a Markdown list."""
        source = self.source_catalog.by_category(category)
        if not source:
            return f"Category '{category}' not found."

        if not toc_map:
            return f"No Table of Contents available for {category}."

        lines = [f"# Plesk {category.upper()} Table of Contents\n"]

        # Sort entries by breadcrumb
        # toc_map returns Dict[filename, Dict[title, breadcrumb]]
        sorted_items = sorted(toc_map.items(), key=lambda x: x[1].get("breadcrumb", ""))

        for filename, entry in sorted_items:
            title = entry.get("title", "Untitled")
            breadcrumb = entry.get("breadcrumb", title)
            url = source.build_doc_url(filename)

            if url:
                lines.append(f"- [{title}]({url})")
                lines.append(f"  Path: {breadcrumb}")
            else:
                lines.append(f"- {breadcrumb}")

        return "\n".join(lines)
