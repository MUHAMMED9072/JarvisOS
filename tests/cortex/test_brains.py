from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.core.registry import ServiceRegistry
from app.cortex.brains import BaseBrain
from app.cortex.brains.deep_brain import DeepBrain
from app.cortex.brains.fast_brain import FastBrain
from app.cortex.brains.smart_brain import SmartBrain
from app.cortex.models import BrainType, CortexRequest
from app.skills.result import SkillResult


class TestBaseBrain:
    def test_cannot_instantiate_abstract(self):
        with pytest.raises(TypeError):
            BaseBrain(MagicMock())

    def test_concrete_brains_are_subclasses(self):
        registry = MagicMock()
        assert isinstance(FastBrain(registry), BaseBrain)
        assert isinstance(SmartBrain(registry), BaseBrain)
        assert isinstance(DeepBrain(registry), BaseBrain)


class TestFastBrain:
    @pytest.fixture
    def registry(self):
        r = ServiceRegistry()
        skill_manager = MagicMock()
        skill = MagicMock()
        skill.execute.return_value = SkillResult.ok(message="done")
        skill_manager.get.return_value = skill
        r.register("skill_manager", skill_manager)
        r.register("memory", MagicMock())
        r.register("ai_router", MagicMock())
        r.register("fast_brain", FastBrain(r))
        r.register("smart_brain", SmartBrain(r))
        r.register("deep_brain", DeepBrain(r))
        return r

    @pytest.fixture
    def brain(self, registry):
        return registry.get("fast_brain")

    @pytest.fixture
    def cortex_request(self):
        return CortexRequest(
            text="open browser",
            normalized="open browser",
            intent="open_application",
            confidence=0.98,
            entities={"application": "browser"},
            brain=BrainType.FAST.value,
        )

    def test_process_delegates_to_skill_manager(self, brain, cortex_request):
        result = brain.process(cortex_request)
        assert result.success is True
        assert result.message == "done"
        skill_manager = brain.registry.get("skill_manager")
        skill_manager.get.assert_called_once_with("open_application")

    def test_process_returns_skill_result(self, brain, cortex_request):
        result = brain.process(cortex_request)
        assert isinstance(result, SkillResult)

    def test_process_includes_execution_time(self, brain, cortex_request):
        result = brain.process(cortex_request)
        assert result.execution_time >= 0

    def test_process_fallback_intent(self, brain, cortex_request):
        cortex_request.intent = "unknown"
        result = brain.process(cortex_request)
        assert isinstance(result, SkillResult)


class TestSmartBrain:
    @pytest.fixture
    def registry(self):
        r = ServiceRegistry()
        memory = MagicMock()
        memory.get_session_messages.return_value = []
        r.register("skill_manager", MagicMock())
        r.register("memory", memory)
        ai_router = MagicMock()
        ai_router.ask.return_value = "Hello! How can I help you?"
        r.register("ai_router", ai_router)
        r.register("fast_brain", FastBrain(r))
        r.register("smart_brain", SmartBrain(r))
        r.register("deep_brain", DeepBrain(r))
        return r

    @pytest.fixture
    def brain(self, registry):
        return registry.get("smart_brain")

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

    def test_process_uses_ai_handler(self, brain, cortex_request):
        result = brain.process(cortex_request)
        assert result.success is True
        assert "Hello" in result.message
        brain.registry.get("ai_router").ask.assert_called_once()

    def test_process_returns_skill_result(self, brain, cortex_request):
        result = brain.process(cortex_request)
        assert isinstance(result, SkillResult)

    def test_process_includes_brain_data(self, brain, cortex_request):
        result = brain.process(cortex_request)
        assert result.data.get("brain") == "smart"


class TestDeepBrain:
    @pytest.fixture
    def registry(self):
        r = ServiceRegistry()
        skill_manager = MagicMock()
        fallback = MagicMock()
        fallback.intent = "unknown"
        skill_manager.fallback = fallback
        skill_manager.get.return_value = fallback
        r.register("skill_manager", skill_manager)
        r.register("memory", MagicMock())
        ai_router = MagicMock()
        ai_router.ask.return_value = "I'll help you with that."
        r.register("ai_router", ai_router)
        r.register("fast_brain", FastBrain(r))
        r.register("smart_brain", SmartBrain(r))
        r.register("deep_brain", DeepBrain(r))
        return r

    @pytest.fixture
    def brain(self, registry):
        return registry.get("deep_brain")

    @pytest.fixture
    def cortex_request(self):
        return CortexRequest(
            text="do something complex",
            normalized="do something complex",
            intent="unknown",
            confidence=0.3,
            entities={},
            brain=BrainType.DEEP.value,
        )

    def test_process_fallback_uses_ai(self, brain, cortex_request):
        result = brain.process(cortex_request)
        assert result.success is True
        assert result.data.get("brain") == "deep"
        assert "plan" in result.data

    def test_process_known_intent_uses_skill(self, brain, cortex_request):
        cortex_request.intent = "open_application"
        cortex_request.brain = BrainType.DEEP.value
        skill_manager = brain.registry.get("skill_manager")
        known_skill = MagicMock()
        known_skill.execute.return_value = SkillResult.ok(message="Opening app")
        skill_manager.get.return_value = known_skill
        skill_manager.fallback = MagicMock()

        result = brain.process(cortex_request)
        assert result.success is True
        assert result.message == "Opening app"

    def test_process_returns_skill_result(self, brain, cortex_request):
        result = brain.process(cortex_request)
        assert isinstance(result, SkillResult)
