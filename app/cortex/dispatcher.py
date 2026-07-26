from app.core.registry import ServiceRegistry
from app.cortex.handlers.ai_handler import AIHandler
from app.cortex.models import CortexRequest, CortexResponse
from app.skills.result import SkillResult


class Dispatcher:

    def __init__(self, registry: ServiceRegistry):

        self.registry = registry
        self.skill_manager = registry.get("skill_manager")
        self.memory = registry.get("memory")
        self._ai_handler = AIHandler(registry)

        self._brains = {
            "fast": registry.get("fast_brain"),
            "smart": registry.get("smart_brain"),
            "deep": registry.get("deep_brain"),
        }

    def dispatch(self, request: CortexRequest) -> SkillResult:

        self.memory.remember(
            role="user",
            content=request.text,
            metadata={
                "intent": request.intent,
                "entities": request.entities,
                "brain": request.brain,
            },
        )

        self.memory.set_context(
            intent=request.intent,
            entities=request.entities,
            skill=request.intent,
        )

        brain = self._brains.get(
            request.brain,
            self._brains["deep"],
        )

        result = brain.process(request)

        self.memory.remember(
            role="assistant",
            content=result.message,
        )

        return result

    def dispatch_with_response(
        self, request: CortexRequest,
    ) -> tuple[SkillResult, CortexResponse]:
        """Dispatch *request* and return both ``SkillResult`` and
        ``CortexResponse``."""
        result = self.dispatch(request)
        cortex_response = AIHandler.translate_to_cortex_response(
            result.message if hasattr(result.message, "metadata") else None,
            request_text=request.text,
        )
        return result, cortex_response