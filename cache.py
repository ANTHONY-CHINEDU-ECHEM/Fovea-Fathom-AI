"""Answer cache keyed on the redacted question, the de identified context and the provider.

Answers that raised an emergency are never cached, so the banner is always re evaluated.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from collections import OrderedDict
from typing import Any, Protocol


class AnswerCache(Protocol):
    def get(self, key: str) -> dict[str, Any] | None: ...

    def set(self, key: str, value: dict[str, Any], ttl: int) -> None: ...


def cache_key(question: str, context: dict[str, Any], provider: str | None, index_version: str) -> str:
    payload = json.dumps(
        {"q": question.strip().lower(), "c": context, "p": provider, "v": index_version}, sort_keys=True
    )
    return "fovea:answer:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


class MemoryCache:
    def __init__(self, max_items: int = 512) -> None:
        self.items: OrderedDict[str, tuple[float, dict[str, Any]]] = OrderedDict()
        self.max_items = max_items
        self._lock = threading.Lock()

    def get(self, key: str) -> dict[str, Any] | None:
        with self._lock:
            entry = self.items.get(key)
            if not entry:
                return None
            expires, value = entry
            if expires < time.time():
                self.items.pop(key, None)
                return None
            self.items.move_to_end(key)
            return value

    def set(self, key: str, value: dict[str, Any], ttl: int) -> None:
        with self._lock:
            self.items[key] = (time.time() + ttl, value)
            self.items.move_to_end(key)
            while len(self.items) > self.max_items:
                self.items.popitem(last=False)


class RedisCache:
    def __init__(self, url: str) -> None:
        import redis  # optional dependency

        self.client = redis.Redis.from_url(url)

    def get(self, key: str) -> dict[str, Any] | None:
        raw = self.client.get(key)
        return json.loads(raw) if raw else None

    def set(self, key: str, value: dict[str, Any], ttl: int) -> None:
        self.client.setex(key, ttl, json.dumps(value))


def build_cache(backend: str, redis_url: str) -> AnswerCache:
    if backend == "redis":
        try:
            return RedisCache(redis_url)
        except Exception:  # fall back rather than fail a clinic
            return MemoryCache()
    return MemoryCache()
