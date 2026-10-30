"""HTTP providers for Claude (Anthropic Messages API), OpenAI and a local Ollama model.

Providers talk to the vendor APIs directly over httpx so the service has no vendor SDK
dependency. The Anthropic provider sends the system prompt as a cached block, which lowers
cost and latency for repeated consultations with the same instructions.
"""

from __future__ import annotations

import json
from collections.abc import Iterator

import httpx

from fovea.llm.base import GenerationRequest, GenerationResult, ProviderError

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
OPENAI_URL = "https://api.openai.com/v1/chat/completions"


class AnthropicProvider:
    name = "anthropic"

    def __init__(
        self, api_key: str, model: str, timeout: float, transport: httpx.BaseTransport | None = None
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.client = httpx.Client(timeout=timeout, transport=transport)

    def available(self) -> bool:
        return bool(self.api_key)

    def _payload(self, request: GenerationRequest, stream: bool) -> dict[str, object]:
        system: list[dict[str, object]] = [{"type": "text", "text": request.system}]
        if request.cache_system:
            system[0]["cache_control"] = {"type": "ephemeral"}
        return {
            "model": self.model,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "system": system,
            "messages": [{"role": "user", "content": request.user}],
            "stream": stream,
        }

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self.api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        }

    def generate(self, request: GenerationRequest) -> GenerationResult:
        if not self.available():
            raise ProviderError("Anthropic API key is not configured")
        try:
            response = self.client.post(
                ANTHROPIC_URL, headers=self._headers(), json=self._payload(request, False)
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ProviderError(f"Anthropic request failed: {exc}") from exc
        data = response.json()
        text = "".join(
            block.get("text", "") for block in data.get("content", []) if block.get("type") == "text"
        )
        usage = data.get("usage", {})
        return GenerationResult(
            text, self.name, self.model, usage.get("input_tokens"), usage.get("output_tokens")
        )

    def stream(self, request: GenerationRequest) -> Iterator[str]:
        if not self.available():
            raise ProviderError("Anthropic API key is not configured")
        try:
            with self.client.stream(
                "POST", ANTHROPIC_URL, headers=self._headers(), json=self._payload(request, True)
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line.startswith("data:"):
                        continue
                    event = json.loads(line[5:].strip() or "{}")
                    if (
                        event.get("type") == "content_block_delta"
                        and event.get("delta", {}).get("type") == "text_delta"
                    ):
                        yield event["delta"]["text"]
        except httpx.HTTPError as exc:
            raise ProviderError(f"Anthropic stream failed: {exc}") from exc


class OpenAIProvider:
    name = "openai"

    def __init__(
        self, api_key: str, model: str, timeout: float, transport: httpx.BaseTransport | None = None
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.client = httpx.Client(timeout=timeout, transport=transport)

    def available(self) -> bool:
        return bool(self.api_key)

    def _payload(self, request: GenerationRequest, stream: bool) -> dict[str, object]:
        return {
            "model": self.model,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "messages": [
                {"role": "system", "content": request.system},
                {"role": "user", "content": request.user},
            ],
            "stream": stream,
        }

    def generate(self, request: GenerationRequest) -> GenerationResult:
        if not self.available():
            raise ProviderError("OpenAI API key is not configured")
        try:
            response = self.client.post(
                OPENAI_URL,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=self._payload(request, False),
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ProviderError(f"OpenAI request failed: {exc}") from exc
        data = response.json()
        usage = data.get("usage", {})
        return GenerationResult(
            data["choices"][0]["message"]["content"],
            self.name,
            self.model,
            usage.get("prompt_tokens"),
            usage.get("completion_tokens"),
        )

    def stream(self, request: GenerationRequest) -> Iterator[str]:
        if not self.available():
            raise ProviderError("OpenAI API key is not configured")
        try:
            with self.client.stream(
                "POST",
                OPENAI_URL,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=self._payload(request, True),
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line.startswith("data:") or line.strip() == "data: [DONE]":
                        continue
                    delta = json.loads(line[5:].strip())["choices"][0].get("delta", {}).get("content")
                    if delta:
                        yield delta
        except httpx.HTTPError as exc:
            raise ProviderError(f"OpenAI stream failed: {exc}") from exc


class OllamaProvider:
    name = "ollama"

    def __init__(
        self, url: str, model: str, timeout: float, transport: httpx.BaseTransport | None = None
    ) -> None:
        self.url = url.rstrip("/")
        self.model = model
        self.client = httpx.Client(timeout=timeout, transport=transport)

    def available(self) -> bool:
        return bool(self.url)

    def _payload(self, request: GenerationRequest, stream: bool) -> dict[str, object]:
        return {
            "model": self.model,
            "stream": stream,
            "options": {"temperature": request.temperature, "num_predict": request.max_tokens},
            "messages": [
                {"role": "system", "content": request.system},
                {"role": "user", "content": request.user},
            ],
        }

    def generate(self, request: GenerationRequest) -> GenerationResult:
        try:
            response = self.client.post(f"{self.url}/api/chat", json=self._payload(request, False))
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ProviderError(f"Ollama request failed: {exc}") from exc
        data = response.json()
        return GenerationResult(
            data["message"]["content"],
            self.name,
            self.model,
            data.get("prompt_eval_count"),
            data.get("eval_count"),
        )

    def stream(self, request: GenerationRequest) -> Iterator[str]:
        try:
            with self.client.stream(
                "POST", f"{self.url}/api/chat", json=self._payload(request, True)
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if line.strip():
                        piece = json.loads(line).get("message", {}).get("content")
                        if piece:
                            yield piece
        except httpx.HTTPError as exc:
            raise ProviderError(f"Ollama stream failed: {exc}") from exc
