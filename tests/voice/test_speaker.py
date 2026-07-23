"""Tests for Speaker stub."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.core.event_bus import EventBus
from app.voice.config import VoiceConfig
from app.voice.speaker import Speaker


class TestSpeaker:
    def test_disabled_by_default(self):
        speaker = Speaker(VoiceConfig())
        assert speaker.enabled is False

    def test_speak_logs_text(self):
        speaker = Speaker(VoiceConfig(speaker_enabled=True))
        speaker._logger = MagicMock()
        speaker.speak("hello")
        speaker._logger.info.assert_called()

    def test_speak_publishes_event_when_event_bus_present(self):
        bus = EventBus()
        subscriber = MagicMock()
        bus.subscribe(Speaker.EVENT_RESPONSE, subscriber)

        speaker = Speaker(VoiceConfig(speaker_enabled=True), event_bus=bus)
        speaker.speak("hi there")

        subscriber.assert_called_once_with("hi there")

    def test_speak_no_event_bus_does_not_raise(self):
        speaker = Speaker(VoiceConfig(speaker_enabled=True))
        # Should not raise even without an event bus.
        speaker.speak("hi there")

    def test_speak_empty_text_is_noop(self):
        speaker = Speaker(VoiceConfig(speaker_enabled=True))
        speaker._logger = MagicMock()
        bus = EventBus()
        subscriber = MagicMock()
        bus.subscribe(Speaker.EVENT_RESPONSE, subscriber)
        speaker.set_event_bus(bus)

        speaker.speak("")

        speaker._logger.info.assert_not_called()
        subscriber.assert_not_called()

    def test_set_event_bus(self):
        speaker = Speaker(VoiceConfig())
        bus = EventBus()
        speaker.set_event_bus(bus)
        assert speaker._event_bus is bus
