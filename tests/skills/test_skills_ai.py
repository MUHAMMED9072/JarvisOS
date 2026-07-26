"""Tests for P9-06: Skills AI Integration.

Verifies that AI-powered skills flow through:
    Skill -> AIManager (capability-routed) -> AIRouter -> Provider
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from unittest.mock import MagicMock, patch

import pytest

from app.ai.conversation import Conversation
from app.ai.planning import Plan, PlanResult, PlanStep
from app.ai.providers.base import AIResponse, AIProviderError, ProviderCapability
from app.ai.reasoning import ReasoningChain, ReasoningResult, ReasoningStep
from app.core.registry import ServiceRegistry
from app.skills.base import Skill
from app.skills.result import SkillResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ai_response(text: str = "AI response", **kw: object) -> AIResponse:
    return AIResponse(
        text,
        provider=kw.get("provider", "test"),
        model=kw.get("model", "mock"),
        latency_ms=kw.get("latency_ms", 10.0),
        metadata=kw.get("metadata", {"routing": "preferred"}),
    )


def _make_registry(
    *, ai_manager: MagicMock | None = None,
) -> ServiceRegistry:
    registry = ServiceRegistry()
    if ai_manager is not None:
        registry.register("ai_manager", ai_manager)
    else:
        manager = MagicMock()
        manager.ask.return_value = _make_ai_response()
        registry.register("ai_manager", manager)
    registry.register("memory", MagicMock())
    registry.register("event_bus", MagicMock())
    registry.register("skill_manager", MagicMock())
    return registry


class _ConcreteSkill(Skill):
    name = "Test Skill"
    intent = "test"
    version = "1.0.0"
    description = "A test skill"

    def run(self, request):
        return SkillResult.ok(message="concrete run")


# ---------------------------------------------------------------------------
# Skill base AI helpers
# ---------------------------------------------------------------------------


class TestSkillAsk:
    """Skill.ask() delegates to AIManager with capability routing."""

    def test_calls_ai_manager_with_provider_none(self):
        ai_manager = MagicMock()
        ai_manager.ask.return_value = _make_ai_response("hello")
        registry = _make_registry(ai_manager=ai_manager)
        skill = _ConcreteSkill()
        skill.setup(registry)

        result = skill.ask("hello world")

        ai_manager.ask.assert_called_once()
        args, kwargs = ai_manager.ask.call_args
        assert args[0] is None  # provider=None for routing
        assert args[1] == "hello world"

    def test_returns_skill_result_with_message(self):
        skill = _ConcreteSkill()
        skill.setup(_make_registry())

        result = skill.ask("hello")

        assert isinstance(result, SkillResult)
        assert result.success is True
        assert result.message == "AI response"

    def test_returns_metadata_in_data(self):
        skill = _ConcreteSkill()
        skill.setup(_make_registry())

        result = skill.ask("hello")

        assert result.data["provider"] == "test"
        assert result.data["model"] == "mock"
        assert result.data["latency_ms"] == 10.0
        assert result.data["metadata"]["routing"] == "preferred"

    def test_fails_when_ai_manager_not_setup(self):
        skill = _ConcreteSkill()
        # Deliberately do NOT call setup()

        result = skill.ask("hello")

        assert result.success is False
        assert "AI not available" in result.message

    def test_fails_on_ai_exception(self):
        ai_manager = MagicMock()
        ai_manager.ask.side_effect = AIProviderError("API error")
        skill = _ConcreteSkill()
        skill.setup(_make_registry(ai_manager=ai_manager))

        result = skill.ask("hello")

        assert result.success is False
        assert "API error" in result.message

    def test_passes_conversation_id(self):
        ai_manager = MagicMock()
        ai_manager.ask.return_value = _make_ai_response()
        skill = _ConcreteSkill()
        skill.setup(_make_registry(ai_manager=ai_manager))

        skill.ask("hello", conversation_id="conv-1")

        _, kwargs = ai_manager.ask.call_args
        assert kwargs["conversation_id"] == "conv-1"

    def test_passes_prompt_template(self):
        ai_manager = MagicMock()
        ai_manager.ask.return_value = _make_ai_response()
        skill = _ConcreteSkill()
        skill.setup(_make_registry(ai_manager=ai_manager))

        skill.ask("hello", prompt_template="my_template", template_variables={"x": "y"})

        _, kwargs = ai_manager.ask.call_args
        assert kwargs["prompt_template"] == "my_template"
        assert kwargs["template_variables"] == {"x": "y"}

    def test_passes_tools_and_schema(self):
        ai_manager = MagicMock()
        ai_manager.ask.return_value = _make_ai_response()
        skill = _ConcreteSkill()
        skill.setup(_make_registry(ai_manager=ai_manager))

        tools = [MagicMock()]
        schema = MagicMock()
        skill.ask("hello", tools=tools, schema=schema)

        _, kwargs = ai_manager.ask.call_args
        assert kwargs["tools"] is tools
        assert kwargs["schema"] is schema

    def test_passes_capabilities(self):
        ai_manager = MagicMock()
        ai_manager.ask.return_value = _make_ai_response()
        skill = _ConcreteSkill()
        skill.setup(_make_registry(ai_manager=ai_manager))

        caps = frozenset({ProviderCapability.TEXT_GENERATION, ProviderCapability.STREAMING})
        skill.ask("hello", capabilities=caps)

        _, kwargs = ai_manager.ask.call_args
        assert kwargs["required_capabilities"] is caps

    def test_does_not_modify_skill_result_execution_time(self):
        skill = _ConcreteSkill()
        skill.setup(_make_registry())

        result = skill.ask("hello")
        # Skill.execute() sets execution_time and skill name, ask() should not reset them
        assert result.execution_time == 0
        assert result.skill == ""


class TestSkillPlan:
    """Skill.plan() delegates to AIManager with capability routing."""

    def test_calls_ai_manager_plan_with_provider_none(self):
        ai_manager = MagicMock()
        plan = Plan(objective="do something")
        ai_manager.plan.return_value = PlanResult(
            plan=plan, provider="test", model="mock",
            duration_ms=50.0, valid=True,
        )
        skill = _ConcreteSkill()
        skill.setup(_make_registry(ai_manager=ai_manager))

        result = skill.plan("do something")

        ai_manager.plan.assert_called_once_with(
            "do something", provider=None,
            conversation_id=None, prompt_template=None,
            template_variables=None,
        )
        assert result.success is True

    def test_returns_plan_metadata(self):
        ai_manager = MagicMock()
        plan = Plan(objective="do it")
        ai_manager.plan.return_value = PlanResult(
            plan=plan, provider="test", model="mock",
            duration_ms=50.0, valid=True,
            metadata={"routing": "preferred"},
        )
        skill = _ConcreteSkill()
        skill.setup(_make_registry(ai_manager=ai_manager))

        result = skill.plan("do it")

        assert result.data["provider"] == "test"
        assert result.data["model"] == "mock"
        assert result.data["duration_ms"] == 50.0
        assert result.data["valid"] is True

    def test_fails_when_ai_not_available(self):
        skill = _ConcreteSkill()

        result = skill.plan("objective")

        assert result.success is False
        assert "AI not available" in result.message

    def test_fails_on_exception(self):
        ai_manager = MagicMock()
        ai_manager.plan.side_effect = AIProviderError("plan failed")
        skill = _ConcreteSkill()
        skill.setup(_make_registry(ai_manager=ai_manager))

        result = skill.plan("objective")

        assert result.success is False


class TestSkillReason:
    """Skill.reason() delegates to AIManager with capability routing."""

    def test_calls_ai_manager_reason_with_provider_none(self):
        ai_manager = MagicMock()
        chain = ReasoningChain(objective="why", conclusion="because")
        ai_manager.reason.return_value = ReasoningResult(
            chain=chain, provider="test", model="mock",
            duration_ms=30.0, valid=True,
        )
        skill = _ConcreteSkill()
        skill.setup(_make_registry(ai_manager=ai_manager))

        result = skill.reason("why")

        ai_manager.reason.assert_called_once_with(
            "why", provider=None,
            conversation_id=None, prompt_template=None,
            template_variables=None,
        )
        assert result.success is True

    def test_returns_reasoning_metadata(self):
        ai_manager = MagicMock()
        chain = ReasoningChain(objective="why", conclusion="because")
        ai_manager.reason.return_value = ReasoningResult(
            chain=chain, provider="test", model="mock",
            duration_ms=30.0, valid=True,
            metadata={"routing": "preferred"},
        )
        skill = _ConcreteSkill()
        skill.setup(_make_registry(ai_manager=ai_manager))

        result = skill.reason("why")

        assert result.data["provider"] == "test"
        assert result.data["valid"] is True


class TestSkillCreateConversation:
    """Skill.create_conversation() delegates to AIManager."""

    def test_creates_conversation(self):
        ai_manager = MagicMock()
        ai_manager.create_conversation.return_value = Conversation(
            conversation_id="conv-new",
        )
        skill = _ConcreteSkill()
        skill.setup(_make_registry(ai_manager=ai_manager))

        conv = skill.create_conversation()

        assert conv.conversation_id == "conv-new"
        ai_manager.create_conversation.assert_called_once()

    def test_returns_none_when_ai_not_available(self):
        skill = _ConcreteSkill()

        conv = skill.create_conversation()

        assert conv is None


# ---------------------------------------------------------------------------
# ChatSkill AI integration
# ---------------------------------------------------------------------------


class TestChatSkill:
    """ChatSkill uses AI via self.ask()."""

    @pytest.fixture
    def skill(self):
        from app.skills.ai.chat import ChatSkill
        return ChatSkill()

    def test_run_delegates_to_ask(self, skill):
        ai_manager = MagicMock()
        ai_manager.ask.return_value = _make_ai_response("Hello from AI")
        skill._ai_manager = ai_manager

        request = MagicMock()
        request.text = "Hi there"
        result = skill.run(request)

        assert result.success is True
        assert result.message == "Hello from AI"

    def test_creates_conversation_on_first_call(self, skill):
        ai_manager = MagicMock()
        ai_manager.ask.return_value = _make_ai_response("reply")
        conv = Conversation(conversation_id="chat-1")
        ai_manager.create_conversation.return_value = conv
        skill._ai_manager = ai_manager
        skill._conversation_id = None

        request = MagicMock()
        request.text = "hello"
        skill.run(request)

        ai_manager.create_conversation.assert_called_once()
        _, kwargs = ai_manager.ask.call_args
        assert kwargs["conversation_id"] == "chat-1"

    def test_reuses_conversation(self, skill):
        ai_manager = MagicMock()
        ai_manager.ask.return_value = _make_ai_response("reply")
        conv = Conversation(conversation_id="chat-1")
        ai_manager.create_conversation.return_value = conv
        skill._ai_manager = ai_manager
        skill._conversation_id = None

        request = MagicMock()
        request.text = "first"
        skill.run(request)

        ai_manager.create_conversation.assert_called_once()

        request.text = "second"
        skill.run(request)

        ai_manager.create_conversation.assert_called_once()

    def test_returns_ai_metadata(self, skill):
        ai_manager = MagicMock()
        ai_manager.ask.return_value = _make_ai_response(
            "reply", provider="deepseek", model="deepseek-v3",
            latency_ms=120.0,
        )
        skill._ai_manager = ai_manager

        request = MagicMock()
        request.text = "hello"
        result = skill.run(request)

        assert result.data["provider"] == "deepseek"
        assert result.data["model"] == "deepseek-v3"
        assert result.data["latency_ms"] == 120.0

    def test_handles_ai_error_gracefully(self, skill):
        ai_manager = MagicMock()
        ai_manager.ask.side_effect = AIProviderError("API unavailable")
        skill._ai_manager = ai_manager

        request = MagicMock()
        request.text = "hello"
        result = skill.run(request)

        assert result.success is False
        assert "API unavailable" in result.message


# ---------------------------------------------------------------------------
# Backward compatibility
# ---------------------------------------------------------------------------


class TestSkillBackwardCompatibility:
    """Existing Skill subclasses work unchanged."""

    def test_existing_skill_executes_without_ai(self):
        skill = _ConcreteSkill()

        request = MagicMock()
        result = skill.execute(request)

        assert result.success is True
        assert result.message == "concrete run"
        assert result.skill == "Test Skill"
        assert result.execution_time >= 0

    def test_existing_skill_has_no_ai_manager_by_default(self):
        skill = _ConcreteSkill()
        assert skill._ai_manager is None

    def test_setup_injects_ai_manager_when_present(self):
        registry = _make_registry()
        skill = _ConcreteSkill()
        skill.setup(registry)

        assert skill._ai_manager is not None

    def test_setup_graceful_when_ai_manager_missing(self):
        registry = ServiceRegistry()
        registry.register("memory", MagicMock())
        registry.register("event_bus", MagicMock())
        registry.register("skill_manager", MagicMock())
        # Deliberately no "ai_manager"

        skill = _ConcreteSkill()
        skill.setup(registry)

        assert skill._ai_manager is None

    def test_existing_skill_attributes_untouched(self):
        skill = _ConcreteSkill()
        assert skill.name == "Test Skill"
        assert skill.intent == "test"
        assert skill.version == "1.0.0"
        assert isinstance(skill, Skill)

    def test_non_ai_skill_does_not_need_setup(self):
        skill = _ConcreteSkill()
        result = skill.execute(MagicMock())
        assert result.success is True


# ---------------------------------------------------------------------------
# AIManager.ask(provider=None) integration
# ---------------------------------------------------------------------------


class TestAIManagerRouting:
    """AIManager.ask() with provider=None uses capability routing."""

    def test_ask_with_none_provider_uses_ask_routed(self):
        from app.ai.manager import AIManager
        manager = AIManager()

        with patch.object(manager.router, "ask_routed") as mock_routed:
            mock_routed.return_value = _make_ai_response()
            result = manager.ask(None, "test prompt")

            mock_routed.assert_called_once()
            assert str(result) == "AI response"

    def test_ask_with_explicit_provider_uses_direct_ask(self):
        from app.ai.manager import AIManager
        manager = AIManager()

        with patch.object(manager.router, "ask") as mock_ask:
            mock_ask.return_value = _make_ai_response()
            result = manager.ask("deepseek", "test prompt")

            mock_ask.assert_called_once()
            assert str(result) == "AI response"

    def test_ask_routed_with_text_generation_capability(self):
        from app.ai.manager import AIManager
        manager = AIManager()

        with patch.object(manager.router, "ask_routed") as mock_routed:
            mock_routed.return_value = _make_ai_response()
            caps = frozenset({ProviderCapability.TEXT_GENERATION})
            manager.ask(None, "test", required_capabilities=caps)

            _, kwargs = mock_routed.call_args
            assert ProviderCapability.TEXT_GENERATION in kwargs["required_capabilities"]

    def test_ask_with_none_provider_and_conversation(self):
        from app.ai.manager import AIManager
        from app.ai.conversation import Conversation
        manager = AIManager()
        conv = manager.create_conversation()

        with patch.object(manager.router, "ask_routed") as mock_routed:
            mock_routed.return_value = _make_ai_response()
            result = manager.ask(None, "hello", conversation_id=conv.conversation_id)

            mock_routed.assert_called_once()
            assert str(result) == "AI response"
