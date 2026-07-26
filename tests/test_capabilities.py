from __future__ import annotations

from typing import Generator

import pytest

from app.ai.providers.base import (
    AIProvider,
    AIProviderError,
    AIResponse,
    AIStreamChunk,
    AIStreamResponse,
    AllProvidersFailedError,
    ProviderCapability,
)
from app.ai.manager import AIManager
from app.ai.router import AIRouter
from app.ai.routing import RoutingConfig


class _MockProvider:
    def __init__(
        self,
        provider_name: str,
        capabilities: frozenset[ProviderCapability] | None = None,
        available: bool = True,
        generate_result: str | None = None,
    ) -> None:
        self.provider_name = provider_name
        self.capabilities = capabilities or frozenset()
        self._available = available
        self._generate_result = generate_result

    def generate(self, prompt: str) -> AIResponse:
        text = self._generate_result or f"{self.provider_name}: {prompt}"
        return AIResponse(text, provider=self.provider_name, model="test", latency_ms=0.0)

    def check_availability(self) -> bool:
        return self._available

    def generate_stream(self, prompt: str) -> Generator[AIStreamChunk, None, None]:
        yield AIStreamChunk(content="streamed")


class _StreamMockProvider(_MockProvider):
    def __init__(
        self,
        provider_name: str,
        capabilities: frozenset[ProviderCapability] | None = None,
        available: bool = True,
    ) -> None:
        caps = capabilities if capabilities is not None else frozenset()
        super().__init__(provider_name, capabilities=caps, available=available)

    def generate_stream(self, prompt: str) -> Generator[AIStreamChunk, None, None]:
        yield AIStreamChunk(content="chunk")


def _make_router(
    providers: dict[str, _MockProvider],
    config: RoutingConfig | None = None,
) -> AIRouter:
    router = AIRouter(routing_config=config)
    router.providers = providers  # type: ignore[assignment]
    return router


class TestProviderCapabilityEnum:
    def test_new_capabilities_defined(self) -> None:
        assert ProviderCapability.CONVERSATION is not None
        assert ProviderCapability.SYSTEM_PROMPT is not None
        assert ProviderCapability.REASONING is not None
        assert ProviderCapability.TEXT_GENERATION is not None

    def test_existing_capabilities_preserved(self) -> None:
        assert ProviderCapability.STREAMING is not None
        assert ProviderCapability.FUNCTION_CALLING is not None
        assert ProviderCapability.EMBEDDINGS is not None
        assert ProviderCapability.IMAGE_INPUT is not None
        assert ProviderCapability.JSON_OUTPUT is not None

    def test_capabilities_are_int_flags(self) -> None:
        combined = ProviderCapability.STREAMING | ProviderCapability.JSON_OUTPUT
        assert isinstance(combined, int)
        assert combined & ProviderCapability.STREAMING
        assert combined & ProviderCapability.JSON_OUTPUT
        assert not combined & ProviderCapability.IMAGE_INPUT


class TestCapabilityDeclaration:
    def test_all_providers_have_text_generation(self) -> None:
        router = AIRouter()
        for name in router.providers:
            caps = router.provider_capabilities(name)
            assert ProviderCapability.TEXT_GENERATION in caps, (
                f"{name} missing TEXT_GENERATION"
            )

    def test_all_providers_have_conversation(self) -> None:
        router = AIRouter()
        for name in router.providers:
            caps = router.provider_capabilities(name)
            assert ProviderCapability.CONVERSATION in caps, (
                f"{name} missing CONVERSATION"
            )

    def test_openai_has_all_major_capabilities(self) -> None:
        router = AIRouter()
        caps = router.provider_capabilities("openai")
        major = {
            ProviderCapability.TEXT_GENERATION,
            ProviderCapability.STREAMING,
            ProviderCapability.CONVERSATION,
            ProviderCapability.SYSTEM_PROMPT,
            ProviderCapability.FUNCTION_CALLING,
            ProviderCapability.JSON_OUTPUT,
            ProviderCapability.IMAGE_INPUT,
        }
        assert caps.issuperset(major)

    def test_ollama_limited_capabilities(self) -> None:
        router = AIRouter()
        caps = router.provider_capabilities("ollama")
        assert ProviderCapability.CONVERSATION in caps
        assert ProviderCapability.SYSTEM_PROMPT in caps
        assert ProviderCapability.FUNCTION_CALLING not in caps


class TestCapabilityQueries:
    def test_provider_capabilities_returns_frozenset(self) -> None:
        router = AIRouter()
        caps = router.provider_capabilities("openai")
        assert isinstance(caps, frozenset)

    def test_provider_capabilities_unknown_provider(self) -> None:
        router = AIRouter()
        caps = router.provider_capabilities("nonexistent")
        assert caps == frozenset()

    def test_supports_capability_true(self) -> None:
        router = AIRouter()
        assert router.supports_capability("openai", ProviderCapability.STREAMING)

    def test_supports_capability_false(self) -> None:
        router = AIRouter()
        assert not router.supports_capability("ollama", ProviderCapability.IMAGE_INPUT)

    def test_supports_capability_none_returns_true(self) -> None:
        p = _MockProvider("test", capabilities=frozenset())
        router = _make_router({"test": p})
        assert router.supports_capability("test", None)

    def test_supports_all_true(self) -> None:
        p = _MockProvider(
            "test",
            capabilities=frozenset({ProviderCapability.STREAMING, ProviderCapability.JSON_OUTPUT}),
        )
        router = _make_router({"test": p})
        assert router.supports_all(
            "test",
            frozenset({ProviderCapability.STREAMING, ProviderCapability.JSON_OUTPUT}),
        )

    def test_supports_all_false(self) -> None:
        p = _MockProvider(
            "test",
            capabilities=frozenset({ProviderCapability.STREAMING}),
        )
        router = _make_router({"test": p})
        assert not router.supports_all(
            "test",
            frozenset({ProviderCapability.STREAMING, ProviderCapability.JSON_OUTPUT}),
        )

    def test_supports_all_none_or_empty_returns_true(self) -> None:
        p = _MockProvider("test", capabilities=frozenset())
        router = _make_router({"test": p})
        assert router.supports_all("test", None)
        assert router.supports_all("test", frozenset())

    def test_providers_with_capability(self) -> None:
        a = _MockProvider("a", capabilities=frozenset({ProviderCapability.STREAMING}))
        b = _MockProvider("b", capabilities=frozenset({ProviderCapability.STREAMING, ProviderCapability.IMAGE_INPUT}))
        c = _MockProvider("c", capabilities=frozenset({ProviderCapability.IMAGE_INPUT}))
        router = _make_router({"a": a, "b": b, "c": c})

        stream_supporters = router.providers_with_capability(ProviderCapability.STREAMING)
        assert sorted(stream_supporters) == ["a", "b"]

        vision_supporters = router.providers_with_capability(ProviderCapability.IMAGE_INPUT)
        assert sorted(vision_supporters) == ["b", "c"]

    def test_providers_with_capability_empty_when_none(self) -> None:
        p = _MockProvider("a", capabilities=frozenset())
        router = _make_router({"a": p})
        assert router.providers_with_capability(ProviderCapability.STREAMING) == []


class TestRoutingByCapability:
    def test_ask_routed_with_capability_selects_compatible(self) -> None:
        a = _MockProvider("a", capabilities=frozenset({ProviderCapability.TEXT_GENERATION}), generate_result="from a")
        b = _MockProvider("b", capabilities=frozenset({ProviderCapability.TEXT_GENERATION, ProviderCapability.JSON_OUTPUT}), generate_result="from b")
        router = _make_router({"a": a, "b": b}, RoutingConfig(providers=("a", "b")))

        result = router.ask_routed("hi", required_capabilities=frozenset({ProviderCapability.JSON_OUTPUT}))
        assert str(result) == "from b"

    def test_ask_routed_skips_providers_without_capability(self) -> None:
        a = _MockProvider("a", capabilities=frozenset({ProviderCapability.TEXT_GENERATION}))
        b = _MockProvider("b", capabilities=frozenset({ProviderCapability.TEXT_GENERATION, ProviderCapability.STREAMING}), generate_result="stream ok")
        router = _make_router({"a": a, "b": b}, RoutingConfig(providers=("a", "b")))

        result = router.ask_routed("hi", required_capabilities=frozenset({ProviderCapability.STREAMING}))
        assert str(result) == "stream ok"

    def test_ask_routed_no_compatible_provider_raises(self) -> None:
        a = _MockProvider("a", capabilities=frozenset({ProviderCapability.TEXT_GENERATION}))
        b = _MockProvider("b", capabilities=frozenset({ProviderCapability.TEXT_GENERATION}))
        router = _make_router({"a": a, "b": b}, RoutingConfig(providers=("a", "b")))

        with pytest.raises(AllProvidersFailedError) as exc:
            router.ask_routed("hi", required_capabilities=frozenset({ProviderCapability.IMAGE_INPUT}))
        assert "a" in exc.value.failures
        assert "b" in exc.value.failures

    def test_ask_routed_multiple_capabilities(self) -> None:
        a = _MockProvider("a", capabilities=frozenset({ProviderCapability.TEXT_GENERATION, ProviderCapability.STREAMING}))
        b = _MockProvider("b", capabilities=frozenset({ProviderCapability.TEXT_GENERATION, ProviderCapability.STREAMING, ProviderCapability.IMAGE_INPUT, ProviderCapability.JSON_OUTPUT}), generate_result="multi ok")
        router = _make_router({"a": a, "b": b}, RoutingConfig(providers=("a", "b")))

        result = router.ask_routed(
            "hi",
            required_capabilities=frozenset({ProviderCapability.STREAMING, ProviderCapability.IMAGE_INPUT, ProviderCapability.JSON_OUTPUT}),
        )
        assert str(result) == "multi ok"

    def test_ask_routed_no_capability_requirement_uses_first_available(self) -> None:
        a = _MockProvider("a", capabilities=frozenset({ProviderCapability.TEXT_GENERATION}), generate_result="from a")
        b = _MockProvider("b", capabilities=frozenset({ProviderCapability.TEXT_GENERATION, ProviderCapability.STREAMING}), generate_result="from b")
        router = _make_router({"a": a, "b": b}, RoutingConfig(providers=("a", "b")))

        result = router.ask_routed("hi")
        assert str(result) == "from a"

    def test_ask_routed_stream_with_capability(self) -> None:
        a = _MockProvider("a", capabilities=frozenset({ProviderCapability.TEXT_GENERATION, ProviderCapability.STREAMING}))
        b = _StreamMockProvider("b", capabilities=frozenset({ProviderCapability.TEXT_GENERATION, ProviderCapability.STREAMING}))
        router = _make_router({"a": a, "b": b}, RoutingConfig(providers=("a", "b")))

        stream = router.ask_routed_stream("hi", required_capabilities=frozenset({ProviderCapability.STREAMING}))
        chunks = list(stream)
        assert len(chunks) > 0

    def test_ask_routed_stream_no_compatible_fails(self) -> None:
        a = _MockProvider("a", capabilities=frozenset({ProviderCapability.TEXT_GENERATION}))
        router = _make_router({"a": a}, RoutingConfig(providers=("a",)))

        with pytest.raises(AllProvidersFailedError):
            router.ask_routed_stream("hi", required_capabilities=frozenset({ProviderCapability.STREAMING}))

    def test_capability_skips_unavailable_providers_then_checks_capability(self) -> None:
        a = _MockProvider("a", capabilities=frozenset({ProviderCapability.JSON_OUTPUT}), available=False)
        b = _MockProvider("b", capabilities=frozenset({ProviderCapability.TEXT_GENERATION}))
        c = _MockProvider("c", capabilities=frozenset({ProviderCapability.TEXT_GENERATION, ProviderCapability.JSON_OUTPUT}), generate_result="from c")
        router = _make_router({"a": a, "b": b, "c": c}, RoutingConfig(providers=("a", "b", "c")))

        result = router.ask_routed("hi", required_capabilities=frozenset({ProviderCapability.JSON_OUTPUT}))
        assert str(result) == "from c"


class TestAIManagerCapabilityValidation:
    def test_ask_passes_without_capability_requirement(self) -> None:
        manager = AIManager()
        result = manager.ask("ollama", "hello")
        assert isinstance(result, AIResponse)

    def test_ask_with_supported_capability_validates_without_error(self) -> None:
        manager = AIManager()
        manager.router.providers["ollama"] = _MockProvider(
            "ollama",
            capabilities=frozenset({ProviderCapability.TEXT_GENERATION}),
            generate_result="validated",
        )
        result = manager.ask("ollama", "hello", required_capabilities=frozenset({ProviderCapability.TEXT_GENERATION}))
        assert str(result) == "validated"

    def test_ask_with_unsupported_capability_raises(self) -> None:
        manager = AIManager()
        with pytest.raises(AIProviderError, match="does not support"):
            manager.ask("ollama", "hello", required_capabilities=frozenset({ProviderCapability.IMAGE_INPUT}))

    def test_ask_with_unsupported_capability_raises(self) -> None:
        manager = AIManager()
        with pytest.raises(AIProviderError, match="does not support"):
            manager.ask("ollama", "hello", required_capabilities=frozenset({ProviderCapability.IMAGE_INPUT}))

    def test_ask_with_multiple_unsupported_capabilities(self) -> None:
        manager = AIManager()
        required = frozenset({ProviderCapability.IMAGE_INPUT, ProviderCapability.FUNCTION_CALLING})
        with pytest.raises(AIProviderError, match="does not support") as exc:
            manager.ask("ollama", "hello", required_capabilities=required)
        msg = str(exc.value)
        assert "IMAGE_INPUT" in msg
        assert "FUNCTION_CALLING" in msg

    def test_ask_stream_validates_streaming_capability(self) -> None:
        manager = AIManager()
        manager.router.providers["nostream"] = _MockProvider(
            "nostream",
            capabilities=frozenset({ProviderCapability.TEXT_GENERATION}),
        )
        with pytest.raises(AIProviderError, match="does not support"):
            manager.ask_stream("nostream", "hello")


class TestCapabilityMetadata:
    def test_routed_response_includes_capability_metadata(self) -> None:
        a = _MockProvider(
            "a",
            capabilities=frozenset({ProviderCapability.TEXT_GENERATION, ProviderCapability.STREAMING}),
            generate_result="with metadata",
        )
        router = _make_router({"a": a}, RoutingConfig(providers=("a",)))

        result = router.ask_routed("hi", required_capabilities=frozenset({ProviderCapability.STREAMING}))
        assert result.metadata.get("capabilities") is not None
        assert result.metadata.get("routing_strategy") is not None

    def test_routed_metadata_includes_fallback_history(self) -> None:
        a = _MockProvider(
            "a",
            capabilities=frozenset({ProviderCapability.TEXT_GENERATION}),
        )
        b = _MockProvider(
            "b",
            capabilities=frozenset({ProviderCapability.TEXT_GENERATION, ProviderCapability.STREAMING}),
            generate_result="fallback ok",
        )
        router = _make_router({"a": a, "b": b}, RoutingConfig(providers=("a", "b")))

        result = router.ask_routed("hi", required_capabilities=frozenset({ProviderCapability.STREAMING}))
        assert "a" in result.metadata.get("fallback_history", [])


class TestFutureCompatibility:
    def test_new_provider_without_capabilities_returns_empty(self) -> None:
        class NewProvider(AIProvider):
            provider_name = "future_provider"
            def generate(self, prompt: str) -> str:
                return "future"

        router = AIRouter()
        router.providers["future_provider"] = NewProvider()
        caps = router.provider_capabilities("future_provider")
        assert caps == frozenset()

    def test_capability_check_without_router_uses_fallback(self) -> None:
        class NoCapProvider(AIProvider):
            provider_name = "nocap"
            def generate(self, prompt: str) -> str:
                return "nocap"

        router = AIRouter()
        router.providers["nocap"] = NoCapProvider()
        assert router.supports_capability("nocap", ProviderCapability.STREAMING) is False

    def test_capability_checks_work_with_overridden_capabilities(self) -> None:
        class CustomProvider(AIProvider):
            provider_name = "custom"
            capabilities = frozenset({ProviderCapability.IMAGE_INPUT, ProviderCapability.REASONING})
            def generate(self, prompt: str) -> str:
                return "custom"

        router = AIRouter()
        router.providers["custom"] = CustomProvider()
        assert router.supports_capability("custom", ProviderCapability.IMAGE_INPUT)
        assert router.supports_capability("custom", ProviderCapability.REASONING)
        assert not router.supports_capability("custom", ProviderCapability.STREAMING)
