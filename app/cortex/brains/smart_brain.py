from __future__ import annotations

from app.cortex.brains import BaseBrain
from app.cortex.handlers.ai_handler import AIHandler
from app.cortex.handlers.memory_handler import MemoryHandler
from app.cortex.models import CortexRequest
from app.skills.result import SkillResult


class SmartBrain(BaseBrain):
    """Conversational path: uses AIManager via AIHandler with memory context."""

    def __init__(self, registry):
        super().__init__(registry)
        self._ai = AIHandler(registry)
        self._memory = MemoryHandler(registry)

    def process(self, request: CortexRequest) -> SkillResult:
        context = self._memory.get_session_context()
        messages = context.get("messages", [])
        recent = "\n".join(
            f"{m['role']}: {m['content']}"
            for m in messages[-6:]
        )
        prompt = (
            f"Previous conversation:\n{recent}\n\n"
            f"User: {request.text}\nAssistant:"
        )
        response = self._ai.chat(prompt)
        return SkillResult.ok(message=response, data={"brain": "smart"})
