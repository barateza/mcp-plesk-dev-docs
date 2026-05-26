import json
import logging
import hashlib
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger("plesk_unified")


class SummaryCacheRepository:
    """Persistent repository for AI-generated summaries by file hash."""

    def __init__(self, cache_path: Path):
        self.cache_path = cache_path
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
        if self.cache_path.exists():
            try:
                with open(self.cache_path, "r", encoding="utf-8") as f:
                    self.cache = json.load(f)
                logger.info("Loaded %d summaries from cache.", len(self.cache))
            except Exception as e:
                logger.error("Failed to load summary cache: %s", e)
                self.cache = {}

    def save(self):
        """Saves cache to disk."""
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.cache_path, "w", encoding="utf-8") as f:
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
