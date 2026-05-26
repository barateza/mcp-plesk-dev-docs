import logging
from typing import Protocol, List, Optional
from pathlib import Path
from plesk_unified import chunking, html_utils
from plesk_unified.domain.models import SourceDefinition

logger = logging.getLogger("plesk_unified")


class ParsedDocument:
    def __init__(
        self,
        filename: str,
        title: str,
        breadcrumb: str,
        text: str,
        endpoint: Optional[str] = None,
    ):
        self.filename = filename
        self.title = title
        self.breadcrumb = breadcrumb
        self.text = text
        self.endpoint = endpoint


class SourceProcessor(Protocol):
    def parse(self, file_path: Path) -> Optional[ParsedDocument]:
        """Parse a file and return a ParsedDocument."""
        ...

    def infer_doctype(self, doc: ParsedDocument, source: SourceDefinition) -> str:
        """Infer the document type."""
        ...

    def chunk(
        self, doc: ParsedDocument, source: SourceDefinition, doctype: str
    ) -> List[str]:
        """Chunk the document text."""
        ...


class HtmlSourceProcessor:
    def parse(self, file_path: Path) -> Optional[ParsedDocument]:
        try:
            filename, title, breadcrumb, text, endpoint = html_utils.parse_html(
                file_path
            )
            if not filename or not text:
                return None
            return ParsedDocument(
                filename, title or "", breadcrumb or "", text, endpoint
            )
        except Exception:
            logger.warning("Error parsing HTML file: %s", file_path.name, exc_info=True)
            return None

    def infer_doctype(self, doc: ParsedDocument, source: SourceDefinition) -> str:
        cat = source.category.value
        trail = doc.breadcrumb.lower()
        if cat == "cli" or "command line" in trail:
            return "cli-command"
        if cat == "api" or "reference" in trail:
            return "api-reference"
        if cat == "guide" or "guide" in trail:
            return "guide-topic"
        return f"{cat}-html"

    def chunk(
        self, doc: ParsedDocument, source: SourceDefinition, doctype: str
    ) -> List[str]:
        chunks = chunking.chunk_by_sentence_window(doc.text, window_size=3)
        return chunks or chunking.chunk_by_chars(doc.text, 1500, 200)


class PhpSourceProcessor:
    def parse(self, file_path: Path) -> Optional[ParsedDocument]:
        try:
            text = file_path.read_text(encoding="utf-8", errors="ignore")
            return ParsedDocument(file_path.name, "", "", text)
        except Exception:
            logger.warning("Error parsing PHP file: %s", file_path.name, exc_info=True)
            return None

    def infer_doctype(self, doc: ParsedDocument, source: SourceDefinition) -> str:
        name = (doc.title or doc.filename or "").lower()
        if "interface" in name:
            return "php-stub-interface"
        if "trait" in name:
            return "php-stub-trait"
        return "php-stub-class"

    def chunk(
        self, doc: ParsedDocument, source: SourceDefinition, doctype: str
    ) -> List[str]:
        chunks = chunking.chunk_php_hierarchical(
            doc.text, section_max_lines=150, overlap=20
        )
        return chunks or chunking.chunk_by_lines(doc.text, 150, 20)


class JsSourceProcessor:
    def parse(self, file_path: Path) -> Optional[ParsedDocument]:
        try:
            text = file_path.read_text(encoding="utf-8", errors="ignore")
            return ParsedDocument(file_path.name, "", "", text)
        except Exception:
            logger.warning("Error parsing JS file: %s", file_path.name, exc_info=True)
            return None

    def infer_doctype(self, doc: ParsedDocument, source: SourceDefinition) -> str:
        filename = doc.filename.lower()
        if filename.endswith(".md"):
            return "js-sdk-guide"
        if filename.endswith(".test.js"):
            return "js-sdk-test"
        return "js-sdk-source"

    def chunk(
        self, doc: ParsedDocument, source: SourceDefinition, doctype: str
    ) -> List[str]:
        if doctype == "js-sdk-guide":
            chunks = chunking.chunk_by_sentence_window(doc.text, window_size=3)
            return chunks or chunking.chunk_by_lines(doc.text, 60, 10)

        # Try AST chunking if enabled
        from plesk_unified.settings import settings

        if settings.plesk_enable_ast_chunking:
            lang = "javascript"
            if doc.filename.endswith((".ts", ".tsx")):
                lang = "typescript"
            ast_chunks = chunking.chunk_by_ast(doc.text, lang)
            if ast_chunks:
                return ast_chunks

        js_chunks = chunking.chunk_js_hierarchical(
            doc.text, section_max_lines=60, overlap=10
        )
        return js_chunks or chunking.chunk_by_lines(doc.text, 60, 10)


class ProcessorRegistry:
    def __init__(self):
        self._processors = {
            "html": HtmlSourceProcessor(),
            "php": PhpSourceProcessor(),
            "js": JsSourceProcessor(),
        }

    def get(self, source_type: str) -> SourceProcessor:
        return self._processors.get(
            source_type, HtmlSourceProcessor()
        )  # Fallback to HTML
