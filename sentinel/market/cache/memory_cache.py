from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sentinel.market.cache.base import CacheEntry, CacheStore, T


class InMemoryCacheStore(CacheStore[T]):
    def __init__(self) -> None:
        self._store: dict[str, CacheEntry[T]] = {}

    def get(self, key: str) -> T | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        if entry.is_expired:
            self._store.pop(key, None)
            return None
        return entry.value

    def put(self, key: str, value: T, ttl: timedelta) -> None:
        self._store[key] = CacheEntry(
            value=value,
            created_at=datetime.now(timezone.utc),
            ttl=ttl,
        )

    def invalidate(self, key: str) -> None:
        self._store.pop(key, None)
