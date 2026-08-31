"""Tiny in-process TTL cache for hot entitlement reads (subscriptions, seats).

Entitlements change mid-session (owner revokes a seat, quota burns down) so the
TTL is deliberately short. AI quota is read live (never cached) for accuracy.
"""
from __future__ import annotations
import time
import threading
from typing import Any, Callable, Optional

_DEFAULT_TTL = float(__import__("os").getenv("ENTITLEMENTS_CACHE_TTL", "20"))


class TTLCache:
    def __init__(self, ttl: float = _DEFAULT_TTL):
        self.ttl = ttl
        self._store: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get_or_set(self, key: str, producer: Callable[[], Any]) -> Any:
        now = time.time()
        with self._lock:
            hit = self._store.get(key)
            if hit and hit[0] > now:
                return hit[1]
        value = producer()  # produce outside lock (may do I/O)
        with self._lock:
            self._store[key] = (now + self.ttl, value)
        return value

    def invalidate(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()


cache = TTLCache()
