"""Speaker stub.

TTS is intentionally not implemented in P3-22. The interface exists
so that :class:`VoiceManager` can call ``speak()`` and a future TTS
backend can be plugged in without touching the orchestrator.

Current behaviour: log the text and publish a ``voice.response`` event
on the event bus, if one was injected. This is enough to wire the
GUI or external TTS in the meantime.
"""

from __future__ import annotations

from typing import Optional

from app.core.event_bus import EventBus
from app.core.logger import JarvisLogger
from app.voice.config import VoiceConfig


class Speaker:
    """Stub TTS interface."""

    EVENT_RESPONSE = "voice.response"

    def __init__(
        self,
        config: VoiceConfig | None = None,
        event_bus: Optional[EventBus] = None,
    ) -> None:
        self._config = config or VoiceConfig()
        self._event_bus = event_bus
        self._logger = JarvisLogger

    def set_event_bus(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus

    @property
    def enabled(self) -> bool:
        return self._config.speaker_enabled

    def speak(self, text: str) -> None:
        """Emit the response.

        Today this only logs and publishes an event. A real TTS
        backend (pyttsx3, edge-tts, piper) belongs in a subclass or a
        follow-up milestone.

        When ``speaker_enabled`` is False the call is a no-op so the
        orchestrator can leave TTS wiring in place without flooding
        the log / event bus during tests or headless runs.
        """
        if not text:
            return

        if not self.enabled:
            return

        self._logger.info("Speaker (stub): %s", text)

        if self._event_bus is not None:
            self._event_bus.publish(self.EVENT_RESPONSE, text)
