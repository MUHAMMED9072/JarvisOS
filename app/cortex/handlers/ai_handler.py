from __future__ import annotations

from app.ai.conversation import Conversation
from app.ai.manager import AIManager
from app.ai.memory_integration import MemoryAwareAI, _try_get_memory_manager
from app.ai.providers.base import AIResponse, AIStreamResponse
from app.core.config import Config
from app.cortex.handlers import BaseHandler
from app.cortex.models import CortexResponse


class AIHandler(BaseHandler):
    """Thin wrapper around AIManager for LLM interactions.

    Automatically integrates with MemoryManager for context retrieval
    and memory recording.  Manages conversation lifecycle transparently:
    calls from the same handler instance share a single conversation.
    """

    DEFAULT_PROVIDER = Config.AI.conversation.default_provider

    def __init__(self, registry):
        super().__init__(registry)
        self._ai_manager: AIManager = registry.get("ai_manager")
        memory_ai = registry.get_optional("memory_aware_ai")
        if isinstance(memory_ai, MemoryAwareAI):
            self._memory_ai: MemoryAwareAI = memory_ai
        else:
            memory_manager = _try_get_memory_manager(registry)
            self._memory_ai = MemoryAwareAI(self._ai_manager, memory_manager)
        self._conversation_id: str | None = None

    # ------------------------------------------------------------------
    # Chat
    # ------------------------------------------------------------------

    def chat(
        self,
        prompt: str,
        *,
        provider: str | None = None,
        prompt_template: str | None = None,
        template_variables: dict[str, str] | None = None,
        conversation_id: str | None = None,
    ) -> AIResponse:
        """Send a chat prompt and return the ``AIResponse``.

        When *conversation_id* is provided the call uses that
        conversation (which must already exist).  Otherwise the
        handler manages its own default conversation, created on
        first call and reused for subsequent calls.
        """
        effective_conv = (
            conversation_id
            if conversation_id is not None
            else self._ensure_conversation(provider)
        )
        return self._memory_ai.ask(
            provider or self.DEFAULT_PROVIDER,
            prompt,
            conversation_id=effective_conv,
            prompt_template=prompt_template,
            template_variables=template_variables,
        )

    # ------------------------------------------------------------------
    # Streaming
    # ------------------------------------------------------------------

    def chat_stream(
        self,
        prompt: str,
        *,
        provider: str | None = None,
        prompt_template: str | None = None,
        template_variables: dict[str, str] | None = None,
        conversation_id: str | None = None,
    ) -> AIStreamResponse:
        """Send a chat prompt and return an ``AIStreamResponse``.

        Conversation semantics are identical to :meth:`chat`.
        """
        effective_conv = (
            conversation_id
            if conversation_id is not None
            else self._ensure_conversation(provider)
        )
        return self._memory_ai.ask_stream(
            provider or self.DEFAULT_PROVIDER,
            prompt,
            conversation_id=effective_conv,
            prompt_template=prompt_template,
            template_variables=template_variables,
        )

    # ------------------------------------------------------------------
    # Plan
    # ------------------------------------------------------------------

    def plan(
        self,
        objective: str,
        *,
        provider: str | None = None,
        prompt_template: str | None = None,
        template_variables: dict[str, str] | None = None,
        conversation_id: str | None = None,
    ) -> AIResponse:
        """Create a plan for *objective* and return the rendered text."""
        result = self._memory_ai.plan(
            objective,
            provider=provider or self.DEFAULT_PROVIDER,
            conversation_id=conversation_id,
            prompt_template=prompt_template,
            template_variables=template_variables,
        )
        return AIResponse(
            str(_plan_to_text(result.plan)),
            provider=result.provider,
            model=result.model,
            latency_ms=result.duration_ms,
            metadata=result.metadata,
        )

    # ------------------------------------------------------------------
    # Reason
    # ------------------------------------------------------------------

    def reason(
        self,
        objective: str,
        *,
        provider: str | None = None,
        prompt_template: str | None = None,
        template_variables: dict[str, str] | None = None,
        conversation_id: str | None = None,
    ) -> AIResponse:
        """Reason about *objective* and return the rendered text."""
        result = self._memory_ai.reason(
            objective,
            provider=provider or self.DEFAULT_PROVIDER,
            conversation_id=conversation_id,
            prompt_template=prompt_template,
            template_variables=template_variables,
        )
        return AIResponse(
            str(_chain_to_text(result.chain)),
            provider=result.provider,
            model=result.model,
            latency_ms=result.duration_ms,
            metadata=result.metadata,
        )

    # ------------------------------------------------------------------
    # Summarize
    # ------------------------------------------------------------------

    def summarize(self, text: str) -> AIResponse:
        """Summarize *text* via the default chat method."""
        return self.chat(f"Summarize the following:\n\n{text}")

    # ------------------------------------------------------------------
    # Conversation management
    # ------------------------------------------------------------------

    def _ensure_conversation(
        self, provider: str | None = None,
    ) -> str | None:
        """Return an existing conversation ID, creating one if needed."""
        if self._conversation_id is not None:
            return self._conversation_id
        conv = self.create_conversation(provider=provider)
        self._conversation_id = conv.conversation_id
        return self._conversation_id

    def create_conversation(
        self,
        provider: str | None = None,
    ) -> Conversation:
        """Create and return a new conversation."""
        from app.ai.conversation import Conversation
        return self._ai_manager.create_conversation(
            provider=provider or self.DEFAULT_PROVIDER,
        )

    def load_history(
        self,
        conversation_id: str | None = None,
    ) -> list[dict]:
        """Return messages for a conversation as role/content dicts.

        When *conversation_id* is ``None`` the handler's default
        conversation is queried.
        """
        conv_id = conversation_id or self._conversation_id
        if conv_id is None:
            return []
        conv = self._ai_manager.conversation_manager.get(conv_id)
        if conv is None:
            return []
        return [
            {"role": m.role, "content": m.content}
            for m in conv.messages
        ]

    # ------------------------------------------------------------------
    # Response translation
    # ------------------------------------------------------------------

    @staticmethod
    def translate_to_cortex_response(
        ai_response: AIResponse | None,
        request_text: str = "",
        routing_strategy: str = "",
        conversation_id: str = "",
        template_name: str = "",
    ) -> CortexResponse:
        """Translate an ``AIResponse`` into a ``CortexResponse``.

        When *ai_response* is ``None`` (e.g. the brain returned a
        plain string result), the produced response carries the
        input *request_text* as its ``response`` field.
        """
        meta = dict(ai_response.metadata) if ai_response and ai_response.metadata else {}
        return CortexResponse(
            success=True,
            response=str(ai_response) if ai_response is not None else request_text,
            provider=ai_response.provider or "" if ai_response is not None else "",
            model=ai_response.model or "" if ai_response is not None else "",
            routing_strategy=routing_strategy,
            conversation_id=conversation_id,
            template_name=template_name,
            metadata=meta,
        )


def _plan_to_text(plan) -> str:
    """Format a ``Plan`` as human-readable text."""
    lines = [f"Plan: {plan.title}", f"Objective: {plan.objective}", ""]
    for i, step in enumerate(plan.steps, 1):
        header = f"{i}. [{step.id}] {step.title} ({step.action_type.value})"
        lines.append(header)
        if step.description:
            lines.append(f"   {step.description}")
        if step.depends_on:
            lines.append(f"   Depends on: {', '.join(step.depends_on)}")
    if plan.metadata:
        lines.append(f"\nMetadata: {plan.metadata}")
    return "\n".join(lines)


def _chain_to_text(chain) -> str:
    """Format a ``ReasoningChain`` as human-readable text."""
    lines = [f"Objective: {chain.objective}", ""]
    if chain.assumptions:
        lines.append("Assumptions:")
        for a in chain.assumptions:
            lines.append(f"  - {a}")
        lines.append("")
    for i, step in enumerate(chain.steps, 1):
        header = f"{i}. [{step.id}] {step.title} ({step.step_type.value})"
        lines.append(header)
        if step.description:
            lines.append(f"   {step.description}")
        if step.evidence:
            lines.append(f"   Evidence: {step.evidence}")
        lines.append(f"   Confidence: {step.confidence}")
        if step.depends_on:
            lines.append(f"   Depends on: {', '.join(step.depends_on)}")
    lines.append(f"\nConclusion: {chain.conclusion}")
    lines.append(f"Confidence: {chain.confidence}")
    if chain.metadata:
        lines.append(f"\nMetadata: {chain.metadata}")
    return "\n".join(lines)
