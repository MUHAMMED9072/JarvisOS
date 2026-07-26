from __future__ import annotations

import json

import pytest

from app.ai.providers.base import (
    AIProvider,
    AIProviderError,
    AIResponse,
    ProviderCapability,
)
from app.ai.manager import AIManager
from app.ai.router import AIRouter
from app.ai.routing import RoutingConfig, RoutingStrategy
from app.ai.structured import (
    OutputParseError,
    OutputValidationError,
    SchemaValidationError,
    StructuredResult,
    StructuredSchema,
    parse_structured_output,
    validate_structured_schema,
)
from app.ai.tools import ToolDefinition


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_schema(
    name: str = "test_schema",
    **overrides,
) -> StructuredSchema:
    schema_dict = overrides.pop("schema", {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "age": {"type": "integer"},
            "active": {"type": "boolean"},
        },
        "required": ["name", "age"],
    })
    return StructuredSchema(name=name, schema=schema_dict, **overrides)


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------


class TestSchemaValidation:
    def test_valid_schema(self) -> None:
        validate_structured_schema(_make_schema())

    def test_empty_name_raises(self) -> None:
        with pytest.raises(SchemaValidationError, match="non-empty"):
            validate_structured_schema(StructuredSchema(name="", schema={"type": "object", "properties": {}}))

    def test_non_dict_schema_raises(self) -> None:
        with pytest.raises(SchemaValidationError, match="must be a dict"):
            validate_structured_schema(StructuredSchema(name="s", schema="bad"))

    def test_missing_type_raises(self) -> None:
        with pytest.raises(SchemaValidationError, match="must specify 'type'"):
            validate_structured_schema(StructuredSchema(name="s", schema={"properties": {}}))

    def test_invalid_type_raises(self) -> None:
        with pytest.raises(SchemaValidationError):
            validate_structured_schema(StructuredSchema(name="s", schema={"type": "invalid", "properties": {}}))

    def test_metadata_must_be_dict(self) -> None:
        with pytest.raises(SchemaValidationError, match="metadata"):
            validate_structured_schema(StructuredSchema(name="s", schema={"type": "object", "properties": {}}, metadata="bad"))

    def test_metadata_none_allowed(self) -> None:
        validate_structured_schema(StructuredSchema(name="s", schema={"type": "object", "properties": {}}, metadata=None))


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


class TestParsing:
    def test_parse_valid_json(self) -> None:
        schema = _make_schema()
        result = parse_structured_output('{"name": "Alice", "age": 30}', schema)
        assert result.valid is True
        assert result.data["name"] == "Alice"
        assert result.data["age"] == 30

    def test_parse_invalid_json(self) -> None:
        schema = _make_schema()
        result = parse_structured_output("{bad json}", schema)
        assert result.valid is False
        assert any("Invalid JSON" in e for e in result.errors)

    def test_parse_missing_required_field(self) -> None:
        schema = _make_schema()
        result = parse_structured_output('{"name": "Alice"}', schema)
        assert result.valid is False
        assert any("age" in e and "missing" in e for e in result.errors)

    def test_parse_wrong_type(self) -> None:
        schema = _make_schema()
        result = parse_structured_output('{"name": "Alice", "age": "thirty"}', schema)
        assert result.valid is False
        assert any("integer" in e for e in result.errors)


# ---------------------------------------------------------------------------
# Nested object validation
# ---------------------------------------------------------------------------


class TestNestedValidation:
    def test_valid_nested_object(self) -> None:
        schema = StructuredSchema(name="nested", schema={
            "type": "object",
            "properties": {
                "user": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "scores": {
                            "type": "array",
                            "items": {"type": "integer"},
                        },
                    },
                    "required": ["name"],
                },
            },
            "required": ["user"],
        })
        result = parse_structured_output(
            '{"user": {"name": "Bob", "scores": [95, 87]}}',
            schema,
        )
        assert result.valid is True
        assert result.data["user"]["name"] == "Bob"

    def test_invalid_nested_field(self) -> None:
        schema = StructuredSchema(name="nested", schema={
            "type": "object",
            "properties": {
                "user": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                    },
                    "required": ["name"],
                },
            },
            "required": ["user"],
        })
        result = parse_structured_output('{"user": {"name": 123}}', schema)
        assert result.valid is False
        assert any("string" in e for e in result.errors)

    def test_missing_nested_required(self) -> None:
        schema = StructuredSchema(name="nested", schema={
            "type": "object",
            "properties": {
                "user": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                    },
                    "required": ["name"],
                },
            },
            "required": ["user"],
        })
        result = parse_structured_output('{"user": {}}', schema)
        assert result.valid is False
        assert any("name" in e and "missing" in e for e in result.errors)

    def test_invalid_array_item(self) -> None:
        schema = StructuredSchema(name="arr", schema={
            "type": "object",
            "properties": {
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
            "required": [],
        })
        result = parse_structured_output('{"tags": [1, 2, 3]}', schema)
        assert result.valid is False
        assert any("string" in e for e in result.errors)


# ---------------------------------------------------------------------------
# Enum validation
# ---------------------------------------------------------------------------


class TestEnumValidation:
    def test_valid_enum(self) -> None:
        schema = StructuredSchema(name="enum", schema={
            "type": "object",
            "properties": {
                "role": {"type": "string", "enum": ["admin", "user"]},
            },
            "required": ["role"],
        })
        result = parse_structured_output('{"role": "admin"}', schema)
        assert result.valid is True

    def test_invalid_enum_value(self) -> None:
        schema = StructuredSchema(name="enum", schema={
            "type": "object",
            "properties": {
                "role": {"type": "string", "enum": ["admin", "user"]},
            },
            "required": ["role"],
        })
        result = parse_structured_output('{"role": "superadmin"}', schema)
        assert result.valid is False
        assert any("must be one of" in e for e in result.errors)


# ---------------------------------------------------------------------------
# Provider format_structured_schema
# ---------------------------------------------------------------------------


class TestProviderSchemaTranslation:
    def test_openai_format_schema(self) -> None:
        from app.ai.providers.openai import OpenAIProvider
        provider = OpenAIProvider(api_key="test", model="gpt-4o-mini")
        schema = _make_schema()
        result = provider.format_structured_schema(schema)
        assert result is not None
        assert result["response_format"]["type"] == "json_schema"
        assert result["response_format"]["json_schema"]["name"] == "test_schema"

    def test_gemini_format_schema(self) -> None:
        from app.ai.providers.gemini import GeminiProvider
        provider = GeminiProvider(api_key="test", model="gemini-2.0-flash")
        schema = _make_schema()
        result = provider.format_structured_schema(schema)
        assert result is not None
        assert "generation_config" in result

    def test_deepseek_format_schema(self) -> None:
        from app.ai.providers.deepseek import DeepSeekProvider
        provider = DeepSeekProvider(api_key="test", model="deepseek-chat")
        schema = _make_schema()
        result = provider.format_structured_schema(schema)
        assert result is not None
        assert result["response_format"]["type"] == "json_object"

    def test_claude_returns_none(self) -> None:
        from app.ai.providers.claude import AnthropicProvider
        provider = AnthropicProvider(api_key="test", model="claude-3-5-sonnet-20241022")
        schema = _make_schema()
        result = provider.format_structured_schema(schema)
        assert result is None

    def test_base_returns_none(self) -> None:
        from app.ai.providers.base import _ProviderBase
        result = _ProviderBase().format_structured_schema(_make_schema())
        assert result is None


# ---------------------------------------------------------------------------
# Mock provider for structured output tests
# ---------------------------------------------------------------------------


class _MockStructuredProvider(AIProvider):
    def __init__(
        self,
        provider_name: str = "structured",
        capabilities: frozenset | None = None,
        available: bool = True,
        generate_result: str | None = None,
    ):
        self.provider_name = provider_name
        self.capabilities = capabilities or frozenset({
            ProviderCapability.TEXT_GENERATION,
            ProviderCapability.JSON_OUTPUT,
        })
        self._available = available
        self._generate_result = generate_result

    def generate(self, prompt: str, **kwargs) -> AIResponse:
        return AIResponse(
            self._generate_result or f"{self.provider_name}: {prompt}",
            provider=self.provider_name,
            model="test",
            latency_ms=0.0,
        )

    def check_availability(self) -> bool:
        return self._available


class _NoJSONMockProvider(AIProvider):
    def __init__(self, provider_name: str = "nojson"):
        self.provider_name = provider_name
        self.capabilities = frozenset({ProviderCapability.TEXT_GENERATION})

    def generate(self, prompt: str, **kwargs) -> AIResponse:
        return AIResponse(f"{self.provider_name}: {prompt}", provider=self.provider_name, model="test", latency_ms=0.0)


# ---------------------------------------------------------------------------
# Router integration
# ---------------------------------------------------------------------------


class TestRouterStructuredOutput:
    def test_ask_with_schema(self) -> None:
        provider = _MockStructuredProvider("test")
        router = AIRouter()
        router.providers = {"test": provider}
        schema = _make_schema()
        result = router.ask("test", "hello", schema=schema)
        assert isinstance(result, AIResponse)

    def test_routed_skips_without_json_capability(self) -> None:
        a = _NoJSONMockProvider("a")
        b = _MockStructuredProvider("b", generate_result="from b")
        config = RoutingConfig(providers=("a", "b"))
        router = AIRouter(routing_config=config)
        router.providers = {"a": a, "b": b}
        schema = _make_schema()

        result = router.ask_routed("hi", schema=schema)
        assert str(result) == "from b"

    def test_routed_no_json_provider_fails(self) -> None:
        a = _NoJSONMockProvider("a")
        b = _NoJSONMockProvider("b")
        config = RoutingConfig(providers=("a", "b"))
        router = AIRouter(routing_config=config)
        router.providers = {"a": a, "b": b}
        schema = _make_schema()

        with pytest.raises(Exception):
            router.ask_routed("hi", schema=schema)


# ---------------------------------------------------------------------------
# AIManager integration
# ---------------------------------------------------------------------------


class TestAIManagerStructured:
    def test_ask_with_schema(self) -> None:
        manager = AIManager()
        manager.router.providers["test"] = _MockStructuredProvider("test")
        schema = _make_schema()
        result = manager.ask("test", "hello", schema=schema)
        assert isinstance(result, AIResponse)

    def test_ask_with_schema_no_json_capability_raises(self) -> None:
        manager = AIManager()
        manager.router.providers["nojson"] = _NoJSONMockProvider("nojson")
        schema = _make_schema()
        with pytest.raises(AIProviderError, match="JSON_OUTPUT"):
            manager.ask("nojson", "hello", schema=schema)

    def test_ask_with_schema_and_tools(self) -> None:
        manager = AIManager()
        manager.router.providers["test"] = _MockStructuredProvider(
            "test",
            capabilities=frozenset({
                ProviderCapability.TEXT_GENERATION,
                ProviderCapability.JSON_OUTPUT,
                ProviderCapability.FUNCTION_CALLING,
            }),
        )
        schema = _make_schema()
        tool = ToolDefinition(name="t", description="desc", parameters={"type": "object", "properties": {}})
        result = manager.ask("test", "hello", tools=[tool], schema=schema)
        assert isinstance(result, AIResponse)


# ---------------------------------------------------------------------------
# StructuredResult and metadata
# ---------------------------------------------------------------------------


class TestStructuredResult:
    def test_structured_result_creation(self) -> None:
        result = StructuredResult(data={"key": "val"}, schema_name="test", valid=True)
        assert result.data == {"key": "val"}
        assert result.valid is True
        assert result.errors == []

    def test_structured_result_invalid(self) -> None:
        result = StructuredResult(data={}, schema_name="test", valid=False, errors=["missing field"])
        assert result.valid is False
        assert result.errors == ["missing field"]

    def test_structured_result_raw(self) -> None:
        raw = '{"key": "val"}'
        result = StructuredResult(data={"key": "val"}, schema_name="test", valid=True, raw=raw)
        assert result.raw == raw

    def test_parse_returns_raw_text(self) -> None:
        schema = _make_schema()
        result = parse_structured_output('{"name": "Alice", "age": 30}', schema)
        assert result.raw == '{"name": "Alice", "age": 30}'


# ---------------------------------------------------------------------------
# Backward compatibility
# ---------------------------------------------------------------------------


class TestBackwardCompatibility:
    def test_generate_without_schema_still_works(self) -> None:
        provider = _MockStructuredProvider("test")
        result = provider.generate("hello")
        assert isinstance(result, AIResponse)
        assert str(result) == "test: hello"

    def test_router_ask_without_schema(self) -> None:
        provider = _MockStructuredProvider("test")
        router = AIRouter()
        router.providers = {"test": provider}
        result = router.ask("test", "hello")
        assert isinstance(result, AIResponse)

    def test_manager_ask_without_schema(self) -> None:
        manager = AIManager()
        result = manager.ask("ollama", "hello")
        assert isinstance(result, AIResponse)
