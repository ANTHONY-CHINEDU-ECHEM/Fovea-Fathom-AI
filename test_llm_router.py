import json
from collections.abc import Iterator

import httpx
import pytest

from fovea.config import Settings
from fovea.llm.base import GenerationRequest, GenerationResult, ProviderError
from fovea.llm.providers import AnthropicProvider, OllamaProvider, OpenAIProvider
from fovea.llm.router import CircuitBreaker, LLMRouter

REQUEST = GenerationRequest("system", "user")


class FakeProvider:
    def __init__(self, name: str, fail: bool = False, configured: bool = True) -> None:
        self.name, self.model, self.fail, self.configured, self.calls = (
            name,
            f"{name}-model",
            fail,
            configured,
            0,
        )

    def available(self) -> bool:
        return self.configured

    def generate(self, request: GenerationRequest) -> GenerationResult:
        return GenerationResult("x", self.name, self.model)

    def stream(self, request: GenerationRequest) -> Iterator[str]:
        self.calls += 1
        if self.fail:
            raise ProviderError("down")
        yield from ["Answer ", "text [1]."]


def _router(**providers: FakeProvider) -> LLMRouter:
    settings = Settings(
        llm_provider="anthropic",
        llm_fallbacks=["openai", "ollama"],
        circuit_failure_threshold=2,
        circuit_reset_seconds=60,
    )
    return LLMRouter(settings, providers=dict(providers))


def _extractive() -> Iterator[str]:
    yield "extractive [1]."


def test_primary_used_when_healthy() -> None:
    router = _router(
        anthropic=FakeProvider("anthropic"), openai=FakeProvider("openai"), ollama=FakeProvider("ollama")
    )
    tokens, outcome = router.stream(REQUEST, None, _extractive)
    assert "".join(tokens) == "Answer text [1]." and outcome.provider == "anthropic" and not outcome.fallbacks


def test_falls_back_then_opens_circuit() -> None:
    primary = FakeProvider("anthropic", fail=True)
    router = _router(
        anthropic=primary, openai=FakeProvider("openai", configured=False), ollama=FakeProvider("ollama")
    )
    for _ in range(2):
        tokens, outcome = router.stream(REQUEST, None, _extractive)
        assert outcome.provider == "ollama" and "anthropic" in outcome.fallbacks
        list(tokens)
    assert router.breakers["anthropic"].state == "open"
    router.stream(REQUEST, None, _extractive)
    assert primary.calls == 2


def test_extractive_closes_the_chain() -> None:
    router = _router(
        anthropic=FakeProvider("anthropic", fail=True),
        openai=FakeProvider("openai", fail=True),
        ollama=FakeProvider("ollama", fail=True),
    )
    tokens, outcome = router.stream(REQUEST, None, _extractive)
    assert outcome.provider == "extractive" and "".join(tokens) == "extractive [1]."


def test_preferred_provider_goes_first() -> None:
    router = _router(
        anthropic=FakeProvider("anthropic"), openai=FakeProvider("openai"), ollama=FakeProvider("ollama")
    )
    _, outcome = router.stream(REQUEST, "ollama", _extractive)
    assert outcome.provider == "ollama"


def test_circuit_half_opens_after_reset() -> None:
    breaker = CircuitBreaker(threshold=1, reset_seconds=0.0)
    breaker.failure()
    assert breaker.state == "half_open" and breaker.allow()


def _sse(events: list[dict]) -> str:
    return "".join(f"data: {json.dumps(e)}\n\n" for e in events)


def test_anthropic_streaming_and_cached_system_prompt() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        seen["headers"] = request.headers
        body = _sse(
            [
                {"type": "message_start"},
                {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "Hello"}},
                {"type": "content_block_delta", "delta": {"type": "text_delta", "text": " world"}},
                {"type": "message_stop"},
            ]
        )
        return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})

    provider = AnthropicProvider("key", "claude-model", 5, transport=httpx.MockTransport(handler))
    assert "".join(provider.stream(REQUEST)) == "Hello world"
    assert seen["body"]["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert seen["headers"]["x-api-key"] == "key"


def test_openai_and_ollama_streaming() -> None:
    def openai(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, text=_sse([{"choices": [{"delta": {"content": "Hi"}}]}]) + "data: [DONE]\n\n"
        )

    def ollama(request: httpx.Request) -> httpx.Response:
        lines = [
            json.dumps({"message": {"content": "Lo"}}),
            json.dumps({"message": {"content": "cal"}, "done": True}),
        ]
        return httpx.Response(200, text="\n".join(lines))

    assert "".join(OpenAIProvider("k", "m", 5, transport=httpx.MockTransport(openai)).stream(REQUEST)) == "Hi"
    assert (
        "".join(
            OllamaProvider("http://ollama", "m", 5, transport=httpx.MockTransport(ollama)).stream(REQUEST)
        )
        == "Local"
    )


def test_http_errors_become_provider_errors() -> None:
    provider = AnthropicProvider("key", "m", 5, transport=httpx.MockTransport(lambda r: httpx.Response(529)))
    with pytest.raises(ProviderError):
        list(provider.stream(REQUEST))
    with pytest.raises(ProviderError):
        AnthropicProvider("", "m", 5).generate(REQUEST)
