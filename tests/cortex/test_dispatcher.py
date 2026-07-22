from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.core.registry import ServiceRegistry
from app.cortex.brains.deep_brain import DeepBrain
from app.cortex.brains.fast_brain import FastBrain
from app.cortex.brains.smart_brain import SmartBrain
from app.cortex.dispatcher import Dispatcher
from app.cortex.models import BrainType, CortexRequest
from app.skills.result import SkillResult


class TestDispatcher:
    @pytest.fixture
    def registry(self):
        r = ServiceRegistry()
        skill_manager = MagicMock()
        skill = MagicMock()
        skill.execute.return_value = SkillResult.ok(message="skill done")
        skill_manager.get.return_value = skill
        r.register("skill_manager", skill_manager)
        memory = MagicMock()
        r.register("memory", memory)
        r.register("ai_router", MagicMock())
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
            text="open browser",
            normalized="open browser",
            intent="open_application",
            confidence=0.98,
            entities={"application": "browser"},
            brain=BrainType.FAST.value,
        )

    def test_dispatch_returns_skill_result(self, dispatcher, cortex_request):
        result = dispatcher.dispatch(cortex_request)
        assert isinstance(result, SkillResult)

    def test_dispatch_fast_brain(self, dispatcher, cortex_request):
        result = dispatcher.dispatch(cortex_request)
        assert result.success is True

    def test_dispatch_smart_brain(self, dispatcher, cortex_request):
        cortex_request.brain = BrainType.SMART.value
        cortex_request.intent = "chat"
        cortex_request.text = "hello"
        result = dispatcher.dispatch(cortex_request)
        assert result.success is True

    def test_dispatch_deep_brain(self, dispatcher, cortex_request):
        cortex_request.brain = BrainType.DEEP.value
        result = dispatcher.dispatch(cortex_request)
        assert result.success is True

    def test_dispatch_unknown_brain_defaults_to_deep(self, dispatcher, cortex_request):
        cortex_request.brain = "nonexistent"
        result = dispatcher.dispatch(cortex_request)
        assert result.success is True

    def test_dispatch_stores_user_message(self, dispatcher, cortex_request):
        dispatcher.dispatch(cortex_request)
        dispatcher.memory.remember.assert_called()

    def test_dispatch_stores_assistant_response(self, dispatcher, cortex_request):
        dispatcher.dispatch(cortex_request)
        dispatcher.memory.remember.assert_called()

    def test_dispatch_sets_context(self, dispatcher, cortex_request):
        dispatcher.dispatch(cortex_request)
        dispatcher.memory.set_context.assert_called_once()
