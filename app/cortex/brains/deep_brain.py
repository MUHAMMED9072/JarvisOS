from __future__ import annotations

from app.cortex.brains import BaseBrain
from app.cortex.handlers.ai_handler import AIHandler
from app.cortex.models import CortexRequest
from app.skills.result import SkillResult


class DeepBrain(BaseBrain):
    """Deep reasoning path: tries SkillManager first, then AI reasoning."""

    def __init__(self, registry):
        super().__init__(registry)
        self._ai = AIHandler(registry)

    def process(self, request: CortexRequest) -> SkillResult:
        skill_manager = self.registry.get("skill_manager")
        skill = skill_manager.get(request.intent)
        if skill is not skill_manager.fallback:
            return skill.execute(request)

        plan_text = self._ai.plan(request.text)
        response = self._ai.chat(
            f"Based on this plan:\n{plan_text}\n\n"
            f"Handle this request: {request.text}"
        )
        return SkillResult.ok(
            message=response,
            data={"brain": "deep", "plan": str(plan_text)},
        )
