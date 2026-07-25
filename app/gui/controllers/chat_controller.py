from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from app.ai.providers.base import AIResponse
from app.cortex.handlers.ai_handler import AIHandler
from app.cortex.handlers.memory_handler import MemoryHandler
from app.skills.result import SkillResult

if TYPE_CHECKING:
    from app.core.event_bus import EventBus


class ChatController:
    """Orchestrates AI chat by coordinating AIHandler and MemoryHandler.

    The controller is provider-agnostic — the effective provider is
    determined at construction time by inspecting the available
    providers registered with the ``ai_router`` service.  Callers
    may override the provider per-message via ``send_message(...,
    provider=...)``.
    """

    def __init__(self, registry) -> None:
        self.registry = registry
        self._ai = AIHandler(registry)
        self._memory = MemoryHandler(registry)
        self._provider = self._resolve_provider()
        self._event_bus: EventBus | None = None

        # Optional callback set by the page to receive voice input.
        self.on_voice_input: Callable[[str], None] | None = None

    # ------------------------------------------------------------------
    # Provider resolution
    # ------------------------------------------------------------------

    def _resolve_provider(self) -> str:
        """Return the best available provider name.

        Priority:
          1. ``Config`` attribute (if one exists in future).
          2. The first provider registered with ``ai_router`` that is
             not a known-stub provider.
          3. ``"ollama"`` as the final fallback (the only provider
             guaranteed to work out of the box).
        """
        router = self.registry.get("ai_router")
        available = list(router.providers.keys())

        if "ollama" in available:
            return "ollama"

        if available:
            return available[0]

        return "ollama"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def send_message(
        self,
        text: str,
        *,
        provider: str | None = None,
    ) -> SkillResult:
        """Send a user message and return the assistant response.

        The current conversation context (last N session messages) is
        automatically prepended so the AI has continuity.
        """
        if not isinstance(text, str) or not text.strip():
            return SkillResult.fail(message="Message cannot be empty.")

        effective = provider or self._provider

        try:
            context = self._memory.get_session_context()
            messages = context.get("messages", [])
            recent = "\n".join(
                f"{m['role']}: {m['content']}"
                for m in messages[-6:]
            )
            prompt = (
                f"Previous conversation:\n{recent}\n\n"
                f"User: {text}\nAssistant:"
            )
            response = self._ai.chat(prompt, provider=effective)
            return SkillResult.ok(message=response)
        except Exception as exc:
            return SkillResult.fail(
                message=f"AI request failed: {exc}",
            )

    def load_history(self) -> list[dict]:
        """Return the current session conversation history."""
        context = self._memory.get_session_context()
        return context.get("messages", [])

    def clear_conversation(self) -> None:
        """Clear the in-memory session conversation."""
        memory = self.registry.get("memory")
        memory.clear()

    # ------------------------------------------------------------------
    # EventBus integration (lifecycle managed by page)
    # ------------------------------------------------------------------

    def subscribe_events(self, event_bus: EventBus) -> None:
        """Subscribe to voice transcript events for voice-to-chat."""
        self._event_bus = event_bus
        event_bus.subscribe("voice.transcript", self._on_transcript)

    def unsubscribe_events(self) -> None:
        """Remove all event subscriptions."""
        if self._event_bus is None:
            return
        self._event_bus.unsubscribe("voice.transcript", self._on_transcript)
        self._event_bus = None

    def _on_transcript(self, text: str, **kwargs) -> None:
        if self.on_voice_input is not None:
            self.on_voice_input(text)
