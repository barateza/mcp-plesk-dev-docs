from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from plesk_unified.types import CategoryEnum


@dataclass(frozen=True)
class SourceDefinition:
    category: CategoryEnum
    path: Path
    source_type: str  # "html", "php", "js"
    repo_url: Optional[str] = None
    zip_url: Optional[str] = None

    @property
    def doc_base_url(self) -> Optional[str]:
        if not self.zip_url:
            return None
        # Pattern: https://.../zip/<name>.zip  →  https://.../<name>/
        return self.zip_url.replace("/zip/", "/").removesuffix(".zip") + "/"

    def build_doc_url(self, filename: str) -> Optional[str]:
        base = self.doc_base_url
        if base and filename:
            return base + filename
        return None
