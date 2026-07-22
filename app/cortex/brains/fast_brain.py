from __future__ import annotations

from app.cortex.brains import BaseBrain
from app.cortex.models import CortexRequest
from app.skills.result import SkillResult


class FastBrain(BaseBrain):
    """Fast path: delegates directly to SkillManager for deterministic intents."""

    def process(self, request: CortexRequest) -> SkillResult:
        skill_manager = self.registry.get("skill_manager")
        skill = skill_manager.get(request.intent)
        return skill.execute(request)
