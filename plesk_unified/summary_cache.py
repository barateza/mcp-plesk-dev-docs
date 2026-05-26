import json
import logging
import hashlib
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

CACHE_FILE = Path("storage/summaries_cache.json")


class SummaryCache:
    """A persistent cache for AI-generated summaries indexed by file content hash."""

    def __init__(self):
        self.cache: Dict[str, str] = {}
        self._load()

    def _get_file_hash(self, file_path: Path) -> str:
        """Computes MD5 hash of file content."""
        hasher = hashlib.md5(usedforsecurity=False)
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    def _load(self):
        """Loads cache from disk."""
        if CACHE_FILE.exists():
            try:
                with open(CACHE_FILE, "r", encoding="utf-8") as f:
                    self.cache = json.load(f)
                logger.info("Loaded %d summaries from cache.", len(self.cache))
            except Exception as e:
                logger.error("Failed to load summary cache: %s", e)
                self.cache = {}

    def save(self):
        """Saves cache to disk."""
        try:
            CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error("Failed to save summary cache: %s", e)

    def get(self, file_path: Path) -> Optional[str]:
        """Retrieves a cached summary if the file hasn't changed."""
        file_hash = self._get_file_hash(file_path)
        return self.cache.get(file_hash)

    def set(self, file_path: Path, summary: str):
        """Stores a summary in the cache."""
        file_hash = self._get_file_hash(file_path)
        self.cache[file_hash] = summary
