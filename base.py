"""Polite HTTP harvesting shared by every connector.

* A token bucket per host keeps request rates within each provider's published limits.
* Retries use exponential backoff with jitter and honour ``Retry-After``.
* HTML pages are fetched only after checking ``robots.txt``.
* Every connector yields :class:`~fovea.domain.Document` objects and never holds a whole
  corpus in memory.
"""

from __future__ import annotations

import logging
import random
import threading
import time
import urllib.robotparser
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlparse

import httpx

from fovea.domain import Document

log = logging.getLogger(__name__)
USER_AGENT = "FoveaFathomAI/1.0 (evidence harvester for clinical decision support; contact via repository)"


@dataclass
class TokenBucket:
    rate_per_second: float
    capacity: float
    tokens: float = 0.0
    updated: float = 0.0

    def __post_init__(self) -> None:
        self.tokens = self.capacity
        self.updated = time.monotonic()
        self._lock = threading.Lock()

    def take(self) -> None:
        with self._lock:
            while True:
                now = time.monotonic()
                self.tokens = min(self.capacity, self.tokens + (now - self.updated) * self.rate_per_second)
                self.updated = now
                if self.tokens >= 1:
                    self.tokens -= 1
                    return
                time.sleep((1 - self.tokens) / self.rate_per_second)


class PoliteClient:
    def __init__(
        self,
        rate_per_second: float = 3.0,
        max_retries: int = 5,
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
        sleep: Any = time.sleep,
    ) -> None:
        self.client = httpx.Client(
            timeout=timeout, headers={"User-Agent": USER_AGENT}, transport=transport, follow_redirects=True
        )
        self.rate = rate_per_second
        self.buckets: dict[str, TokenBucket] = {}
        self.max_retries = max_retries
        self.robots: dict[str, urllib.robotparser.RobotFileParser] = {}
        self.sleep = sleep

    def _bucket(self, host: str) -> TokenBucket:
        if host not in self.buckets:
            self.buckets[host] = TokenBucket(self.rate, max(1.0, self.rate))
        return self.buckets[host]

    def allowed(self, url: str) -> bool:
        parsed = urlparse(url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        if base not in self.robots:
            parser = urllib.robotparser.RobotFileParser()
            try:
                response = self.client.get(f"{base}/robots.txt")
                parser.parse(response.text.splitlines() if response.status_code == 200 else [])
            except httpx.HTTPError:
                parser.parse([])
            self.robots[base] = parser
        return self.robots[base].can_fetch(USER_AGENT, url)

    def get(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        check_robots: bool = False,
    ) -> httpx.Response:
        if check_robots and not self.allowed(url):
            raise PermissionError(f"robots.txt disallows {url}")
        host = urlparse(url).netloc
        attempt = 0
        while True:
            self._bucket(host).take()
            try:
                response = self.client.get(url, params=params, headers=headers)
            except httpx.TransportError as exc:
                response = None
                error: Exception | None = exc
            else:
                error = None
            if response is not None and response.status_code < 400:
                return response
            retryable = response is None or response.status_code in {429, 500, 502, 503, 504}
            attempt += 1
            if not retryable or attempt > self.max_retries:
                if response is not None:
                    response.raise_for_status()
                raise error or RuntimeError(f"request to {url} failed")
            delay = min(60.0, (2**attempt) + random.uniform(0, 1))
            if response is not None and "retry-after" in response.headers:
                try:
                    delay = max(delay, float(response.headers["retry-after"]))
                except ValueError:
                    pass
            log.info("retrying %s in %.1fs (attempt %d)", url, delay, attempt)
            self.sleep(delay)


class Connector(Protocol):
    name: str

    def harvest(self, limit: int | None = None) -> Iterator[Document]: ...
