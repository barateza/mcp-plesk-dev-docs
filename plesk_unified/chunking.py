import re
from typing import Dict, List


def chunk_by_chars(text: str, size: int = 1500, overlap: int = 200) -> List[str]:
    """Chunk text by fixed character window with overlap."""
    if not text:
        return []
    chunks: List[str] = []
    start = 0
    n = len(text)
    step = max(1, size - overlap)
    while start < n:
        end = min(n, start + size)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start += step
    return chunks


def chunk_by_lines(text: str, chunk_size: int, overlap: int = 0) -> List[str]:
    """Chunk text by lines with optional overlap.

    `chunk_size` is number of lines per chunk. `overlap` is number of lines
    to overlap between consecutive chunks.
    """
    if not text:
        return []
    lines = text.splitlines()
    if not lines:
        return []
    chunks: List[str] = []
    step = max(1, chunk_size - overlap)
    for i in range(0, len(lines), step):
        chunk = "\n".join(lines[i : i + chunk_size])
        if chunk.strip():
            chunks.append(chunk)
    return chunks


def _split_sentences(text: str) -> List[str]:
    """Split prose into sentences using a lightweight regex heuristic."""
    if not text:
        return []
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return []
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'`])", normalized)
    return [p.strip() for p in parts if p.strip()]


def chunk_by_sentence_window(text: str, window_size: int = 5) -> List[str]:
    """Build overlapping sentence windows (stride=1) for narrative documents.

    Task C: Increased default window size to 5 for better context.
    """
    if not text:
        return []
    sentences = _split_sentences(text)
    if not sentences:
        return []
    if len(sentences) <= window_size:
        return [" ".join(sentences)]

    chunks: List[str] = []
    for idx in range(0, len(sentences) - window_size + 1):
        chunk = " ".join(sentences[idx : idx + window_size]).strip()
        if chunk:
            chunks.append(chunk)
    return chunks


def _split_by_regex_boundaries(text: str, boundary_regex: str) -> List[str]:
    """Split code by declaration boundaries while preserving section content."""
    if not text:
        return []

    lines = text.splitlines()
    if not lines:
        return []

    boundary = re.compile(boundary_regex)
    starts = [idx for idx, line in enumerate(lines) if boundary.search(line)]

    if not starts:
        return [text]

    if starts[0] != 0:
        starts = [0] + starts

    starts.append(len(lines))
    sections: List[str] = []
    for i in range(len(starts) - 1):
        start = starts[i]
        end = starts[i + 1]
        section = "\n".join(lines[start:end]).strip()
        if section:
            sections.append(section)
    return sections


def chunk_php_hierarchical(
    text: str, section_max_lines: int = 150, overlap: int = 20
) -> List[str]:
    """Chunk PHP by class/method declarations with line-window fallback."""
    boundary_regex = (
        r"^\s*(abstract\s+class|final\s+class|class|interface|trait|"
        r"public\s+function|protected\s+function|private\s+function|"
        r"function)\b"
    )
    sections = _split_by_regex_boundaries(text, boundary_regex)
    chunks: List[str] = []

    for section in sections:
        line_count = len(section.splitlines())
        if line_count > section_max_lines:
            chunks.extend(chunk_by_lines(section, section_max_lines, overlap))
        else:
            chunks.append(section)

    return chunks


def chunk_js_hierarchical(
    text: str, section_max_lines: int = 60, overlap: int = 10
) -> List[str]:
    """Chunk JS/TS-like code by export/class/function boundaries."""
    boundary_regex = (
        r"^\s*(export\s+(default\s+)?(class|function|const|let|var)|"
        r"class\s+|function\s+|const\s+[A-Za-z0-9_$]+\s*=\s*\(|"
        r"describe\(|test\(|it\()"
    )
    sections = _split_by_regex_boundaries(text, boundary_regex)
    chunks: List[str] = []

    for section in sections:
        line_count = len(section.splitlines())
        if line_count > section_max_lines:
            chunks.extend(chunk_by_lines(section, section_max_lines, overlap))
        else:
            chunks.append(section)

    return chunks


def build_doc_records(filename: str, chunks: List[str], meta: Dict) -> List[Dict]:
    """Build a list of document dicts suitable for DB insertion.

    Each record includes `text`, `title`, `filename`, `category`, `breadcrumb`,
    and `endpoint`.

    The `text` field is enriched with title and breadcrumb for better retrieval.
    """
    records: List[Dict] = []
    title = meta.get("title") or ""
    breadcrumb = meta.get("breadcrumb") or ""

    for i, c in enumerate(chunks):
        # Task B: Prepend context to the text before embedding.
        enriched_text = f"[Title: {title} | Path: {breadcrumb}] \n\n {c}"

        records.append(
            {
                "text": enriched_text,
                "title": title,
                "filename": filename,
                "category": meta.get("category"),
                "breadcrumb": breadcrumb,
                "endpoint": meta.get("endpoint"),  # Prepare for Task E
                "chunk_id": i,  # Task D
            }
        )
    return records


def persist_batch(table, docs: List[Dict]):
    """Persist a batch of docs to `table`.

    `table` is expected to implement an `add(iterable)` method
    (LanceDB-like).

    This wrapper keeps the call site testable. Returns the result of
    `table.add` when present.
    """
    if not docs:
        return None
    if hasattr(table, "add"):
        return table.add(docs)
    # Fallback: try treating table as a callable
    return table(docs)
