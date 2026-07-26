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
from app.ai.routing import RoutingConfig, RoutingStrategy
from app.ai.tools import (
    DuplicateToolError,
    ToolCall,
    ToolDefinition,
    ToolError,
    ToolNotFoundError,
    ToolRegistry,
    ToolResult,
    ToolValidationError,
    validate_tool_call_arguments,
    validate_tool_definition,
)


# ---------------------------------------------------------------------------
# Valid tool definition fixtures
# ---------------------------------------------------------------------------


def _make_valid_tool(
    name: str = "get_weather",
    desc: str = "Get the current weather",
    **overrides,
) -> ToolDefinition:
    params = overrides.pop("parameters", {
        "type": "object",
        "properties": {
            "location": {"type": "string", "description": "City name"},
            "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]},
        },
        "required": ["location"],
    })
    return ToolDefinition(name=name, description=desc, parameters=params, **overrides)


# ---------------------------------------------------------------------------
# ToolDefinition model & validation
# ---------------------------------------------------------------------------


class TestToolDefinition:
    def test_valid_tool(self) -> None:
        tool = _make_valid_tool()
        validate_tool_definition(tool)

    def test_empty_name_raises(self) -> None:
        with pytest.raises(ToolValidationError, match="non-empty"):
            validate_tool_definition(ToolDefinition(name="", description="desc", parameters={"type": "object", "properties": {}}))

    def test_empty_description_raises(self) -> None:
        with pytest.raises(ToolValidationError, match="non-empty"):
            validate_tool_definition(ToolDefinition(name="t", description="", parameters={"type": "object", "properties": {}}))

    def test_non_dict_parameters_raises(self) -> None:
        with pytest.raises(ToolValidationError, match="must be a dict"):
            validate_tool_definition(ToolDefinition(name="t", description="desc", parameters="bad"))

    def test_missing_type_in_schema_raises(self) -> None:
        with pytest.raises(ToolValidationError, match="must specify 'type'"):
            validate_tool_definition(ToolDefinition(name="t", description="desc", parameters={"properties": {}}))

    def test_missing_properties_raises(self) -> None:
        with pytest.raises(ToolValidationError, match="must specify 'properties'"):
            validate_tool_definition(ToolDefinition(name="t", description="desc", parameters={"type": "object"}))

    def test_tool_metadata_must_be_dict(self) -> None:
        with pytest.raises(ToolValidationError, match="metadata"):
            validate_tool_definition(ToolDefinition(name="t", description="desc", parameters={"type": "object", "properties": {}}, metadata="bad"))

    def test_tool_metadata_none_is_ok(self) -> None:
        validate_tool_definition(ToolDefinition(name="t", description="desc", parameters={"type": "object", "properties": {}}, metadata=None))


# ---------------------------------------------------------------------------
# Tool argument validation
# ---------------------------------------------------------------------------


class TestToolArgumentValidation:
    def test_valid_arguments(self) -> None:
        tool = _make_valid_tool()
        errors = validate_tool_call_arguments(tool, {"location": "London", "unit": "celsius"})
        assert errors == []

    def test_missing_required_parameter(self) -> None:
        tool = _make_valid_tool()
        errors = validate_tool_call_arguments(tool, {"unit": "celsius"})
        assert any("location" in e for e in errors)

    def test_invalid_enum_value(self) -> None:
        tool = _make_valid_tool()
        errors = validate_tool_call_arguments(tool, {"location": "London", "unit": "kelvin"})
        assert any("kelvin" in e for e in errors)


# ---------------------------------------------------------------------------
# ToolRegistry
# ---------------------------------------------------------------------------


class TestToolRegistry:
    def test_register_and_get(self) -> None:
        reg = ToolRegistry()
        tool = _make_valid_tool()
        reg.register(tool)
        assert reg.get("get_weather") == tool

    def test_register_duplicate_raises(self) -> None:
        reg = ToolRegistry()
        reg.register(_make_valid_tool())
        with pytest.raises(DuplicateToolError, match="already registered"):
            reg.register(_make_valid_tool())

    def test_register_duplicate_different_tool_raises(self) -> None:
        reg = ToolRegistry()
        reg.register(_make_valid_tool(name="get_weather"))
        with pytest.raises(DuplicateToolError):
            reg.register(_make_valid_tool(name="get_weather", desc="different desc"))

    def test_unregister_existing(self) -> None:
        reg = ToolRegistry()
        reg.register(_make_valid_tool())
        assert reg.unregister("get_weather") is True
        assert reg.get("get_weather") is None

    def test_unregister_missing(self) -> None:
        reg = ToolRegistry()
        assert reg.unregister("nonexistent") is False

    def test_has_existing(self) -> None:
        reg = ToolRegistry()
        reg.register(_make_valid_tool())
        assert reg.has("get_weather") is True

    def test_has_missing(self) -> None:
        reg = ToolRegistry()
        assert reg.has("nonexistent") is False

    def test_list_empty(self) -> None:
        reg = ToolRegistry()
        assert reg.list() == []

    def test_list_returns_all(self) -> None:
        reg = ToolRegistry()
        a = _make_valid_tool(name="a")
        b = _make_valid_tool(name="b")
        reg.register(a)
        reg.register(b)
        assert reg.list() == [a, b]

    def test_count(self) -> None:
        reg = ToolRegistry()
        assert reg.count == 0
        reg.register(_make_valid_tool())
        assert reg.count == 1

    def test_invalid_tool_on_register(self) -> None:
        reg = ToolRegistry()
        with pytest.raises(ToolValidationError):
            reg.register(ToolDefinition(name="", description="desc", parameters={"type": "object", "properties": {}}))

    def test_registered_tool_preserves_metadata(self) -> None:
        reg = ToolRegistry()
        tool = _make_valid_tool(metadata={"source": "test"})
        reg.register(tool)
        assert reg.get("get_weather").metadata == {"source": "test"}


# ---------------------------------------------------------------------------
# ToolCall & ToolResult models
# ---------------------------------------------------------------------------


class TestToolCallAndResult:
    def test_tool_call_creation(self) -> None:
        tc = ToolCall(id="call_1", name="get_weather", arguments={"location": "London"})
        assert tc.id == "call_1"
        assert tc.name == "get_weather"
        assert tc.arguments == {"location": "London"}

    def test_tool_result_success(self) -> None:
        tr = ToolResult(id="call_1", name="get_weather", content='{"temp": 22}')
        assert tr.error is None
        assert tr.content == '{"temp": 22}'

    def test_tool_result_error(self) -> None:
        tr = ToolResult(id="call_1", name="get_weather", content="", error="API unavailable")
        assert tr.error == "API unavailable"


# ---------------------------------------------------------------------------
# Mock provider for tool calling tests
# ---------------------------------------------------------------------------


class _ToolMockProvider(AIProvider):
    """Mock provider that declares FUNCTION_CALLING capability."""

    def __init__(
        self,
        provider_name: str,
        capabilities: frozenset | None = None,
        available: bool = True,
        generate_result: str | None = None,
    ):
        self.provider_name = provider_name
        self.capabilities = capabilities or frozenset({
            ProviderCapability.TEXT_GENERATION,
            ProviderCapability.FUNCTION_CALLING,
            ProviderCapability.STREAMING,
        })
        self._available = available
        self._generate_result = generate_result

    def generate(self, prompt: str, tools: list[ToolDefinition] | None = None) -> AIResponse:
        return AIResponse(
            self._generate_result or f"{self.provider_name}: {prompt}",
            provider=self.provider_name,
            model="test",
            latency_ms=0.0,
            metadata={"tool_calls": []},
        )

    def check_availability(self) -> bool:
        return self._available


class _NoToolMockProvider(AIProvider):
    """Mock provider WITHOUT FUNCTION_CALLING capability."""

    def __init__(self, provider_name: str = "notool", available: bool = True):
        self.provider_name = provider_name
        self.capabilities = frozenset({ProviderCapability.TEXT_GENERATION})
        self._available = available

    def generate(self, prompt: str, tools: list[ToolDefinition] | None = None) -> AIResponse:
        return AIResponse(f"{self.provider_name}: {prompt}", provider=self.provider_name, model="test", latency_ms=0.0)

    def check_availability(self) -> bool:
        return self._available


def _make_router(providers: dict, config: RoutingConfig | None = None) -> AIRouter:
    router = AIRouter(routing_config=config)
    router.providers = providers  # type: ignore[assignment]
    return router


# ---------------------------------------------------------------------------
# Router: tools passthrough
# ---------------------------------------------------------------------------


class TestRouterToolsPassthrough:
    def test_ask_with_tools_passed_to_provider(self) -> None:
        tool = _make_valid_tool()
        provider = _ToolMockProvider("test")
        router = _make_router({"test": provider})

        result = router.ask("test", "hello", tools=[tool])
        assert str(result).startswith("test:")

    def test_ask_without_tools_still_works(self) -> None:
        provider = _ToolMockProvider("test")
        router = _make_router({"test": provider})
        result = router.ask("test", "hello")
        assert str(result).startswith("test:")


# ---------------------------------------------------------------------------
# Routing: TOOL_CALLING capability check
# ---------------------------------------------------------------------------


class TestRoutingWithTools:
    def test_routed_skips_provider_without_tool_calling(self) -> None:
        tool = _make_valid_tool()
        a = _NoToolMockProvider("a")
        b = _ToolMockProvider("b", generate_result="from b")
        router = _make_router({"a": a, "b": b}, RoutingConfig(providers=("a", "b")))

        result = router.ask_routed("hi", tools=[tool])
        assert str(result) == "from b"

    def test_routed_all_providers_lack_tool_calling_raises(self) -> None:
        tool = _make_valid_tool()
        a = _NoToolMockProvider("a")
        b = _NoToolMockProvider("b")
        router = _make_router({"a": a, "b": b}, RoutingConfig(providers=("a", "b")))

        with pytest.raises(AllProvidersFailedError):
            router.ask_routed("hi", tools=[tool])

    def test_routed_without_tools_uses_first_available(self) -> None:
        a = _NoToolMockProvider("a")
        b = _ToolMockProvider("b", generate_result="from b")
        router = _make_router({"a": a, "b": b}, RoutingConfig(providers=("a", "b")))

        result = router.ask_routed("hi")
        assert str(result) == "a: hi"

    def test_routed_capability_and_tools_combined(self) -> None:
        tool = _make_valid_tool()
        a = _ToolMockProvider("a", capabilities=frozenset({
            ProviderCapability.TEXT_GENERATION, ProviderCapability.FUNCTION_CALLING,
        }), generate_result="from a")
        b = _ToolMockProvider("b", capabilities=frozenset({
            ProviderCapability.TEXT_GENERATION, ProviderCapability.FUNCTION_CALLING,
            ProviderCapability.JSON_OUTPUT,
        }), generate_result="from b")
        router = _make_router({"a": a, "b": b}, RoutingConfig(providers=("a", "b")))

        result = router.ask_routed(
            "hi",
            required_capabilities=frozenset({ProviderCapability.JSON_OUTPUT}),
            tools=[tool],
        )
        assert str(result) == "from b"


# ---------------------------------------------------------------------------
# AIManager: tools integration
# ---------------------------------------------------------------------------


class TestAIManagerTools:
    def test_ask_with_tools(self) -> None:
        tool = _make_valid_tool()
        manager = AIManager()
        manager.router.providers["tool_provider"] = _ToolMockProvider("tool_provider")
        result = manager.ask("tool_provider", "hello", tools=[tool])
        assert isinstance(result, AIResponse)

    def test_ask_with_tools_requires_function_calling(self) -> None:
        tool = _make_valid_tool()
        manager = AIManager()
        manager.router.providers["notool"] = _NoToolMockProvider("notool")
        with pytest.raises(AIProviderError, match="FUNCTION_CALLING"):
            manager.ask("notool", "hello", tools=[tool])

    def test_ask_with_tools_and_required_capabilities_merged(self) -> None:
        tool = _make_valid_tool()
        manager = AIManager()
        manager.router.providers["tool_provider"] = _ToolMockProvider("tool_provider")
        result = manager.ask(
            "tool_provider",
            "hello",
            required_capabilities=frozenset({ProviderCapability.TEXT_GENERATION}),
            tools=[tool],
        )
        assert isinstance(result, AIResponse)

    def test_ask_stream_rejects_tools_on_no_stream(self) -> None:
        tool = _make_valid_tool()
        manager = AIManager()
        manager.router.providers["nostream"] = _ToolMockProvider(
            "nostream", capabilities=frozenset({ProviderCapability.TEXT_GENERATION}),
        )
        with pytest.raises(AIProviderError, match="STREAMING"):
            manager.ask_stream("nostream", "hello")


# ---------------------------------------------------------------------------
# Provider format_tools / parse_tool_calls
# ---------------------------------------------------------------------------


class TestProviderToolTranslation:
    def test_openai_format_tools(self) -> None:
        from app.ai.providers.openai import OpenAIProvider
        provider = OpenAIProvider(api_key="test", model="gpt-4o-mini")
        tool = _make_valid_tool()
        result = provider.format_tools([tool])
        assert len(result) == 1
        assert result[0]["type"] == "function"
        assert result[0]["function"]["name"] == "get_weather"

    def test_deepseek_format_tools(self) -> None:
        from app.ai.providers.deepseek import DeepSeekProvider
        provider = DeepSeekProvider(api_key="test", model="deepseek-chat")
        tool = _make_valid_tool()
        result = provider.format_tools([tool])
        assert len(result) == 1
        assert result[0]["type"] == "function"
        assert result[0]["function"]["name"] == "get_weather"

    def test_claude_format_tools(self) -> None:
        from app.ai.providers.claude import AnthropicProvider
        provider = AnthropicProvider(api_key="test", model="claude-3-5-sonnet-20241022")
        tool = _make_valid_tool()
        result = provider.format_tools([tool])
        assert len(result) == 1
        assert result[0]["name"] == "get_weather"
        assert "input_schema" in result[0]

    def test_gemini_format_tools(self) -> None:
        from app.ai.providers.gemini import GeminiProvider
        provider = GeminiProvider(api_key="test", model="gemini-2.0-flash")
        tool = _make_valid_tool()
        result = provider.format_tools([tool])
        assert len(result) == 1
        assert "function_declarations" in result[0]

    def test_ollama_lacks_format_tools(self) -> None:
        from app.ai.providers.ollama import OllamaProvider
        provider = OllamaProvider()
        assert not hasattr(provider, "format_tools")

    def test_parse_tool_calls_empty_when_no_tools(self) -> None:
        from app.ai.providers.openai import OpenAIProvider
        provider = OpenAIProvider(api_key="test", model="gpt-4o-mini")
        assert provider.parse_tool_calls(None) == []


# ---------------------------------------------------------------------------
# Future provider compatibility
# ---------------------------------------------------------------------------


class TestFutureCompatibility:
    def test_new_provider_can_declare_tool_capabilities(self) -> None:
        class FutureProvider(AIProvider):
            provider_name = "future"
            capabilities = frozenset({
                ProviderCapability.TEXT_GENERATION,
                ProviderCapability.FUNCTION_CALLING,
            })
            def generate(self, prompt: str, tools: list[ToolDefinition] | None = None) -> str:
                return "future result"

        router = AIRouter()
        router.providers["future"] = FutureProvider()
        assert router.supports_capability("future", ProviderCapability.FUNCTION_CALLING)

    def test_new_provider_format_tools_optional(self) -> None:
        class FutureProvider(AIProvider):
            provider_name = "future"
            capabilities = frozenset({ProviderCapability.TEXT_GENERATION})
            def generate(self, prompt: str, tools: list[ToolDefinition] | None = None) -> str:
                return "future result"

        router = AIRouter()
        router.providers["future"] = FutureProvider()
        # Should work without format_tools
        result = router.ask("future", "hello", tools=None)
        assert str(result) == "future result"


# ---------------------------------------------------------------------------
# Metadata in AIResponse
# ---------------------------------------------------------------------------


class TestToolMetadata:
    def test_provider_declares_tool_capability(self) -> None:
        from app.ai.providers.openai import OpenAIProvider
        assert ProviderCapability.FUNCTION_CALLING in OpenAIProvider.capabilities

    def test_tool_provider_metadata_includes_provider_name(self) -> None:
        p = _ToolMockProvider("test")
        result = p.generate("hello")
        assert result.provider == "test"
