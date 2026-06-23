# FUTURE: Online tile-based viewport rendering. Implemented, zero consumers.
"""Bounded LRU cache for rendered tile data.

``TileCache`` stores arbitrary bytes objects keyed by ``TileKey``.
Eviction is based on total bytes consumed (not entry count).  When a
``put`` would exceed ``max_bytes``, the least recently used entries are
evicted until the new entry fits (or until the cache is empty).

Usage::

    cache = TileCache(max_bytes=64 * 1024 * 1024)  # 64 MiB
    cache.put(key, tile_bytes)
    data = cache.get(key)
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Optional

from .tile_grid import TileKey


class TileCache:
    """LRU cache with byte-based capacity and eviction.

    Parameters
    ----------
    max_bytes:
        Soft upper bound on total bytes stored.  A single entry larger
        than *max_bytes* is still accepted (it drains the cache first).
    """

    def __init__(self, max_bytes: int) -> None:
        if max_bytes <= 0:
            raise ValueError(f"max_bytes must be positive: {max_bytes}")
        self._max_bytes = max_bytes
        self._total_bytes: int = 0
        # OrderedDict: first item = least recently used, last = most recent
        self._store: OrderedDict[TileKey, bytes] = OrderedDict()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def max_bytes(self) -> int:
        return self._max_bytes

    @property
    def total_bytes(self) -> int:
        return self._total_bytes

    def __len__(self) -> int:
        return len(self._store)

    def get(self, key: TileKey) -> Optional[bytes]:
        """Return cached data for *key*, or ``None``.

        Access counts as "use" and moves the entry to the MRU end.
        """
        if key not in self._store:
            return None
        self._store.move_to_end(key)
        return self._store[key]

    def contains(self, key: TileKey) -> bool:
        """Return ``True`` if *key* is cached (without changing LRU order)."""
        return key in self._store

    def put(self, key: TileKey, data: bytes) -> None:
        """Store *data* under *key*, evicting LRU entries if needed.

        If *key* already exists its old value is replaced (and LRU
        order is updated).  *data* size is measured via ``len(data)``.
        """
        new_size = len(data)

        # If key already exists, account for the size delta
        if key in self._store:
            old_size = len(self._store[key])
            self._store.move_to_end(key)
            self._store[key] = data
            self._total_bytes += new_size - old_size
        else:
            # Make room for the new entry
            while self._store and self._total_bytes + new_size > self._max_bytes:
                self._evict_lru()
            self._store[key] = data
            self._total_bytes += new_size
            # Entry was just added at the end (MRU)

    def clear(self) -> None:
        """Remove all cached entries and reset byte counter."""
        self._store.clear()
        self._total_bytes = 0

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _evict_lru(self) -> None:
        """Evict the least recently used entry (first in OrderedDict)."""
        if not self._store:
            return
        evicted_key, evicted_data = self._store.popitem(last=False)
        self._total_bytes -= len(evicted_data)
