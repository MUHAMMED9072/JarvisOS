from __future__ import annotations

from abc import ABC, abstractmethod
from time import perf_counter

from app.skills.result import SkillResult


class Skill(ABC):

    name = "Unnamed Skill"
    intent = ""
    version = "1.0.0"
    description = ""
    author = "JarvisOS"

    def __init__(self):

        # Injected by SkillLoader
        self.memory = None
        self.event_bus = None
        self.logger = None
        self.skill_manager = None
        self._ai_manager = None

    def setup(self, registry):
        """
        Inject shared services from the Kernel.
        """

        self.memory = registry.get("memory")
        self.event_bus = registry.get("event_bus")
        self.skill_manager = registry.get("skill_manager")
        self._ai_manager = (
            registry.get("ai_manager")
            if registry.exists("ai_manager")
            else None
        )

    def execute(self, request):

        start = perf_counter()

        try:

            result = self.run(request)

            if not isinstance(result, SkillResult):
                raise TypeError(
                    f"{self.__class__.__name__}.run() must return SkillResult"
                )

        except Exception as e:

            result = SkillResult.fail(
                message=str(e)
            )

        result.skill = self.name
        result.execution_time = round(
            perf_counter() - start,
            4
        )

        return result

    # ------------------------------------------------------------------
    # AI integration helpers
    # ------------------------------------------------------------------

    def ask(
        self,
        prompt: str,
        *,
        conversation_id: str | None = None,
        prompt_template: str | None = None,
        template_variables: dict[str, str] | None = None,
        tools: list | None = None,
        schema: object | None = None,
        capabilities: frozenset | None = None,
    ) -> SkillResult:
        """Send a prompt to AI via capability routing and return a
        ``SkillResult`` with the response text and AI metadata.

        Returns ``SkillResult.fail`` when the AI manager is unavailable
        or the AI call raises an exception.
        """
        if self._ai_manager is None:
            return SkillResult.fail(message="AI not available")

        try:
            response = self._ai_manager.ask(
                None, prompt,
                conversation_id=conversation_id,
                prompt_template=prompt_template,
                template_variables=template_variables,
                tools=tools,
                schema=schema,
                required_capabilities=capabilities,
            )
            data = {
                "provider": response.provider,
                "model": response.model,
                "latency_ms": response.latency_ms,
            }
            if response.metadata:
                data["metadata"] = dict(response.metadata)
            return SkillResult.ok(message=str(response), data=data)

        except Exception as exc:
            return SkillResult.fail(message=str(exc))

    def plan(
        self,
        objective: str,
        *,
        conversation_id: str | None = None,
        prompt_template: str | None = None,
        template_variables: dict[str, str] | None = None,
    ) -> SkillResult:
        """Create an AI plan via capability routing and return a
        ``SkillResult`` with the plan text and metadata."""
        if self._ai_manager is None:
            return SkillResult.fail(message="AI not available")

        try:
            result = self._ai_manager.plan(
                objective,
                provider=None,
                conversation_id=conversation_id,
                prompt_template=prompt_template,
                template_variables=template_variables,
            )
            data = {
                "provider": result.provider,
                "model": result.model,
                "duration_ms": result.duration_ms,
                "valid": result.valid,
            }
            if result.metadata:
                data["metadata"] = dict(result.metadata)
            return SkillResult.ok(message=str(result.plan), data=data)

        except Exception as exc:
            return SkillResult.fail(message=str(exc))

    def reason(
        self,
        objective: str,
        *,
        conversation_id: str | None = None,
        prompt_template: str | None = None,
        template_variables: dict[str, str] | None = None,
    ) -> SkillResult:
        """Run AI reasoning via capability routing and return a
        ``SkillResult`` with the reasoning text and metadata."""
        if self._ai_manager is None:
            return SkillResult.fail(message="AI not available")

        try:
            result = self._ai_manager.reason(
                objective,
                provider=None,
                conversation_id=conversation_id,
                prompt_template=prompt_template,
                template_variables=template_variables,
            )
            data = {
                "provider": result.provider,
                "model": result.model,
                "duration_ms": result.duration_ms,
                "valid": result.valid,
            }
            if result.metadata:
                data["metadata"] = dict(result.metadata)
            return SkillResult.ok(message=str(result.chain), data=data)

        except Exception as exc:
            return SkillResult.fail(message=str(exc))

    def create_conversation(
        self,
        provider: str = "",
        model: str = "",
        system_prompt: str = "",
        max_messages: int = 50,
        metadata: dict | None = None,
    ):
        """Create a new conversation for multi-turn AI interactions.

        Returns ``None`` when the AI manager is unavailable.
        """
        if self._ai_manager is None:
            return None
        return self._ai_manager.create_conversation(
            provider=provider,
            model=model,
            system_prompt=system_prompt,
            max_messages=max_messages,
            metadata=metadata,
        )

    @abstractmethod
    def run(self, request):
        pass