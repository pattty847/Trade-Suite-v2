from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class CacheEntry(Generic[T]):
    value: T
    created_at: datetime
    ttl: timedelta

    @property
    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) >= self.created_at + self.ttl


class CacheStore(ABC, Generic[T]):
    @abstractmethod
    def get(self, key: str) -> T | None:
        raise NotImplementedError

    @abstractmethod
    def put(self, key: str, value: T, ttl: timedelta) -> None:
        raise NotImplementedError

    @abstractmethod
    def invalidate(self, key: str) -> None:
        raise NotImplementedError
