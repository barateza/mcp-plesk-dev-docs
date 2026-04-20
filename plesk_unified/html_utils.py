import re
from pathlib import Path
from typing import Optional, Tuple

from bs4 import BeautifulSoup
from markdownify import markdownify as _md


def _normalize_table_to_sentences(table) -> str:
    """Convert an HTML table into descriptive prose sentences."""
    rows = table.find_all("tr")
    if not rows:
        return ""

    matrix = []
    for row in rows:
        cells = row.find_all(["th", "td"])
        values = [c.get_text(" ", strip=True) for c in cells]
        if any(values):
            matrix.append(values)

    if not matrix:
        return ""

    header_row = rows[0].find_all("th")
    has_header = bool(header_row)

    headers = matrix[0] if has_header else []
    data_rows = matrix[1:] if has_header else matrix

    sentences = []
    for row in data_rows:
        if headers and len(headers) == len(row):
            parts = [f"{headers[i]}: {row[i]}" for i in range(len(row)) if row[i]]
            sentence = ", ".join(parts)
        else:
            sentence = " | ".join(cell for cell in row if cell)
        sentence = sentence.strip()
        if sentence:
            sentences.append(sentence + ".")

    return "\n".join(sentences)


def _replace_tables_with_prose(soup: BeautifulSoup) -> None:
    """Replace HTML tables with prose blocks to preserve semantic relationships."""
    for table in soup.find_all("table"):
        prose = _normalize_table_to_sentences(table)
        if not prose:
            table.decompose()
            continue
        replacement = soup.new_tag("p")
        replacement.string = prose
        table.replace_with(replacement)


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

    # Preserve parameter relationships before markdown conversion flattens tables.
    _replace_tables_with_prose(soup)

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
    _replace_tables_with_prose(soup)
    main = soup.find("main") or soup.find("article") or soup.body
    return str(main) if main else str(soup)
