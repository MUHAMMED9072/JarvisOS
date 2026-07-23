"""Tests for VoiceManager orchestrator."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.core.event_bus import EventBus
from app.core.registry import ServiceRegistry
from app.cortex.models import CortexRequest
from app.skills.result import SkillResult
from app.voice.config import VoiceConfig
from app.voice.manager import VoiceManager


def _build_registry(
    *,
    enabled: bool = False,
    commands: tuple[str, ...] = (),
    speaker_enabled: bool = False,
    cortex_exc: BaseException | None = None,
    dispatcher_exc: BaseException | None = None,
    dispatcher_result: SkillResult | None = None,
):
    registry = ServiceRegistry()

    event_bus = EventBus()
    cortex = MagicMock()
    request = CortexRequest(
        text="hi",
        normalized="hi",
        intent="chat",
        confidence=0.9,
        brain="fast",
    )
    if cortex_exc is not None:
        cortex.process.side_effect = cortex_exc
    else:
        cortex.process.return_value = request

    dispatcher = MagicMock()
    if dispatcher_exc is not None:
        dispatcher.dispatch.side_effect = dispatcher_exc
    else:
        dispatcher.dispatch.return_value = (
            dispatcher_result
            if dispatcher_result is not None
            else SkillResult.ok(message="dispatched")
        )

    memory = MagicMock()

    registry.register("event_bus", event_bus)
    registry.register("cortex", cortex)
    registry.register("dispatcher", dispatcher)
    registry.register("memory", memory)
    registry.register(
        "voice_config",
        VoiceConfig(
            enabled=enabled,
            commands=commands,
            speaker_enabled=speaker_enabled,
        ),
    )
    return registry, cortex, dispatcher, event_bus, memory


class TestVoiceManagerLifecycle:
    def test_disabled_start_is_noop(self):
        registry, *_ = _build_registry(enabled=False)
        manager = VoiceManager(registry)
        manager.start()
        assert manager.is_running() is False

    def test_disabled_stop_is_noop(self):
        registry, *_ = _build_registry(enabled=False)
        manager = VoiceManager(registry)
        manager.stop()  # must not raise
        assert manager.is_running() is False

    def test_start_then_stop(self):
        registry, *_ = _build_registry(enabled=True)
        manager = VoiceManager(registry)
        manager.start()
        try:
            assert manager.is_running() is True
        finally:
            manager.stop()
        assert manager.is_running() is False

    def test_double_start_is_idempotent(self):
        registry, *_ = _build_registry(enabled=True)
        manager = VoiceManager(registry)
        manager.start()
        try:
            thread_a = manager._thread
            manager.start()
            assert manager._thread is thread_a
        finally:
            manager.stop()

    def test_double_stop_is_safe(self):
        registry, *_ = _build_registry(enabled=True)
        manager = VoiceManager(registry)
        manager.start()
        manager.stop()
        manager.stop()  # must not raise
        assert manager.is_running() is False


class TestVoiceManagerHandleTranscript:
    def test_empty_text_returns_failure(self):
        registry, *_ = _build_registry()
        manager = VoiceManager(registry)
        result = manager.handle_transcript("")
        assert result.success is False
        assert "empty" in result.message.lower()

    def test_none_text_returns_failure(self):
        registry, *_ = _build_registry()
        manager = VoiceManager(registry)
        result = manager.handle_transcript(None)  # type: ignore[arg-type]
        assert result.success is False

    def test_calls_cortex_then_dispatcher(self):
        registry, cortex, dispatcher, *_ = _build_registry()
        manager = VoiceManager(registry)
        result = manager.handle_transcript("hello jarvis")

        cortex.process.assert_called_once_with("hello jarvis", source="voice")
        dispatcher.dispatch.assert_called_once()
        assert result.success is True
        assert result.message == "dispatched"

    def test_does_not_call_memory_directly(self):
        """Memory writes are the dispatcher's job. Voice must not duplicate."""
        registry, cortex, dispatcher, _, memory = _build_registry()
        manager = VoiceManager(registry)
        manager.handle_transcript("hello")

        memory.remember.assert_not_called()
        memory.set_context.assert_not_called()

    def test_does_not_call_skill_manager_directly(self):
        """Voice must not reach into the skill manager."""
        skill_manager = MagicMock()
        registry, cortex, dispatcher, *_ = _build_registry()
        registry.register("skill_manager", skill_manager)
        manager = VoiceManager(registry)
        manager.handle_transcript("hello")

        skill_manager.get.assert_not_called()

    def test_cortex_error_returns_failure(self):
        registry, *_ = _build_registry(
            cortex_exc=RuntimeError("cortex broke"),
        )
        manager = VoiceManager(registry)
        result = manager.handle_transcript("hello")

        assert result.success is False
        assert "cortex" in result.message.lower()

    def test_dispatcher_error_returns_failure(self):
        registry, *_ = _build_registry(
            dispatcher_exc=RuntimeError("dispatcher broke"),
        )
        manager = VoiceManager(registry)
        result = manager.handle_transcript("hello")

        assert result.success is False
        assert "dispatcher" in result.message.lower()

    def test_whitespace_only_returns_failure(self):
        registry, cortex, dispatcher, *_ = _build_registry()
        manager = VoiceManager(registry)
        result = manager.handle_transcript("   \t  \n ")

        assert result.success is False
        cortex.process.assert_not_called()
        dispatcher.dispatch.assert_not_called()

    def test_publishes_transcript_event(self):
        registry, cortex, dispatcher, event_bus, _ = _build_registry()
        subscriber = MagicMock()
        event_bus.subscribe(VoiceManager.EVENT_TRANSCRIPT, subscriber)
        manager = VoiceManager(registry)

        manager.handle_transcript("hello")

        subscriber.assert_called_once_with("hello")

    def test_publishes_error_event_on_failure(self):
        registry, *_ = _build_registry(cortex_exc=RuntimeError("boom"))
        event_bus = registry.get("event_bus")
        subscriber = MagicMock()
        event_bus.subscribe(VoiceManager.EVENT_ERROR, subscriber)
        manager = VoiceManager(registry)

        manager.handle_transcript("hello")

        subscriber.assert_called()

    def test_speak_called_when_speaker_enabled(self):
        registry, *_ = _build_registry(speaker_enabled=True)
        manager = VoiceManager(registry)
        manager._speaker = MagicMock()

        manager.handle_transcript("hello")

        manager._speaker.speak.assert_called_once_with("dispatched")

    def test_speak_always_invoked_manager_does_not_gate(self):
        """The manager always hands the response to the Speaker stub.
        The Speaker stub itself decides whether to emit anything
        based on its own ``enabled`` flag — see test_speaker.py.
        """
        registry, *_ = _build_registry(speaker_enabled=False)
        manager = VoiceManager(registry)
        manager._speaker = MagicMock()

        manager.handle_transcript("hello")

        manager._speaker.speak.assert_called_once_with("dispatched")

    def test_speak_skipped_when_response_is_empty(self):
        """If the dispatcher returns no message, speak is not called."""
        registry, *_ = _build_registry(
            dispatcher_result=SkillResult.ok(message=""),
        )
        manager = VoiceManager(registry)
        manager._speaker = MagicMock()

        manager.handle_transcript("hello")

        manager._speaker.speak.assert_not_called()

    def test_command_short_circuits_cortex(self):
        registry, cortex, dispatcher, *_ = _build_registry(
            commands=("stop",),
            dispatcher_result=SkillResult.ok(message="ack"),
        )
        manager = VoiceManager(registry)
        manager._speaker = MagicMock()

        result = manager.handle_transcript("stop")

        cortex.process.assert_not_called()
        dispatcher.dispatch.assert_not_called()
        assert result.success is True
        assert "ack" in result.message.lower() or "stop" in result.message.lower()


class TestVoiceManagerSpeak:
    def test_speak_delegates_to_speaker(self):
        registry, *_ = _build_registry()
        manager = VoiceManager(registry)
        manager._speaker = MagicMock()
        manager.speak("hello there")
        manager._speaker.speak.assert_called_once_with("hello there")

    def test_speak_empty_string_is_noop(self):
        registry, *_ = _build_registry()
        manager = VoiceManager(registry)
        manager._speaker = MagicMock()
        manager.speak("")
        manager._speaker.speak.assert_not_called()


class TestVoiceManagerListenOnce:
    def test_listen_once_returns_transcript(self):
        registry, *_ = _build_registry()
        manager = VoiceManager(registry)
        recognizer = MagicMock()
        recognizer.listen_and_transcribe.return_value = "hi there"
        manager.set_recognizer(recognizer)

        result = manager.listen_once()

        assert result == "hi there"
        recognizer.listen_and_transcribe.assert_called_once()

    def test_listen_once_returns_none_when_no_speech(self):
        registry, *_ = _build_registry()
        manager = VoiceManager(registry)
        recognizer = MagicMock()
        recognizer.listen_and_transcribe.return_value = None
        manager.set_recognizer(recognizer)

        assert manager.listen_once() is None


class TestVoiceManagerLoop:
    def test_loop_runs_handle_transcript(self):
        """Background loop calls recognizer + handle_transcript."""
        registry, cortex, dispatcher, *_ = _build_registry(enabled=True)
        manager = VoiceManager(registry)
        recognizer = MagicMock()
        # First call returns a transcript, second call to stop the loop
        recognizer.listen_and_transcribe.side_effect = ["hi", None]
        manager.set_recognizer(recognizer)
        # Use a tiny pause so the test does not sleep long
        manager._config.loop_pause_seconds = 0.01
        manager._config.wake_word_enabled = False

        manager.start()
        # Wait for at least one iteration
        import time
        deadline = time.time() + 2.0
        while cortex.process.call_count == 0 and time.time() < deadline:
            time.sleep(0.05)

        manager.stop()

        assert cortex.process.call_count >= 1
        recognizer.listen_and_transcribe.assert_called()

    def test_loop_survives_exception(self):
        registry, cortex, dispatcher, *_ = _build_registry(enabled=True)
        manager = VoiceManager(registry)
        recognizer = MagicMock()
        # Always raise to stress the loop
        recognizer.listen_and_transcribe.side_effect = RuntimeError("loop oops")
        manager.set_recognizer(recognizer)
        manager._config.loop_pause_seconds = 0.01
        manager._config.wake_word_enabled = False

        manager.start()
        import time
        time.sleep(0.2)
        manager.stop()

        # Cortex must never have been called because the recognizer raised
        # before the transcript was produced.
        cortex.process.assert_not_called()


class TestVoiceManagerRegistryContract:
    def test_uses_registry_cortex(self):
        registry = ServiceRegistry()
        cortex = MagicMock()
        cortex.process.return_value = CortexRequest(text="x")
        registry.register("cortex", cortex)
        registry.register("dispatcher", MagicMock(dispatch=MagicMock(
            return_value=SkillResult.ok(message="ok"))))
        registry.register("voice_config", VoiceConfig())
        manager = VoiceManager(registry)
        manager.handle_transcript("x")
        cortex.process.assert_called_once()

    def test_uses_voice_config_from_registry(self):
        registry = ServiceRegistry()
        registry.register("voice_config", VoiceConfig(wake_word="custom"))
        manager = VoiceManager(registry)
        assert manager._config.wake_word == "custom"

    def test_falls_back_to_default_config(self):
        """No voice_config registered -> defaults."""
        registry = ServiceRegistry()
        manager = VoiceManager(registry)
        assert isinstance(manager._config, VoiceConfig)
        assert manager._config.enabled is False
