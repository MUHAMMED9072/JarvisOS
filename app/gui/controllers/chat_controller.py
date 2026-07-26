from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.ai.providers.base import AIResponse, AIStreamResponse
from app.cortex.handlers.ai_handler import AIHandler
from app.cortex.handlers.memory_handler import MemoryHandler

try:
    from app.core.event_bus import EventBus
except ImportError:
    EventBus = Any  # type: ignore[assignment,misc]


@dataclass
class ChatResult:
    """Result of a GUI AI operation with full metadata."""

    success: bool
    response: str
    response_type: str = "chat"  # "chat" | "plan" | "reason"
    provider: str = ""
    model: str = ""
    conversation_id: str = ""
    latency_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    error: str = ""


class ChatController:
    """Orchestrates AI chat, planning, reasoning, and streaming for the
    GUI frontend.

    Manages its own conversation lifecycle so that each chat "session"
    (created via ``new_conversation()``) has an independent conversation
    with the AI backend.  All AI calls go through AIHandler (and
    therefore MemoryAwareAI), preserving the existing memory integration.
    """

    def __init__(self, registry) -> None:
        self.registry = registry
        self._ai = AIHandler(registry)
        self._memory = MemoryHandler(registry)
        self._provider = self._resolve_provider()
        self._conversation_id: str | None = None
        self._event_bus: EventBus | None = None

        self.on_voice_input: Callable[[str], None] | None = None

    # ------------------------------------------------------------------
    # Provider resolution
    # ------------------------------------------------------------------

    def _resolve_provider(self) -> str:
        router = self.registry.get("ai_router")
        available = list(router.providers.keys())
        if "deepseek" in available:
            return "deepseek"
        if "ollama" in available:
            return "ollama"
        if available:
            return available[0]
        return "deepseek"

    def get_provider(self) -> str:
        return self._provider

    # ------------------------------------------------------------------
    # Conversation management
    # ------------------------------------------------------------------

    def _ensure_conversation(self) -> str:
        if self._conversation_id is None:
            conv = self._ai.create_conversation(provider=self._provider)
            self._conversation_id = conv.conversation_id
        return self._conversation_id

    def new_conversation(self) -> None:
        self._conversation_id = None

    def get_conversation_id(self) -> str | None:
        return self._conversation_id

    # ------------------------------------------------------------------
    # Chat
    # ------------------------------------------------------------------

    def send_message(
        self,
        text: str,
        *,
        provider: str | None = None,
        prompt_template: str | None = None,
        template_variables: dict[str, str] | None = None,
    ) -> ChatResult:
        """Send a chat message and return the result with metadata."""
        if not isinstance(text, str) or not text.strip():
            return ChatResult(
                success=False, response="", error="Message cannot be empty.",
            )

        effective = provider or self._provider
        conv_id = self._ensure_conversation()

        try:
            response = self._ai.chat(
                text,
                provider=effective,
                conversation_id=conv_id,
                prompt_template=prompt_template,
                template_variables=template_variables,
            )
            return ChatResult(
                success=True,
                response=str(response),
                provider=response.provider or effective,
                model=response.model or "",
                conversation_id=conv_id,
                latency_ms=response.latency_ms,
                metadata=dict(response.metadata) if response.metadata else {},
            )
        except Exception as exc:
            return ChatResult(
                success=False, response="", error=f"AI request failed: {exc}",
            )

    # ------------------------------------------------------------------
    # Streaming
    # ------------------------------------------------------------------

    def send_message_stream(
        self,
        text: str,
        *,
        provider: str | None = None,
        prompt_template: str | None = None,
        template_variables: dict[str, str] | None = None,
    ) -> AIStreamResponse:
        """Send a chat message and return an ``AIStreamResponse``.

        The caller is responsible for iterating the stream and
        calling ``final_response()`` to get the complete result.
        """
        effective = provider or self._provider
        conv_id = self._ensure_conversation()
        return self._ai.chat_stream(
            text,
            provider=effective,
            conversation_id=conv_id,
            prompt_template=prompt_template,
            template_variables=template_variables,
        )

    # ------------------------------------------------------------------
    # Planning
    # ------------------------------------------------------------------

    def send_plan(
        self,
        objective: str,
        *,
        provider: str | None = None,
        prompt_template: str | None = None,
        template_variables: dict[str, str] | None = None,
    ) -> ChatResult:
        """Create a plan for *objective* and return the rendered result."""
        if not isinstance(objective, str) or not objective.strip():
            return ChatResult(
                success=False, response="", error="Objective cannot be empty.",
            )

        effective = provider or self._provider

        try:
            response = self._ai.plan(
                objective,
                provider=effective,
                prompt_template=prompt_template,
                template_variables=template_variables,
            )
            return ChatResult(
                success=True,
                response=str(response),
                response_type="plan",
                provider=response.provider or effective,
                model=response.model or "",
                conversation_id=self._conversation_id or "",
                latency_ms=response.latency_ms,
                metadata=dict(response.metadata) if response.metadata else {},
            )
        except Exception as exc:
            return ChatResult(
                success=False, response="", error=f"Planning failed: {exc}",
            )

    # ------------------------------------------------------------------
    # Reasoning
    # ------------------------------------------------------------------

    def send_reason(
        self,
        objective: str,
        *,
        provider: str | None = None,
        prompt_template: str | None = None,
        template_variables: dict[str, str] | None = None,
    ) -> ChatResult:
        """Reason about *objective* and return the rendered result."""
        if not isinstance(objective, str) or not objective.strip():
            return ChatResult(
                success=False, response="", error="Objective cannot be empty.",
            )

        effective = provider or self._provider

        try:
            response = self._ai.reason(
                objective,
                provider=effective,
                prompt_template=prompt_template,
                template_variables=template_variables,
            )
            return ChatResult(
                success=True,
                response=str(response),
                response_type="reason",
                provider=response.provider or effective,
                model=response.model or "",
                conversation_id=self._conversation_id or "",
                latency_ms=response.latency_ms,
                metadata=dict(response.metadata) if response.metadata else {},
            )
        except Exception as exc:
            return ChatResult(
                success=False, response="", error=f"Reasoning failed: {exc}",
            )

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def load_history(self) -> list[dict]:
        """Return the current conversation history as role/content dicts."""
        conv = self._ai.load_history(conversation_id=self._conversation_id)
        return conv

    def clear_conversation(self) -> None:
        self.new_conversation()

    # ------------------------------------------------------------------
    # EventBus integration
    # ------------------------------------------------------------------

    def subscribe_events(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        event_bus.subscribe("voice.transcript", self._on_transcript)

    def unsubscribe_events(self) -> None:
        if self._event_bus is None:
            return
        self._event_bus.unsubscribe("voice.transcript", self._on_transcript)
        self._event_bus = None

    def _on_transcript(self, text: str, **kwargs) -> None:
        if self.on_voice_input is not None:
            self.on_voice_input(text)
