import logging
import os
import re
from pathlib import Path
from typing import Optional, Tuple, Set

from bs4 import BeautifulSoup
from markdownify import markdownify as _md

from plesk_unified.ai_client import AIClient

logger = logging.getLogger(__name__)

# Constants for cognitive load rules
MAX_TABLE_ROWS = 10
MIN_PACKET_LEN = 5


def _is_table_complex(table) -> bool:
    """Heuristic to determine if a table is complex enough to need LLM normalization."""
    # merged cells
    if table.find_all(attrs={"colspan": True}) or table.find_all(
        attrs={"rowspan": True}
    ):
        return True

    rows = table.find_all("tr")
    if len(rows) > MAX_TABLE_ROWS:  # Oversized table
        return True

    # Check for multi-level headers (th in non-first row or multiple rows with th)
    th_rows = 0
    for row in rows:
        if row.find("th"):
            th_rows += 1
    if th_rows > 1:
        return True

    return False


def _normalize_table_with_llm(
    table, ai_client: AIClient, model: Optional[str] = None
) -> str:
    """Convert a complex HTML table into prose using an LLM."""
    table_html = str(table)
    prompt = (
        "Convert the following HTML table into descriptive prose sentences "
        "that preserve row-column semantic relationships. Output ONLY the prose.\n\n"
        f"Table:\n{table_html}"
    )

    try:
        models = [model] if model else ["google/gemini-2.5-flash-lite"]
        res = ai_client.generate_description(prompt, model_list=models)
        if res and res != "Description unavailable.":
            return res
    except Exception:
        pass

    return ""


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


def _replace_tables_with_prose(
    soup: BeautifulSoup,
    llm_enabled: bool = False,
    ai_client: Optional[AIClient] = None,
    llm_model: Optional[str] = None,
) -> None:
    """Replace HTML tables with prose blocks to preserve semantic relationships."""
    for table in soup.find_all("table"):
        prose = ""
        if llm_enabled and ai_client and _is_table_complex(table):
            prose = _normalize_table_with_llm(table, ai_client, llm_model)

        if not prose:
            prose = _normalize_table_to_sentences(table)

        if not prose:
            table.decompose()
            continue
        replacement = soup.new_tag("p")
        replacement.string = prose
        table.replace_with(replacement)


def extract_api_endpoints(html: str) -> Optional[str]:
    """Extract API endpoint signatures (REST, XML, CLI) from HTML content."""
    found_endpoints: Set[str] = set()

    # 1. REST API patterns
    rest_matches = re.findall(
        r"(GET|POST|PUT|DELETE|PATCH).{0,100}?((/api/v2)?/[a-zA-Z0-9\/\-\_{}]+)",
        html,
    )
    for method, path, _ in rest_matches:
        found_endpoints.add(f"{method} {path}")

    # 2. XML API patterns
    xml_matches = re.findall(r"([a-z0-9\_]+(?:_list|_get|_set))", html)
    for packet in xml_matches:
        if len(packet) > MIN_PACKET_LEN:  # avoid tiny noise
            found_endpoints.add(f"XML: {packet}")

    # 3. CLI patterns
    cli_matches = re.findall(r"plesk\s+(?:bin\s+)?([a-z0-9\_]+)\s+([a-z0-9\_]+)", html)
    for obj, cmd in cli_matches:
        found_endpoints.add(f"CLI: {obj} {cmd}")

    if not found_endpoints:
        return None

    return ", ".join(sorted(found_endpoints))


def clean_dom_tree(soup: BeautifulSoup) -> BeautifulSoup:
    """Remove nav, footer, scripts and other noisy elements from the DOM tree."""
    for sel in soup.select(
        "nav, footer, script, style, aside, .sidebar, .toc, noscript"
    ):
        sel.decompose()

    llm_enabled = os.environ.get("PLESK_HTML_LLM_TABLE_NORMALIZE") == "1"
    ai_client = AIClient() if llm_enabled else None
    _replace_tables_with_prose(soup, llm_enabled=llm_enabled, ai_client=ai_client)

    return soup


def convert_soup_to_markdown(soup: BeautifulSoup) -> str:
    """Convert a cleaned BeautifulSoup tree into Markdown text."""
    main = soup.find("main") or soup.find("article") or soup.body
    raw_html = str(main) if main else str(soup)

    # Convert to Markdown to preserve code blocks and headings.
    text = _md(raw_html, heading_style="ATX", strip=["a"])

    # Collapse runs of 3+ blank lines
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


def parse_html(
    path: Path, toc_meta: Optional[dict] = None
) -> Tuple[str, str, Optional[str], str, Optional[str]]:
    """Parse an HTML file and return (filename, title, breadcrumb, text, endpoint)."""
    path = Path(path)
    with path.open("r", encoding="utf-8", errors="ignore") as fh:
        html = fh.read()

    # 1. Extraction (Functional Decomposition)
    endpoint = extract_api_endpoints(html)

    soup = BeautifulSoup(html, "html.parser")

    # 2. Title extraction
    title_tag = soup.find("title")
    title = (
        title_tag.get_text(strip=True)
        if title_tag
        else (toc_meta or {}).get("title", "")
    )

    # 3. DOM Cleaning
    soup = clean_dom_tree(soup)

    # 4. Conversion
    text = convert_soup_to_markdown(soup)

    breadcrumb = (toc_meta or {}).get("breadcrumb")

    return path.name, title, breadcrumb, text, endpoint


def clean_html_for_markdown(html: str) -> str:
    """Return cleaned HTML string suitable for markdown conversion."""
    soup = BeautifulSoup(html, "html.parser")
    soup = clean_dom_tree(soup)

    main = soup.find("main") or soup.find("article") or soup.body
    return str(main) if main else str(soup)
