import logging
import os
import re
from pathlib import Path
from typing import Optional, Tuple

from bs4 import BeautifulSoup
from markdownify import markdownify as _md

from plesk_unified.ai_client import AIClient

logger = logging.getLogger(__name__)


def _is_table_complex(table) -> bool:
    """Heuristic to determine if a table is complex enough to need LLM normalization."""
    # merged cells
    if table.find_all(attrs={"colspan": True}) or table.find_all(
        attrs={"rowspan": True}
    ):
        return True

    rows = table.find_all("tr")
    if len(rows) > 10:  # Oversized table
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

    # Use evaluate_ragas_score's judge logic OR generate_description's summary logic?
    # Actually, we want prose, so generate_description (which is just a prompt wrapper)
    # but with a custom prompt.
    # Let's use a direct call if we want more control.
    # For now, I'll use a direct prompt with AIClient.

    # Reusing RAGAS_DEFAULT_MODELS as they are good for instruction following
    # but we need one sentence summary usually in generate_description.
    # Here we want a bit more.
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
    llm_enabled = os.environ.get("PLESK_HTML_LLM_TABLE_NORMALIZE") == "1"
    ai_client = AIClient() if llm_enabled else None
    _replace_tables_with_prose(soup, llm_enabled=llm_enabled, ai_client=ai_client)

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

    llm_enabled = os.environ.get("PLESK_HTML_LLM_TABLE_NORMALIZE") == "1"
    ai_client = AIClient() if llm_enabled else None
    _replace_tables_with_prose(soup, llm_enabled=llm_enabled, ai_client=ai_client)

    main = soup.find("main") or soup.find("article") or soup.body
    return str(main) if main else str(soup)
