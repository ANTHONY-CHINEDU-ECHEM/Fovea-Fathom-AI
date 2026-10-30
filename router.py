"""Model router with ordered fallbacks and a circuit breaker per vendor.

The router tries the selected provider, then each configured fallback, and always ends with
the extractive generator, which cannot fail. A provider that fails repeatedly is opened (skipped)
for a cooling period so a vendor outage during a clinic does not add latency to every question.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field

from fovea.config import Settings
from fovea.llm.base import GenerationRequest, LLMProvider, ProviderError
from fovea.llm.providers import AnthropicProvider, OllamaProvider, OpenAIProvider

log = logging.getLogger(__name__)


@dataclass
class CircuitBreaker:
    threshold: int
    reset_seconds: float
    failures: int = 0
    opened_at: float | None = None

    @property
    def state(self) -> str:
        if self.opened_at is None:
            return "closed"
        if time.monotonic() - self.opened_at >= self.reset_seconds:
            return "half_open"
        return "open"

    def allow(self) -> bool:
        return self.state != "open"

    def success(self) -> None:
        self.failures = 0
        self.opened_at = None

    def failure(self) -> None:
        self.failures += 1
        if self.failures >= self.threshold:
            self.opened_at = time.monotonic()


@dataclass
class RouteOutcome:
    provider: str
    model: str
    fallbacks: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class LLMRouter:
    def __init__(self, settings: Settings, providers: dict[str, LLMProvider] | None = None) -> None:
        self.settings = settings
        self.providers: dict[str, LLMProvider] = providers or {
            "anthropic": AnthropicProvider(
                settings.anthropic_api_key, settings.anthropic_model, settings.llm_timeout_seconds
            ),
            "openai": OpenAIProvider(
                settings.openai_api_key, settings.openai_model, settings.llm_timeout_seconds
            ),
            "ollama": OllamaProvider(
                settings.ollama_url, settings.ollama_model, settings.llm_timeout_seconds
            ),
        }
        self.breakers = {
            name: CircuitBreaker(settings.circuit_failure_threshold, settings.circuit_reset_seconds)
            for name in self.providers
        }

    def chain(self, preferred: str | None = None) -> list[str]:
        return self.settings.provider_chain(preferred)

    def status(self) -> list[dict[str, object]]:
        out = []
        for name in self.chain():
            if name == "extractive":
                out.append({"provider": "extractive", "configured": True, "circuit": "closed"})
                continue
            provider = self.providers.get(name)
            out.append(
                {
                    "provider": name,
                    "model": getattr(provider, "model", None),
                    "configured": bool(provider and provider.available()),
                    "circuit": self.breakers[name].state if name in self.breakers else "unknown",
                }
            )
        return out

    def stream(
        self, request: GenerationRequest, preferred: str | None, extractive: Callable[[], Iterator[str]]
    ) -> tuple[Iterator[str], RouteOutcome]:
        """Return a token iterator from the first provider that starts streaming successfully.

        The first chunk is pulled eagerly so a provider that fails before producing any text
        falls back cleanly; a failure after text has streamed is reported as an error.
        """
        outcome = RouteOutcome(provider="extractive", model="extractive")
        for name in self.chain(preferred):
            if name == "extractive":
                outcome.provider, outcome.model = "extractive", "extractive"
                return extractive(), outcome
            provider = self.providers.get(name)
            breaker = self.breakers.get(name)
            if provider is None or breaker is None or not provider.available() or not breaker.allow():
                outcome.fallbacks.append(name)
                continue
            try:
                iterator = provider.stream(request)
                first = next(iterator)
            except (ProviderError, StopIteration) as exc:
                breaker.failure()
                outcome.fallbacks.append(name)
                outcome.errors.append(f"{name}: {exc or 'empty response'}")
                log.warning("provider %s failed, falling back: %s", name, exc)
                continue
            breaker.success()
            outcome.provider, outcome.model = name, provider.model

            def chained(first: str = first, rest: Iterator[str] = iterator) -> Iterator[str]:
                yield first
                yield from rest

            return chained(), outcome
        return extractive(), outcome
