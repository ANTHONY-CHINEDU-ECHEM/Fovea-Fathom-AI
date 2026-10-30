"""API key authentication and a sliding window rate limiter per key or client address."""

from __future__ import annotations

import hmac
import threading
import time
from collections import defaultdict, deque

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import APIKeyHeader

from fovea.config import get_settings

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


class RateLimiter:
    def __init__(self) -> None:
        self.windows: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, identity: str, limit: int, window_seconds: float = 60.0) -> bool:
        now = time.monotonic()
        with self._lock:
            window = self.windows[identity]
            while window and now - window[0] > window_seconds:
                window.popleft()
            if len(window) >= limit:
                return False
            window.append(now)
            return True


LIMITER = RateLimiter()


def _matches(candidate: str | None, keys: list[str]) -> bool:
    return bool(candidate) and any(hmac.compare_digest(candidate or "", k) for k in keys)


def require_api_key(request: Request, api_key: str | None = Depends(API_KEY_HEADER)) -> str:
    settings = get_settings()
    if settings.api_keys and not _matches(api_key, settings.api_keys + settings.admin_api_keys):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "A valid API key is required")
    identity = api_key or (request.client.host if request.client else "anonymous")
    if not LIMITER.check(identity, settings.rate_limit_per_minute):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "Rate limit exceeded", headers={"Retry-After": "60"}
        )
    return identity


def require_admin(api_key: str | None = Depends(API_KEY_HEADER)) -> str:
    settings = get_settings()
    if not settings.admin_api_keys:
        if settings.is_production:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin keys are not configured")
        return "development"
    if not _matches(api_key, settings.admin_api_keys):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "An admin API key is required")
    return api_key or ""
