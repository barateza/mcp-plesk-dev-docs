import hashlib
import re
import logging
from typing import Dict, List, Optional

logger = logging.getLogger("mcp_plesk_dev_docs")

# Bump this version whenever the chunking logic or context injection changes
# to force a re-embedding of changed chunks while preserving identical ones.
CHUNK_VERSION = "v15"

# Global registry for tree-sitter languages to avoid repeated lookups
_TS_LANGS: dict[str, object] = {}


def _get_ts_lang(lang_name: str):
    """Get or load a tree-sitter language."""
    if lang_name in _TS_LANGS:
        return _TS_LANGS[lang_name]

    try:
        import tree_sitter_language_pack

        lang = tree_sitter_language_pack.get_language(lang_name)
        _TS_LANGS[lang_name] = lang
        return lang
    except Exception:
        return None


def _get_ts_query(lang_name: str) -> Optional[str]:
    """Return the tree-sitter query string for the given language."""
    if lang_name == "php":
        return """
            (class_declaration) @decl
            (function_declaration) @decl
            (method_declaration) @decl
            (interface_declaration) @decl
            (trait_declaration) @decl
        """
    if lang_name in ("javascript", "typescript"):
        return """
            (class_declaration) @decl
            (function_declaration) @decl
            (method_definition) @decl
            (export_statement) @decl
        """
    return None


def chunk_by_ast(
    text: str, lang_name: str, max_chars: int = 1500, overlap: int = 200
) -> Optional[List[str]]:
    """Chunk code using tree-sitter AST nodes (classes, functions, methods)."""
    lang = _get_ts_lang(lang_name)
    query_str = _get_ts_query(lang_name)
    if not lang or not query_str:
        return None

    try:
        from tree_sitter import Parser

        parser = Parser()
        parser.set_language(lang)
        tree = parser.parse(bytes(text, "utf-8"))
        query = lang.query(query_str)
        captures = query.captures(tree.root_node)

        if not captures:
            return None

        chunks = []
        last_end = 0

        for node, _ in captures:
            # Handle gap before this node
            if node.start_byte > last_end:
                gap = text[last_end : node.start_byte].strip()
                if gap:
                    chunks.extend(
                        chunk_by_chars(gap, max_chars, overlap)
                        if len(gap) > max_chars
                        else [gap]
                    )

            block = text[node.start_byte : node.end_byte].strip()
            if block:
                chunks.extend(
                    chunk_by_chars(block, max_chars, overlap)
                    if len(block) > max_chars
                    else [block]
                )
            last_end = node.end_byte

        # Handle tail
        if last_end < len(text):
            tail = text[last_end:].strip()
            if tail:
                chunks.extend(
                    chunk_by_chars(tail, max_chars, overlap)
                    if len(tail) > max_chars
                    else [tail]
                )

        return chunks
    except Exception as e:
        logger.warning("AST chunking failed for %s: %s", lang_name, e)
        return None


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


def chunk_by_sentence_window(
    text: str, window_size: int = 5, overlap: int = 2
) -> List[str]:
    """Build overlapping sentence windows with configurable stride.

    Task C: Increased default window size to 5 for better context.
    The stride is determined by window_size - overlap to prevent chunk explosion.
    """
    if not text:
        return []
    sentences = _split_sentences(text)
    if not sentences:
        return []
    if len(sentences) <= window_size:
        return [" ".join(sentences)]

    chunks: List[str] = []
    step = max(1, window_size - overlap)
    for idx in range(0, len(sentences), step):
        chunk = " ".join(sentences[idx : idx + window_size]).strip()
        if chunk:
            chunks.append(chunk)
        # If this chunk already reached the end, stop to avoid redundant tail chunks
        if idx + window_size >= len(sentences):
            break
    return chunks


def chunk_php_hierarchical(
    text: str, section_max_lines: int = 150, overlap: int = 20
) -> List[str]:
    """Chunk PHP by declarations, preserving docblocks and injecting context.

    Task F: Improved boundary detection and block preservation.
    Phase 5: Structural context injection for better method retrieval.
    """
    if not text:
        return []

    # Regex that matches PHP declarations, optionally preceded by a docblock.
    # Pattern: (/** ... */)? (abstract|final|...)* (class|interface|trait|function)
    boundary_regex = (
        r"(?:/\*\*[\s\S]*?\*/\s*)?"
        r"^\s*(?:abstract\s+|final\s+|public\s+|protected\s+|private\s+|static\s+)*"
        r"(class|interface|trait|function)\s+([a-zA-Z0-9_]+)"
    )

    matches = list(re.finditer(boundary_regex, text, re.MULTILINE))

    if not matches:
        return chunk_by_lines(text, section_max_lines, overlap)

    sections = []
    current_class = ""

    for i, match in enumerate(matches):
        m_type = match.group(1)
        m_name = match.group(2)

        # If there's text before the first match (like <?php)
        if i == 0 and match.start() > 0:
            sections.append(text[0 : match.start()].strip())

        # Determine header for this block
        header = ""
        if m_type == "function" and current_class:
            header = f"// Context: {current_class}::{m_name}\n"
        elif m_type in ("class", "interface", "trait"):
            header = f"// Context: {m_type} {m_name}\n"
            current_class = m_name

        # Find end of this section
        next_start = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        section_text = text[match.start() : next_start].strip()

        if section_text:
            sections.append(f"{header}{section_text}")

    chunks: List[str] = []
    for section in sections:
        if not section:
            continue
        line_count = len(section.splitlines())
        if line_count > section_max_lines:
            chunks.extend(chunk_by_lines(section, section_max_lines, overlap))
        else:
            chunks.append(section)

    return chunks


def chunk_js_hierarchical(
    text: str, section_max_lines: int = 60, overlap: int = 10
) -> List[str]:
    """Chunk JS/TS by export/class/function boundaries, preserving docblocks.

    Task F: Improved boundary detection and block preservation.
    """
    if not text:
        return []

    # Regex for JS declarations, optionally preceded by a docblock
    boundary_regex = (
        r"(?:/\*\*[\s\S]*?\*/\s*)?"
        r"^\s*(?:export\s+(?:default\s+)*)?"
        r"(?:class|function|const|let|var|describe|test|it)\b"
    )

    sections = []
    matches = list(re.finditer(boundary_regex, text, re.MULTILINE))

    if not matches:
        return chunk_by_lines(text, section_max_lines, overlap)

    last_pos = 0
    for match in matches:
        if match.start() > last_pos:
            section = text[last_pos : match.start()].strip()
            if section:
                sections.append(section)
        last_pos = match.start()

    if last_pos < len(text):
        sections.append(text[last_pos:].strip())

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
    `doctype`, `endpoint` and `summary`.

    The `text` field is enriched with metadata for better retrieval.
    """
    records: List[Dict] = []
    title = meta.get("title") or ""
    breadcrumb = meta.get("breadcrumb") or ""
    summary = meta.get("summary")
    endpoint = meta.get("endpoint")

    for i, c in enumerate(chunks):
        # Task B & Phase 2: Prepend context to the text before embedding.
        category = meta.get("category", "unknown").upper()
        doctype = meta.get("doctype", "unknown")

        header = f"[{category}] DocType: {doctype}\n"
        header += f"[Title: {title} | Path: {breadcrumb}] \n"
        if endpoint:
            header += f"[Endpoint: {endpoint}] \n"
        if summary:
            header += f"[Summary: {summary}] \n"

        enriched_text = f"{header}\n {c}"

        # Strategy 2: Per-chunk fingerprinting
        # Includes enriched_text (which has all context) and logic version.
        h = hashlib.sha256()
        h.update(f"{CHUNK_VERSION}:{enriched_text}".encode("utf-8"))
        chunk_hash = h.hexdigest()

        records.append(
            {
                "text": enriched_text,
                "title": title,
                "filename": filename,
                "category": meta.get("category"),
                "breadcrumb": breadcrumb,
                "doctype": meta.get("doctype", "unknown"),
                "endpoint": endpoint,
                "summary": summary,
                "chunk_id": i,
                "chunk_hash": chunk_hash,
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
