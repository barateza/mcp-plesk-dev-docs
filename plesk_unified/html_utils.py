import re
from pathlib import Path
from typing import Optional, Tuple

from bs4 import BeautifulSoup
from markdownify import markdownify as _md


def parse_html_file(
    path: Path, toc_meta: Optional[dict] = None
) -> Tuple[str, Optional[str], str]:
    """Parse an HTML file and return (title, breadcrumb, text).

    - Removes nav/footer/script/style/aside elements before extracting text.
    - Prefers <main> or <article> when available.
    - Converts HTML to Markdown so that code blocks and headings are preserved.
    """
    path = Path(path)
    with path.open("r", encoding="utf-8", errors="ignore") as fh:
        html = fh.read()

    soup = BeautifulSoup(html, "html.parser")

    title_tag = soup.find("title")
    title = (
        title_tag.get_text(strip=True)
        if title_tag
        else (toc_meta or {}).get("title", "")
    )

    # Remove common noisy elements
    for sel in soup.select(
        "nav, footer, script, style, aside, .sidebar, .toc, noscript"
    ):
        sel.decompose()

    main = soup.find("main") or soup.find("article") or soup.body
    raw_html = str(main) if main else str(soup)

    # Convert to Markdown to preserve code blocks and headings.
    # strip=["a"] removes anchor tags but keeps their visible text,
    # which avoids noisy "[text](url)" patterns in the indexed corpus.
    text = _md(raw_html, heading_style="ATX", strip=["a"])

    # Collapse runs of 3+ blank lines introduced by some HTML layouts.
    text = re.sub(r"\n{3,}", "\n\n", text).strip()

    breadcrumb = (toc_meta or {}).get("breadcrumb")

    return title, breadcrumb, text


def clean_html_for_markdown(html: str) -> str:
    """Return cleaned HTML string suitable for markdown conversion.

    This removes nav/footer/script/style/aside nodes and returns the inner
    HTML of main/article/body.
    """
    soup = BeautifulSoup(html, "html.parser")
    for sel in soup.select(
        "nav, footer, script, style, aside, .sidebar, .toc, noscript"
    ):
        sel.decompose()
    main = soup.find("main") or soup.find("article") or soup.body
    return str(main) if main else str(soup)
