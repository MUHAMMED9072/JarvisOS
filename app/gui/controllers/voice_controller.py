from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from app.voice.config import VoiceConfig

if TYPE_CHECKING:
    from app.core.event_bus import EventBus


class VoiceController:
    """Orchestrates the voice control page.

    Wraps the registered ``voice_manager`` service and listens to voice
    events from the EventBus for live transcript / status display.
    """

    def __init__(self, registry) -> None:
        self.registry = registry
        self._event_bus: EventBus | None = None
        self._config: VoiceConfig | None = None

        # Callbacks the page can set to receive live updates.
        self.on_transcript: Callable[[str], None] | None = None
        self.on_response: Callable[[str], None] | None = None
        self.on_error: Callable[[str], None] | None = None
        self.on_wake: Callable[[], None] | None = None
        self.on_running_changed: Callable[[bool], None] | None = None

    # ------------------------------------------------------------------
    # Voice manager access
    # ------------------------------------------------------------------

    def _manager(self):
        return self.registry.get("voice_manager")

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def is_running(self) -> bool:
        try:
            return self._manager().is_running()
        except KeyError:
            return False

    @property
    def config(self) -> VoiceConfig:
        if self._config is None:
            self._config = (
                self.registry.get("voice_config")
                if self.registry.exists("voice_config")
                else VoiceConfig()
            )
        return self._config

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        try:
            self._manager().start()
        except KeyError:
            pass
        if self.on_running_changed:
            self.on_running_changed(True)

    def stop(self) -> None:
        try:
            self._manager().stop()
        except KeyError:
            pass
        if self.on_running_changed:
            self.on_running_changed(False)

    def toggle_running(self) -> bool:
        if self.is_running():
            self.stop()
            return False
        self.start()
        return True

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def listen_once(self) -> str | None:
        try:
            return self._manager().listen_once()
        except KeyError:
            return None

    def speak(self, text: str) -> None:
        if not text.strip():
            return
        try:
            self._manager().speak(text)
        except KeyError:
            pass

    # ------------------------------------------------------------------
    # EventBus integration
    # ------------------------------------------------------------------

    def subscribe_events(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        event_bus.subscribe("voice.transcript", self._on_transcript)
        event_bus.subscribe("voice.response", self._on_response)
        event_bus.subscribe("voice.error", self._on_voice_error)
        event_bus.subscribe("voice.wake", self._on_wake)

    def unsubscribe_events(self) -> None:
        bus = self._event_bus
        if bus is None:
            return
        bus.unsubscribe("voice.transcript", self._on_transcript)
        bus.unsubscribe("voice.response", self._on_response)
        bus.unsubscribe("voice.error", self._on_voice_error)
        bus.unsubscribe("voice.wake", self._on_wake)
        self._event_bus = None

    def _on_transcript(self, text: str, **kwargs) -> None:
        if self.on_transcript is not None:
            self.on_transcript(text)

    def _on_response(self, text: str, **kwargs) -> None:
        if self.on_response is not None:
            self.on_response(text)

    def _on_voice_error(self, error: str, **kwargs) -> None:
        if self.on_error is not None:
            self.on_error(error)

    def _on_wake(self, **kwargs) -> None:
        if self.on_wake is not None:
            self.on_wake()
