"""Bounded in-process LRU cache for expanded search results.

The search pipeline is expensive (query embedding, vector scan, cross-encoder
rerank, neighbour expansion) and agent sessions tend to repeat the same handful
of lookups. A small LRU removes that work from repeat calls without adding a
dependency.

Searches run in the shared thread-pool executor, so every operation is guarded
by a ``threading.Lock``. Entry order is the LRU order: the least recently used
key is evicted first once ``maxsize`` is exceeded.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from typing import Any, Hashable


class QueryCache:
    """Thread-safe bounded LRU cache mapping hashable keys to result payloads."""

    def __init__(self, maxsize: int = 256) -> None:
        if maxsize < 1:
            raise ValueError("QueryCache maxsize must be at least 1")
        self._maxsize = maxsize
        self._entries: OrderedDict[Hashable, Any] = OrderedDict()
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    @property
    def maxsize(self) -> int:
        """Maximum number of cached entries."""
        return self._maxsize

    def get(self, key: Hashable) -> Any | None:
        """Return the cached payload for *key*, or ``None`` on a miss."""
        with self._lock:
            if key not in self._entries:
                self._misses += 1
                return None
            self._entries.move_to_end(key)
            self._hits += 1
            return self._entries[key]

    def set(self, key: Hashable, value: Any) -> None:
        """Store *value* under *key*, evicting the least recently used entry."""
        with self._lock:
            self._entries[key] = value
            self._entries.move_to_end(key)
            while len(self._entries) > self._maxsize:
                self._entries.popitem(last=False)

    def clear(self) -> None:
        """Drop every cached entry; hit/miss counters are preserved."""
        with self._lock:
            self._entries.clear()

    def stats(self) -> dict[str, int]:
        """Return a snapshot of ``hits``, ``misses`` and ``entries``."""
        with self._lock:
            return {
                "hits": self._hits,
                "misses": self._misses,
                "entries": len(self._entries),
            }
