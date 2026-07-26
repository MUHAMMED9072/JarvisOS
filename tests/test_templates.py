from __future__ import annotations

import re

import pytest

from app.ai.manager import AIManager
from app.ai.providers.base import AIProvider, AIResponse, ProviderCapability
from app.ai.templates import (
    DuplicateTemplateError,
    PromptRenderResult,
    PromptTemplate,
    PromptTemplateError,
    PromptTemplateRegistry,
    PromptTemplateRenderError,
    PromptTemplateValidationError,
    PromptValidationResult,
    PromptVariable,
    render_template,
    validate_template,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_template(
    name: str = "test_template",
    template: str = "Hello {{name}}, welcome to {{place}}",
    variables: list | None = None,
    description: str = "Test template",
    metadata: dict | None = None,
) -> PromptTemplate:
    if variables is None:
        variables = [
            PromptVariable(name="name", description="User's name", required=True),
            PromptVariable(name="place", description="Location", required=True),
        ]
    return PromptTemplate(
        name=name,
        description=description,
        template=template,
        variables=variables,
        metadata=metadata,
    )


class _MockProvider(AIProvider):
    def __init__(
        self,
        provider_name: str = "mock",
        capabilities: frozenset | None = None,
    ):
        self.provider_name = provider_name
        self.capabilities = capabilities or frozenset({
            ProviderCapability.TEXT_GENERATION,
            ProviderCapability.STREAMING,
        })

    def generate(self, prompt: str, **kwargs) -> AIResponse:
        return AIResponse(
            f"{self.provider_name}: {prompt}",
            provider=self.provider_name,
            model="test",
            latency_ms=0.0,
            metadata={},
        )

    def check_availability(self) -> bool:
        return True


# ---------------------------------------------------------------------------
# PromptVariable
# ---------------------------------------------------------------------------


class TestPromptVariable:
    def test_default_required_true(self) -> None:
        v = PromptVariable(name="name")
        assert v.required is True

    def test_default_description_empty(self) -> None:
        v = PromptVariable(name="name")
        assert v.description == ""

    def test_default_metadata_none(self) -> None:
        v = PromptVariable(name="name")
        assert v.metadata is None

    def test_default_default_none(self) -> None:
        v = PromptVariable(name="name")
        assert v.default is None

    def test_optional_variable(self) -> None:
        v = PromptVariable(name="name", required=False)
        assert v.required is False

    def test_variable_with_default(self) -> None:
        v = PromptVariable(name="name", default="World")
        assert v.default == "World"

    def test_frozen_and_hashable(self) -> None:
        v = PromptVariable(name="name")
        with pytest.raises(AttributeError):
            v.name = "changed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# PromptTemplate
# ---------------------------------------------------------------------------


class TestPromptTemplate:
    def test_create_minimal(self) -> None:
        t = PromptTemplate(name="greeting", description="", template="Hello")
        assert t.name == "greeting"
        assert t.variables == []

    def test_create_with_variables(self) -> None:
        v = PromptVariable(name="name")
        t = PromptTemplate(
            name="greeting",
            description="Says hello",
            template="Hello {{name}}",
            variables=[v],
            metadata={"version": "1.0"},
        )
        assert t.metadata == {"version": "1.0"}

    def test_frozen(self) -> None:
        t = PromptTemplate(name="a", description="", template="b")
        with pytest.raises(AttributeError):
            t.name = "c"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Variable extraction
# ---------------------------------------------------------------------------


class TestVariableExtraction:
    def test_extract_single(self) -> None:
        from app.ai.templates import _VARIABLE_PATTERN
        matches = _VARIABLE_PATTERN.findall("Hello {{name}}")
        assert matches == ["name"]

    def test_extract_multiple(self) -> None:
        from app.ai.templates import _VARIABLE_PATTERN
        matches = _VARIABLE_PATTERN.findall("{{a}} and {{b}} and {{a}}")
        assert matches == ["a", "b", "a"]

    def test_extract_none(self) -> None:
        from app.ai.templates import _VARIABLE_PATTERN
        matches = _VARIABLE_PATTERN.findall("Hello world")
        assert matches == []

    def test_extract_invalid_syntax_no_match(self) -> None:
        from app.ai.templates import _VARIABLE_PATTERN
        matches = _VARIABLE_PATTERN.findall("Hello {name}")
        assert matches == []

    def test_extract_underscore_vars(self) -> None:
        from app.ai.templates import _VARIABLE_PATTERN
        matches = _VARIABLE_PATTERN.findall("{{user_name}} and {{_private}}")
        assert matches == ["user_name", "_private"]


# ---------------------------------------------------------------------------
# Template validation
# ---------------------------------------------------------------------------


class TestTemplateValidation:
    def test_valid_template(self) -> None:
        t = _make_template()
        result = validate_template(t)
        assert result.valid is True
        assert result.errors == []

    def test_empty_name(self) -> None:
        t = _make_template(name="")
        result = validate_template(t)
        assert result.valid is False
        assert any("name" in e for e in result.errors)

    def test_empty_template_body(self) -> None:
        t = _make_template(template="")
        result = validate_template(t)
        assert result.valid is False
        assert any("Template body" in e for e in result.errors)

    def test_invalid_metadata(self) -> None:
        t = _make_template(metadata="not a dict")  # type: ignore[arg-type]
        result = validate_template(t)
        assert result.valid is False
        assert any("metadata" in e for e in result.errors)

    def test_duplicate_variable_name(self) -> None:
        t = PromptTemplate(
            name="dup",
            description="",
            template="{{x}} + {{x}}",
            variables=[
                PromptVariable(name="x"),
                PromptVariable(name="x"),
            ],
        )
        result = validate_template(t)
        assert result.valid is False
        assert any("Duplicate" in e for e in result.errors)

    def test_empty_variable_name(self) -> None:
        t = PromptTemplate(
            name="t",
            description="",
            template="{{x}}",
            variables=[PromptVariable(name="")],
        )
        result = validate_template(t)
        assert result.valid is False

    def test_variable_used_but_not_declared(self) -> None:
        t = PromptTemplate(
            name="t",
            description="",
            template="{{undeclared}}",
            variables=[],
        )
        result = validate_template(t)
        assert result.valid is False
        assert any("undeclared" in e for e in result.errors)

    def test_declared_but_not_used_warning(self) -> None:
        t = PromptTemplate(
            name="t",
            description="",
            template="Hello",
            variables=[PromptVariable(name="unused", required=True)],
        )
        result = validate_template(t)
        assert result.valid is True
        assert any("unused" in w for w in result.warnings)

    def test_variable_invalid_metadata(self) -> None:
        t = PromptTemplate(
            name="t",
            description="",
            template="{{x}}",
            variables=[PromptVariable(name="x", metadata="str")],  # type: ignore[arg-type]
        )
        result = validate_template(t)
        assert result.valid is False

    def test_validation_result_dataclass(self) -> None:
        result = PromptValidationResult(valid=False, errors=["e1"], warnings=["w1"])
        assert result.valid is False
        assert result.errors == ["e1"]
        assert result.warnings == ["w1"]


# ---------------------------------------------------------------------------
# Template rendering
# ---------------------------------------------------------------------------


class TestTemplateRendering:
    def test_render_basic(self) -> None:
        t = _make_template()
        result = render_template(t, {"name": "Alice", "place": "Wonderland"})
        assert result.text == "Hello Alice, welcome to Wonderland"

    def test_render_multiple_occurrences(self) -> None:
        t = PromptTemplate(
            name="multi",
            description="",
            template="{{x}} + {{x}} = {{y}}",
            variables=[
                PromptVariable(name="x", required=True),
                PromptVariable(name="y", required=True),
            ],
        )
        result = render_template(t, {"x": "2", "y": "4"})
        assert result.text == "2 + 2 = 4"

    def test_render_with_defaults(self) -> None:
        t = PromptTemplate(
            name="with_default",
            description="",
            template="Hello {{name}}",
            variables=[PromptVariable(name="name", default="World")],
        )
        result = render_template(t, {})
        assert result.text == "Hello World"

    def test_render_partial_override_default(self) -> None:
        t = PromptTemplate(
            name="partial",
            description="",
            template="{{a}} + {{b}}",
            variables=[
                PromptVariable(name="a", default="1"),
                PromptVariable(name="b", default="2"),
            ],
        )
        result = render_template(t, {"a": "10"})
        assert result.text == "10 + 2"

    def test_render_missing_required_variable(self) -> None:
        t = _make_template()
        with pytest.raises(PromptTemplateRenderError, match="name"):
            render_template(t, {"place": "Wonderland"})

    def test_render_missing_required_variable_no_default(self) -> None:
        t = PromptTemplate(
            name="missing",
            description="",
            template="{{x}}",
            variables=[PromptVariable(name="x", required=True)],
        )
        with pytest.raises(PromptTemplateRenderError, match="x"):
            render_template(t, {})

    def test_render_invalid_template_raises(self) -> None:
        t = PromptTemplate(name="", description="", template="")  # type: ignore[arg-type]
        with pytest.raises(PromptTemplateValidationError, match="invalid"):
            render_template(t, {})

    def test_render_does_not_mutate_template(self) -> None:
        t = _make_template()
        original = t.template
        render_template(t, {"name": "Alice", "place": "Wonderland"})
        assert t.template == original

    def test_render_result_metadata(self) -> None:
        t = _make_template(metadata={"version": "2.0", "author": "test"})
        result = render_template(t, {"name": "A", "place": "B"})
        assert result.metadata == {"version": "2.0", "author": "test"}

    def test_render_result_fields(self) -> None:
        t = _make_template()
        result = render_template(t, {"name": "A", "place": "B"})
        assert isinstance(result, PromptRenderResult)
        assert result.template_name == "test_template"
        assert result.variables_used == frozenset({"name", "place"})
        assert result.render_duration_ms >= 0

    def test_render_variables_used_does_not_include_defaults_not_overridden(self) -> None:
        t = PromptTemplate(
            name="t",
            description="",
            template="{{a}}",
            variables=[
                PromptVariable(name="a", default="default_val"),
            ],
        )
        result = render_template(t, {})
        assert result.variables_used == frozenset({"a"})

    def test_render_empty_variables(self) -> None:
        t = PromptTemplate(name="static", description="", template="Hello world")
        result = render_template(t, {})
        assert result.text == "Hello world"

    def test_render_unicode(self) -> None:
        t = PromptTemplate(
            name="unicode",
            description="",
            template="{{greeting}}, {{name}}",
            variables=[
                PromptVariable(name="greeting"),
                PromptVariable(name="name"),
            ],
        )
        result = render_template(t, {"greeting": "Ciao", "name": "Mondo"})
        assert result.text == "Ciao, Mondo"

    def test_render_nested_curly_braces(self) -> None:
        t = PromptTemplate(
            name="nested",
            description="",
            template="{{x}} {not_a_var} {{y}}",
            variables=[
                PromptVariable(name="x"),
                PromptVariable(name="y"),
            ],
        )
        result = render_template(t, {"x": "1", "y": "2"})
        assert result.text == "1 {not_a_var} 2"


# ---------------------------------------------------------------------------
# PromptTemplateRegistry
# ---------------------------------------------------------------------------


class TestPromptTemplateRegistry:
    def test_register_and_get(self) -> None:
        reg = PromptTemplateRegistry()
        t = _make_template()
        reg.register(t)
        assert reg.get("test_template") == t

    def test_register_duplicate_raises(self) -> None:
        reg = PromptTemplateRegistry()
        reg.register(_make_template())
        with pytest.raises(DuplicateTemplateError, match="already registered"):
            reg.register(_make_template())

    def test_unregister_existing(self) -> None:
        reg = PromptTemplateRegistry()
        reg.register(_make_template())
        assert reg.unregister("test_template") is True
        assert reg.get("test_template") is None

    def test_unregister_missing(self) -> None:
        reg = PromptTemplateRegistry()
        assert reg.unregister("nonexistent") is False

    def test_has_existing(self) -> None:
        reg = PromptTemplateRegistry()
        reg.register(_make_template())
        assert reg.has("test_template") is True

    def test_has_missing(self) -> None:
        reg = PromptTemplateRegistry()
        assert reg.has("nonexistent") is False

    def test_list_empty(self) -> None:
        reg = PromptTemplateRegistry()
        assert reg.list() == []

    def test_list_returns_all(self) -> None:
        reg = PromptTemplateRegistry()
        a = _make_template(name="a")
        b = _make_template(name="b")
        reg.register(a)
        reg.register(b)
        assert reg.list() == [a, b]

    def test_count(self) -> None:
        reg = PromptTemplateRegistry()
        assert reg.count == 0
        reg.register(_make_template())
        assert reg.count == 1

    def test_register_invalid_raises(self) -> None:
        reg = PromptTemplateRegistry()
        t = PromptTemplate(name="", description="", template="")
        with pytest.raises(PromptTemplateValidationError):
            reg.register(t)

    def test_register_validates_before_storing(self) -> None:
        reg = PromptTemplateRegistry()
        t = PromptTemplate(name="t", description="", template="{{x}}", variables=[])
        with pytest.raises(PromptTemplateValidationError):
            reg.register(t)
        assert reg.count == 0

    def test_thread_safety(self) -> None:
        import threading
        reg = PromptTemplateRegistry()
        errors = []

        def register_templates(start: int) -> None:
            for i in range(start, start + 50):
                try:
                    reg.register(_make_template(name=f"t{i}"))
                except Exception as e:
                    errors.append(e)

        threads = [threading.Thread(target=register_templates, args=(i * 50,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert reg.count == 200


# ---------------------------------------------------------------------------
# AIManager integration
# ---------------------------------------------------------------------------


class TestAIManagerTemplates:
    def test_ask_with_template(self) -> None:
        manager = AIManager()
        manager.router.providers["mock"] = _MockProvider("mock")
        t = _make_template(
            template="Hello {{name}}",
            variables=[PromptVariable(name="name")],
        )
        manager.template_registry.register(t)
        result = manager.ask("mock", prompt_template="test_template", template_variables={"name": "Alice"})
        assert "Hello Alice" in str(result)

    def test_ask_template_metadata_in_response(self) -> None:
        manager = AIManager()
        manager.router.providers["mock"] = _MockProvider("mock")
        t = _make_template(
            template="Hello {{name}}",
            variables=[PromptVariable(name="name")],
            metadata={"version": "1.5"},
        )
        manager.template_registry.register(t)
        result = manager.ask("mock", prompt_template="test_template", template_variables={"name": "Alice"})
        assert result.metadata.get("template_name") == "test_template"
        assert result.metadata.get("template_version") == "1.5"
        assert "render_duration_ms" in result.metadata
        assert "template_variables" in result.metadata

    def test_ask_template_unregistered_raises(self) -> None:
        manager = AIManager()
        with pytest.raises(ValueError, match="not registered"):
            manager.ask("mock", prompt_template="nonexistent")

    def test_ask_template_missing_variable_raises(self) -> None:
        manager = AIManager()
        t = _make_template(
            template="Hello {{name}}",
            variables=[PromptVariable(name="name", required=True)],
        )
        manager.template_registry.register(t)
        with pytest.raises(PromptTemplateRenderError):
            manager.ask("mock", prompt_template="test_template", template_variables={})

    def test_ask_with_template_and_conversation(self) -> None:
        manager = AIManager()
        manager.router.providers["mock"] = _MockProvider("mock")
        t = _make_template(
            template="You said {{input}}",
            variables=[PromptVariable(name="input")],
        )
        manager.template_registry.register(t)
        conv = manager.create_conversation()
        result = manager.ask(
            "mock",
            prompt_template="test_template",
            template_variables={"input": "hello"},
            conversation_id=conv.conversation_id,
        )
        assert "You said hello" in str(result)
        # Rendered prompt stored in conversation, not placeholder
        stored = manager.conversation_manager.get(conv.conversation_id)
        assert stored is not None
        assert stored.messages[-2].content == "You said hello"

    def test_ask_template_does_not_affect_prompt_only_call(self) -> None:
        manager = AIManager()
        manager.router.providers["mock"] = _MockProvider("mock")
        result = manager.ask("mock", "direct prompt")
        assert str(result) == "mock: direct prompt"
        assert "template_name" not in result.metadata

    def test_ask_template_render_duration_positive(self) -> None:
        manager = AIManager()
        manager.router.providers["mock"] = _MockProvider("mock")
        t = _make_template(
            template="Hello {{name}}",
            variables=[PromptVariable(name="name")],
        )
        manager.template_registry.register(t)
        result = manager.ask(
            "mock",
            prompt_template="test_template",
            template_variables={"name": "World"},
        )
        assert result.metadata["render_duration_ms"] >= 0

    def test_ask_template_variables_used_in_metadata(self) -> None:
        manager = AIManager()
        manager.router.providers["mock"] = _MockProvider("mock")
        t = _make_template(
            template="{{a}} and {{b}}",
            variables=[
                PromptVariable(name="a"),
                PromptVariable(name="b"),
            ],
        )
        manager.template_registry.register(t)
        result = manager.ask(
            "mock",
            prompt_template="test_template",
            template_variables={"a": "1", "b": "2"},
        )
        assert "a" in result.metadata["template_variables"]
        assert "b" in result.metadata["template_variables"]

    def test_ask_with_template_and_tools(self) -> None:
        from app.ai.tools import ToolDefinition
        manager = AIManager()
        manager.router.providers["mock"] = _MockProvider(
            "mock", capabilities=frozenset({
                ProviderCapability.TEXT_GENERATION,
                ProviderCapability.FUNCTION_CALLING,
            }))
        t = _make_template(
            template="Tool {{query}}",
            variables=[PromptVariable(name="query")],
        )
        manager.template_registry.register(t)
        tool = ToolDefinition(
            name="test_tool",
            description="A test tool",
            parameters={"type": "object", "properties": {"x": {"type": "string"}}},
        )
        result = manager.ask(
            "mock",
            prompt_template="test_template",
            template_variables={"query": "run"},
            tools=[tool],
        )
        assert "Tool run" in str(result)

    def test_ask_with_template_and_schema(self) -> None:
        from app.ai.structured import StructuredSchema
        manager = AIManager()
        manager.router.providers["mock"] = _MockProvider(
            "mock", capabilities=frozenset({
                ProviderCapability.TEXT_GENERATION,
                ProviderCapability.JSON_OUTPUT,
            }))
        t = _make_template(
            template="JSON {{data}}",
            variables=[PromptVariable(name="data")],
        )
        manager.template_registry.register(t)
        schema = StructuredSchema(
            name="test_schema",
            schema={"type": "object", "properties": {"key": {"type": "string"}}},
        )
        result = manager.ask(
            "mock",
            prompt_template="test_template",
            template_variables={"data": "test"},
            schema=schema,
        )
        assert "JSON test" in str(result)

    def test_ask_with_template_and_tools_and_schema_and_conversation(self) -> None:
        from app.ai.structured import StructuredSchema
        from app.ai.tools import ToolDefinition
        manager = AIManager()
        manager.router.providers["mock"] = _MockProvider(
            "mock", capabilities=frozenset({
                ProviderCapability.TEXT_GENERATION,
                ProviderCapability.FUNCTION_CALLING,
                ProviderCapability.JSON_OUTPUT,
                ProviderCapability.STREAMING,
            }))
        t = _make_template(
            template="Combined {{x}}",
            variables=[PromptVariable(name="x")],
        )
        manager.template_registry.register(t)
        conv = manager.create_conversation()
        tool = ToolDefinition(
            name="t",
            description="tool",
            parameters={"type": "object", "properties": {}},
        )
        schema = StructuredSchema(
            name="s",
            schema={"type": "object", "properties": {}},
        )
        result = manager.ask(
            "mock",
            prompt_template="test_template",
            template_variables={"x": "all"},
            conversation_id=conv.conversation_id,
            tools=[tool],
            schema=schema,
        )
        assert "all" in str(result)

    def test_stream_with_template(self) -> None:
        manager = AIManager()
        manager.router.providers["mock"] = _MockProvider("mock")
        t = _make_template(
            template="Stream {{msg}}",
            variables=[PromptVariable(name="msg")],
        )
        manager.template_registry.register(t)
        stream = manager.ask_stream(
            "mock",
            prompt_template="test_template",
            template_variables={"msg": "hello"},
        )
        chunks = list(stream)
        assert len(chunks) >= 1
        final = stream.final_response()
        assert final.metadata.get("template_name") == "test_template"

    def test_stream_with_template_and_conversation_metadata(self) -> None:
        manager = AIManager()
        manager.router.providers["mock"] = _MockProvider("mock")
        t = _make_template(
            template="Conv {{x}}",
            variables=[PromptVariable(name="x")],
        )
        manager.template_registry.register(t)
        conv = manager.create_conversation()
        stream = manager.ask_stream(
            "mock",
            prompt_template="test_template",
            template_variables={"x": "stream"},
            conversation_id=conv.conversation_id,
        )
        list(stream)
        stored = manager.conversation_manager.get(conv.conversation_id)
        assert stored is not None
        # Rendered prompt stored in message
        assert stored.messages[-2].content == "Conv stream"

    def test_template_with_no_version_in_metadata(self) -> None:
        manager = AIManager()
        manager.router.providers["mock"] = _MockProvider("mock")
        t = _make_template(
            template="{{x}}",
            variables=[PromptVariable(name="x")],
            metadata={},
        )
        manager.template_registry.register(t)
        result = manager.ask(
            "mock",
            prompt_template="test_template",
            template_variables={"x": "v"},
        )
        assert "template_version" not in result.metadata


# ---------------------------------------------------------------------------
# Backward compatibility
# ---------------------------------------------------------------------------


class TestBackwardCompatibility:
    def test_ask_without_template_unchanged(self) -> None:
        manager = AIManager()
        manager.router.providers["mock"] = _MockProvider("mock")
        result = manager.ask("mock", "direct")
        assert str(result) == "mock: direct"

    def test_ask_without_template_metadata_empty(self) -> None:
        manager = AIManager()
        manager.router.providers["mock"] = _MockProvider("mock")
        result = manager.ask("mock", "direct")
        assert "template_name" not in result.metadata

    def test_ask_stream_without_template_unchanged(self) -> None:
        manager = AIManager()
        manager.router.providers["mock"] = _MockProvider("mock")
        stream = manager.ask_stream("mock", "direct")
        chunks = list(stream)
        assert len(chunks) >= 1

    def test_ask_with_template_and_empty_variables(self) -> None:
        manager = AIManager()
        manager.router.providers["mock"] = _MockProvider("mock")
        t = PromptTemplate(
            name="static",
            description="",
            template="Hello world",
            variables=[],
        )
        manager.template_registry.register(t)
        result = manager.ask("mock", prompt_template="static")
        assert "Hello world" in str(result)

    def test_existing_ask_signature_maintained(self) -> None:
        manager = AIManager()
        manager.router.providers["mock"] = _MockProvider("mock")
        result = manager.ask("mock", "hello", conversation_id=None)
        assert str(result) == "mock: hello"


# ---------------------------------------------------------------------------
# Error types
# ---------------------------------------------------------------------------


class TestPromptTemplateErrorHierarchy:
    def test_base_error_is_exception(self) -> None:
        assert issubclass(PromptTemplateError, Exception)

    def test_validation_error_subclass(self) -> None:
        assert issubclass(PromptTemplateValidationError, PromptTemplateError)

    def test_render_error_subclass(self) -> None:
        assert issubclass(PromptTemplateRenderError, PromptTemplateError)

    def test_duplicate_error_subclass(self) -> None:
        assert issubclass(DuplicateTemplateError, PromptTemplateError)

    def test_prompt_render_result_dataclass(self) -> None:
        r = PromptRenderResult(
            text="rendered",
            template_name="t",
            variables_used=frozenset({"a"}),
            render_duration_ms=1.5,
            metadata={"v": "1"},
        )
        assert r.text == "rendered"
        assert r.template_name == "t"
        assert r.variables_used == frozenset({"a"})
        assert r.render_duration_ms == 1.5
        assert r.metadata == {"v": "1"}
