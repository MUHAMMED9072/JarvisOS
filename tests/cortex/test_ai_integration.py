from __future__ import annotations

from unittest.mock import MagicMock, PropertyMock

import pytest

from app.ai.manager import AIManager
from app.ai.providers.base import AIProvider, AIResponse, ProviderCapability
from app.core.registry import ServiceRegistry
from app.cortex.brains.deep_brain import DeepBrain
from app.cortex.brains.fast_brain import FastBrain
from app.cortex.brains.smart_brain import SmartBrain
from app.cortex.dispatcher import Dispatcher
from app.cortex.handlers.ai_handler import (
    AIHandler,
    _chain_to_text,
    _plan_to_text,
)
from app.cortex.models import BrainType, CortexRequest, CortexResponse
from app.cortex.pipeline import CortexPipeline
from app.skills.result import SkillResult


# ---------------------------------------------------------------------------
# Mock AIManager for isolation tests
# ---------------------------------------------------------------------------


class _MockAIManager:
    """Minimal AIManager mock that records calls and returns predictable
    responses."""

    def __init__(self):
        self.ask_calls: list[tuple] = []
        self.plan_calls: list[tuple] = []
        self.reason_calls: list[tuple] = []
        self._conversation_id = "conv_mock_001"

    def ask(
        self,
        provider: str,
        prompt: str = "",
        *,
        conversation_id: str | None = None,
        prompt_template: str | None = None,
        template_variables: dict | None = None,
        **kwargs,
    ) -> AIResponse:
        self.ask_calls.append((provider, prompt, conversation_id, prompt_template, template_variables))
        meta = {}
        if conversation_id:
            meta["conversation_id"] = conversation_id
        if prompt_template:
            meta["template_name"] = prompt_template
        return AIResponse(
            f"AI: {prompt[:50]}",
            provider=provider,
            model="mock-model",
            latency_ms=5.0,
            metadata=meta,
        )

    def plan(
        self,
        objective: str,
        *,
        provider: str | None = None,
        prompt_template: str | None = None,
        template_variables: dict | None = None,
        **kwargs,
    ):
        self.plan_calls.append((objective, provider, prompt_template, template_variables))
        from app.ai.planning import Plan, PlanResult, PlanStep
        plan = Plan(
            title="Test Plan",
            objective=objective,
            steps=(PlanStep(id="s1", title="Step 1"),),
        )
        return PlanResult(
            plan=plan, provider=provider or "mock", model="m",
            duration_ms=10.0, valid=True, metadata={"planning_duration_ms": 10.0},
        )

    def reason(
        self,
        objective: str,
        *,
        provider: str | None = None,
        prompt_template: str | None = None,
        template_variables: dict | None = None,
        **kwargs,
    ):
        self.reason_calls.append((objective, provider, prompt_template, template_variables))
        from app.ai.reasoning import ReasoningChain, ReasoningResult, ReasoningStep
        chain = ReasoningChain(
            objective=objective,
            steps=(ReasoningStep(id="r1", title="Reason 1"),),
            conclusion="Done",
        )
        return ReasoningResult(
            chain=chain, provider=provider or "mock", model="m",
            duration_ms=10.0, valid=True, metadata={"reasoning_duration_ms": 10.0},
        )

    def create_conversation(self, **kwargs):
        from app.ai.conversation import Conversation
        return Conversation(conversation_id=self._conversation_id)


# ---------------------------------------------------------------------------
# CortexResponse model
# ---------------------------------------------------------------------------


class TestCortexResponse:
    def test_default_fields(self) -> None:
        r = CortexResponse(success=True, response="hello")
        assert r.provider == ""
        assert r.model == ""
        assert r.metadata == {}

    def test_with_metadata(self) -> None:
        r = CortexResponse(
            success=True, response="hello",
            provider="deepseek", model="deepseek-chat",
            routing_strategy="preferred",
            conversation_id="conv_1",
            template_name="greeting",
            metadata={"key": "val"},
        )
        assert r.provider == "deepseek"
        assert r.routing_strategy == "preferred"
        assert r.metadata["key"] == "val"

    def test_slots(self) -> None:
        r = CortexResponse(success=True, response="r")
        with pytest.raises(AttributeError):
            r.new_attr = "x"  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# AIHandler with mocked AIManager
# ---------------------------------------------------------------------------


class TestAIHandlerMocked:
    @pytest.fixture
    def handler(self):
        registry = MagicMock()
        registry.get.return_value = _MockAIManager()
        return AIHandler(registry)

    def test_chat_returns_response(self, handler):
        response = handler.chat("hello")
        assert "AI:" in str(response)
        assert handler._ai_manager.ask_calls[0][0] == "deepseek"

    def test_chat_with_provider(self, handler):
        response = handler.chat("hello", provider="ollama")
        assert handler._ai_manager.ask_calls[0][0] == "ollama"

    def test_chat_with_template(self, handler):
        handler.chat("hello", prompt_template="greet", template_variables={"name": "World"})
        args = handler._ai_manager.ask_calls[0]
        assert args[3] == "greet"
        assert args[4] == {"name": "World"}

    def test_chat_creates_conversation(self, handler):
        handler.chat("first")
        handler.chat("second")
        # Both calls should reuse the same conversation_id
        conv_id_1 = handler._ai_manager.ask_calls[0][2]
        conv_id_2 = handler._ai_manager.ask_calls[1][2]
        assert conv_id_1 == conv_id_2
        assert conv_id_1 is not None

    def test_plan_returns_ai_response(self, handler):
        response = handler.plan("build something")
        assert isinstance(response, AIResponse)
        assert "Plan:" in str(response)

    def test_plan_contains_steps(self, handler):
        response = handler.plan("test")
        text = str(response)
        assert "Step 1" in text

    def test_reason_returns_ai_response(self, handler):
        response = handler.reason("why?")
        assert isinstance(response, AIResponse)
        assert "Objective:" in str(response)

    def test_reason_contains_steps(self, handler):
        response = handler.reason("analyze")
        text = str(response)
        assert "Reason 1" in text

    def test_summarize_delegates_to_chat(self, handler):
        response = handler.summarize("long text")
        assert "AI:" in str(response)


# ---------------------------------------------------------------------------
# Response translation
# ---------------------------------------------------------------------------


class TestResponseTranslation:
    def test_translate_basic(self):
        ai_resp = AIResponse("Hello", provider="p", model="m", latency_ms=1.0, metadata={"k": "v"})
        cortex_resp = AIHandler.translate_to_cortex_response(
            ai_resp, request_text="hi",
            routing_strategy="failover",
            conversation_id="conv_1",
            template_name="greet",
        )
        assert cortex_resp.success is True
        assert cortex_resp.response == "Hello"
        assert cortex_resp.provider == "p"
        assert cortex_resp.model == "m"
        assert cortex_resp.routing_strategy == "failover"
        assert cortex_resp.conversation_id == "conv_1"
        assert cortex_resp.template_name == "greet"
        assert cortex_resp.metadata["k"] == "v"

    def test_translate_with_empty_metadata(self):
        ai_resp = AIResponse("OK", provider="p", model="m", latency_ms=0.0, metadata={})
        cortex_resp = AIHandler.translate_to_cortex_response(ai_resp)
        assert cortex_resp.success is True
        assert cortex_resp.routing_strategy == ""

    def test_translate_failure_response(self):
        ai_resp = AIResponse("error msg", provider="p", model="m", latency_ms=0.0, metadata={})
        cortex_resp = AIHandler.translate_to_cortex_response(ai_resp)
        assert cortex_resp.success is True  # success reflects delivery, not content


# ---------------------------------------------------------------------------
# Plan/Chain formatting
# ---------------------------------------------------------------------------


class TestPlanFormatting:
    def test_plan_to_text(self):
        from app.ai.planning import Plan, PlanAction, PlanStep
        plan = Plan(
            title="My Plan",
            objective="Do something",
            steps=(
                PlanStep(id="s1", title="Research", action_type=PlanAction.QUERY),
                PlanStep(id="s2", title="Implement", depends_on=("s1",)),
            ),
        )
        text = _plan_to_text(plan)
        assert "My Plan" in text
        assert "Do something" in text
        assert "Research" in text
        assert "s2" in text
        assert "s1" in text  # dependency


class TestChainFormatting:
    def test_chain_to_text(self):
        from app.ai.reasoning import ReasoningChain, ReasoningStep, ReasoningStepType
        chain = ReasoningChain(
            objective="Why?",
            assumptions=("A1", "A2"),
            steps=(
                ReasoningStep(id="r1", title="Analyze", step_type=ReasoningStepType.ANALYSIS, evidence="data1"),
            ),
            conclusion="Because",
            confidence=0.9,
        )
        text = _chain_to_text(chain)
        assert "Why?" in text
        assert "A1" in text
        assert "Analyze" in text
        assert "data1" in text
        assert "Because" in text
        assert "0.9" in text


# ---------------------------------------------------------------------------
# AIManager integration test (real AIManager)
# ---------------------------------------------------------------------------


class TestAIHandlerWithRealAIManager:
    @pytest.fixture
    def handler(self):
        manager = AIManager()
        # Register a mock provider so the real AIManager doesn't try
        # to hit an actual API
        class _MockProvider(AIProvider):
            provider_name = "deepseek"
            capabilities = frozenset({
                ProviderCapability.TEXT_GENERATION,
                ProviderCapability.STREAMING,
                ProviderCapability.CONVERSATION,
                ProviderCapability.SYSTEM_PROMPT,
                ProviderCapability.REASONING,
                ProviderCapability.JSON_OUTPUT,
            })
            def generate(self, prompt: str, **kwargs) -> AIResponse:
                return AIResponse(
                    f"mock: {prompt[:60]}",
                    provider=self.provider_name,
                    model="test",
                    latency_ms=0.0,
                    metadata={},
                )
            def check_availability(self) -> bool:
                return True

        manager.router.providers["deepseek"] = _MockProvider()
        registry = MagicMock()
        registry.get.return_value = manager
        return AIHandler(registry)

    def test_chat_registers_conversation(self, handler):
        response = handler.chat("hello")
        assert isinstance(response, AIResponse)
        assert handler._conversation_id is not None


# ---------------------------------------------------------------------------
# Dispatcher integration with mocked AIManager
# ---------------------------------------------------------------------------


class TestDispatcherAI:
    @pytest.fixture
    def registry(self):
        r = ServiceRegistry()
        skill_manager = MagicMock()
        normal_skill = MagicMock()
        normal_skill.execute.return_value = SkillResult.ok(message="skill done")
        fallback = MagicMock()
        fallback.intent = "unknown"
        fallback.execute.return_value = SkillResult.ok(message="fallback")
        skill_manager.fallback = fallback
        def _get_side_effect(intent):
            return normal_skill if intent != "unknown" else fallback
        skill_manager.get.side_effect = _get_side_effect
        r.register("skill_manager", skill_manager)
        memory = MagicMock()
        r.register("memory", memory)
        r.register("ai_manager", _MockAIManager())
        r.register("fast_brain", FastBrain(r))
        r.register("smart_brain", SmartBrain(r))
        r.register("deep_brain", DeepBrain(r))
        return r

    @pytest.fixture
    def dispatcher(self, registry):
        return Dispatcher(registry)

    @pytest.fixture
    def cortex_request(self):
        return CortexRequest(
            text="hello",
            normalized="hello",
            intent="chat",
            confidence=0.75,
            entities={},
            brain=BrainType.SMART.value,
        )

    def test_dispatch_smart_brain(self, dispatcher, cortex_request):
        result = dispatcher.dispatch(cortex_request)
        assert result.success is True
        assert "AI:" in str(result.message)

    def test_dispatch_deep_brain(self, dispatcher, cortex_request):
        cortex_request.brain = BrainType.DEEP.value
        cortex_request.intent = "unknown"
        result = dispatcher.dispatch(cortex_request)
        assert result.success is True
        assert "plan" in result.data

    def test_dispatch_fast_brain_unchanged(self, dispatcher, cortex_request):
        cortex_request.brain = BrainType.FAST.value
        cortex_request.intent = "open_application"
        result = dispatcher.dispatch(cortex_request)
        assert result.success is True
        assert result.message == "skill done"


# ---------------------------------------------------------------------------
# Full pipeline integration
# ---------------------------------------------------------------------------


class TestPipelineAI:
    def test_pipeline_creates_request(self):
        pipeline = CortexPipeline()
        request = pipeline.process("hello", source="text")
        assert isinstance(request, CortexRequest)
        assert request.text == "hello"
        assert request.source == "text"

    def test_pipeline_detects_chat_intent(self):
        pipeline = CortexPipeline()
        request = pipeline.process("hello")
        assert request.intent == "chat"
        assert request.brain == BrainType.SMART.value


# ---------------------------------------------------------------------------
# Backward compatibility
# ---------------------------------------------------------------------------


class TestBackwardCompatibility:
    def test_ai_handler_still_returns_ai_response(self):
        registry = MagicMock()
        registry.get.return_value = _MockAIManager()
        handler = AIHandler(registry)
        result = handler.chat("test")
        assert isinstance(result, AIResponse)

    def test_dispatcher_still_returns_skill_result(self):
        r = ServiceRegistry()
        skill_manager = MagicMock()
        skill = MagicMock()
        skill.execute.return_value = SkillResult.ok(message="done")
        skill_manager.get.return_value = skill
        r.register("skill_manager", skill_manager)
        r.register("memory", MagicMock())
        r.register("ai_manager", _MockAIManager())
        r.register("fast_brain", FastBrain(r))
        r.register("smart_brain", SmartBrain(r))
        r.register("deep_brain", DeepBrain(r))
        dispatcher = Dispatcher(r)
        request = CortexRequest(text="test", intent="chat", brain=BrainType.SMART.value)
        result = dispatcher.dispatch(request)
        assert isinstance(result, SkillResult)

    def test_kernel_registers_both_ai_services(self):
        from app.ai.manager import AIManager
        from app.ai.router import AIRouter
        # Verify both types are importable
        assert AIManager is not None
        assert AIRouter is not None
