from app.core.registry import ServiceRegistry


class Dispatcher:

    def __init__(self, registry: ServiceRegistry):

        self.registry = registry

        self.skill_manager = registry.get(
            "skill_manager"
        )

        self.memory = registry.get(
            "memory"
        )

        self._brains = {
            "fast": registry.get("fast_brain"),
            "smart": registry.get("smart_brain"),
            "deep": registry.get("deep_brain"),
        }

    def dispatch(self, request):

        # Store user message
        self.memory.remember(
            role="user",
            content=request.text,
            metadata={
                "intent": request.intent,
                "entities": request.entities,
                "brain": request.brain,
            },
        )

        # Update session context
        self.memory.set_context(
            intent=request.intent,
            entities=request.entities,
            skill=request.intent,
        )

        # Select brain by type
        brain = self._brains.get(
            request.brain,
            self._brains["deep"],
        )

        # Execute via brain
        result = brain.process(request)

        # Store assistant response
        self.memory.remember(
            role="assistant",
            content=result.message,
        )

        return result