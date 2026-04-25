from pathlib import Path
from typing import List, Optional
from plesk_unified.domain.models import SourceDefinition
from plesk_unified.types import CategoryEnum

# Base directory for the knowledge base
# This assumes it's relative to the project root
BASE_DIR = Path(__file__).parent.parent.parent
KB_DIR = BASE_DIR / "knowledge_base"


class SourceCatalog:
    def __init__(self, sources: List[SourceDefinition]):
        self._sources = sources
        self._by_category = {s.category.value: s for s in sources}

    def all(self) -> List[SourceDefinition]:
        return self._sources

    def by_category(self, category: str) -> Optional[SourceDefinition]:
        return self._by_category.get(category)

    @classmethod
    def default(cls, kb_dir: Path) -> "SourceCatalog":
        return cls(
            [
                SourceDefinition(
                    category=CategoryEnum.PHP_STUBS,
                    path=kb_dir / "stubs",
                    source_type="php",
                    repo_url="https://github.com/plesk/pm-api-stubs.git",
                ),
                SourceDefinition(
                    category=CategoryEnum.JS_SDK,
                    path=kb_dir / "sdk",
                    source_type="js",
                    repo_url="https://github.com/plesk/plesk-ext-sdk.git",
                ),
                SourceDefinition(
                    category=CategoryEnum.API,
                    path=kb_dir / "api-rpc",
                    source_type="html",
                    zip_url="https://docs.plesk.com/en-US/obsidian/zip/api-rpc.zip",
                ),
                SourceDefinition(
                    category=CategoryEnum.CLI,
                    path=kb_dir / "cli-linux",
                    source_type="html",
                    zip_url="https://docs.plesk.com/en-US/obsidian/zip/cli-linux.zip",
                ),
                SourceDefinition(
                    category=CategoryEnum.GUIDE,
                    path=kb_dir / "extensions-guide",
                    source_type="html",
                    zip_url="https://docs.plesk.com/en-US/obsidian/zip/extensions-guide.zip",
                ),
            ]
        )


# Global default catalog for legacy support if needed
# But we should prefer using the AppContainer later
DEFAULT_SOURCES = SourceCatalog.default(KB_DIR)
