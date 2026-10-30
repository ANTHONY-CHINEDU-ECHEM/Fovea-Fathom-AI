"""Provider neutral language model interface."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Protocol


class ProviderError(RuntimeError):
    """Raised when a provider cannot produce an answer; the router then falls back."""


@dataclass
class GenerationRequest:
    system: str
    user: str
    max_tokens: int = 1400
    temperature: float = 0.1
    cache_system: bool = True


@dataclass
class GenerationResult:
    text: str
    provider: str
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    metadata: dict[str, object] = field(default_factory=dict)


class LLMProvider(Protocol):
    name: str
    model: str

    def available(self) -> bool: ...

    def generate(self, request: GenerationRequest) -> GenerationResult: ...

    def stream(self, request: GenerationRequest) -> Iterator[str]: ...
