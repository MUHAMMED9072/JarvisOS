from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.cortex.handlers.ai_handler import AIHandler
from app.cortex.handlers.automation_handler import AutomationHandler
from app.cortex.handlers.memory_handler import MemoryHandler

if TYPE_CHECKING:
    from app.core.event_bus import EventBus


@dataclass
class ServiceStatus:
    name: str
    online: bool
    detail: str = ""


@dataclass
class ActivityEntry:
    timestamp: float
    summary: str


@dataclass
class QuickActionResult:
    success: bool
    message: str


class DashboardController:
    """Orchestrates the live dashboard by aggregating service status,
    executing quick-action commands, and maintaining an activity log."""

    def __init__(self, registry) -> None:
        self.registry = registry
        self._ai: AIHandler | None = None
        self._automation: AutomationHandler | None = None
        self._memory: MemoryHandler | None = None
        self._activity: list[ActivityEntry] = []
        self._voice_on = False
        self._event_bus: EventBus | None = None

    # ------------------------------------------------------------------
    # Service status
    # ------------------------------------------------------------------

    def get_service_statuses(self) -> list[ServiceStatus]:
        statuses: list[ServiceStatus] = []

        for svc in self.registry.list_services():
            try:
                instance = self.registry.get(svc)
                statuses.append(
                    ServiceStatus(
                        name=svc,
                        online=instance is not None,
                        detail=type(instance).__name__,
                    )
                )
            except KeyError:
                statuses.append(ServiceStatus(name=svc, online=False))

        return statuses

    def get_voice_status(self) -> bool:
        return self._voice_on

    def toggle_voice(self) -> bool:
        self._voice_on = not self._voice_on
        summary = f"Voice {'enabled' if self._voice_on else 'disabled'}"
        self._add_activity(summary)
        self._publish("voice.toggle", enabled=self._voice_on)
        return self._voice_on

    # ------------------------------------------------------------------
    # Quick actions
    # ------------------------------------------------------------------

    def quick_ask(self, question: str) -> QuickActionResult:
        if not question.strip():
            return QuickActionResult(success=False, message="Question is empty.")
        try:
            self._ensure_ai()
            response = self._ai.chat(question)
            self._add_activity(f"AI quick-ask: {question[:50]}")
            return QuickActionResult(success=True, message=response)
        except Exception as exc:
            return QuickActionResult(success=False, message=str(exc))

    def search_memory(self, query: str) -> QuickActionResult:
        if not query.strip():
            return QuickActionResult(success=False, message="Query is empty.")
        try:
            self._ensure_memory()
            result = self._memory.recall(query)
            self._add_activity(f"Memory search: {query[:50]}")
            return QuickActionResult(success=True, message=result)
        except Exception as exc:
            return QuickActionResult(success=False, message=str(exc))

    def open_app(self, app_name: str) -> QuickActionResult:
        try:
            self._ensure_automation()
            result = self._automation.open_application(app_name)
            self._add_activity(f"Open app: {app_name}")
            return QuickActionResult(success=True, message=result)
        except Exception as exc:
            return QuickActionResult(success=False, message=str(exc))

    # ------------------------------------------------------------------
    # Activity log
    # ------------------------------------------------------------------

    def get_activity_log(self) -> list[ActivityEntry]:
        return list(self._activity)

    def _add_activity(self, summary: str) -> None:
        self._activity.append(ActivityEntry(timestamp=time.time(), summary=summary))

    # ------------------------------------------------------------------
    # Lazy handler creation
    # ------------------------------------------------------------------

    def _ensure_ai(self) -> None:
        if self._ai is None:
            self._ai = AIHandler(self.registry)

    def _ensure_automation(self) -> None:
        if self._automation is None:
            self._automation = AutomationHandler(self.registry)

    def _ensure_memory(self) -> None:
        if self._memory is None:
            self._memory = MemoryHandler(self.registry)

    # ------------------------------------------------------------------
    # EventBus integration (lifecycle managed by page)
    # ------------------------------------------------------------------

    def subscribe_events(self, event_bus: EventBus) -> None:
        """Subscribe to voice events for live activity logging."""
        self._event_bus = event_bus
        event_bus.subscribe("voice.transcript", self._on_transcript)
        event_bus.subscribe("voice.wake", self._on_wake)
        event_bus.subscribe("voice.response", self._on_response)
        event_bus.subscribe("voice.error", self._on_voice_error)

    def unsubscribe_events(self) -> None:
        """Remove all event subscriptions."""
        bus = self._event_bus
        if bus is None:
            return
        bus.unsubscribe("voice.transcript", self._on_transcript)
        bus.unsubscribe("voice.wake", self._on_wake)
        bus.unsubscribe("voice.response", self._on_response)
        bus.unsubscribe("voice.error", self._on_voice_error)
        self._event_bus = None

    # ------------------------------------------------------------------
    # Event callbacks
    # ------------------------------------------------------------------

    def _on_transcript(self, text: str, **kwargs) -> None:
        self._add_activity(f"You said: {text[:80]}")

    def _on_wake(self, **kwargs) -> None:
        self._add_activity("Wake word detected")

    def _on_response(self, text: str, **kwargs) -> None:
        self._add_activity(f"Assistant: {text[:80]}")

    def _on_voice_error(self, error: str, **kwargs) -> None:
        self._add_activity(f"Voice error: {error[:80]}")

    # ------------------------------------------------------------------
    # Event publishing
    # ------------------------------------------------------------------

    def _publish(self, event: str, **kwargs) -> None:
        if self._event_bus is not None:
            self._event_bus.publish(event, **kwargs)
