from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.gui.controllers.voice_controller import VoiceController
from app.voice.config import VoiceConfig


class TestVoiceController:
    @pytest.fixture
    def registry(self):
        r = MagicMock()
        return r

    @pytest.fixture
    def controller(self, registry):
        return VoiceController(registry)

    @staticmethod
    def _make_manager(running: bool = False):
        mgr = MagicMock()
        mgr.is_running.return_value = running
        return mgr

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def test_is_running_false_when_no_manager(self, controller):
        controller.registry.get.side_effect = KeyError("no voice_manager")
        assert controller.is_running() is False

    def test_is_running_true(self, controller):
        controller.registry.get.return_value = self._make_manager(running=True)
        assert controller.is_running() is True

    def test_is_running_false(self, controller):
        controller.registry.get.return_value = self._make_manager(running=False)
        assert controller.is_running() is False

    def test_config_reads_voice_config(self, controller):
        cfg = VoiceConfig()
        controller.registry.exists.return_value = True
        controller.registry.get.return_value = cfg
        assert controller.config is cfg

    def test_config_fallback_when_missing(self, controller):
        controller.registry.exists.return_value = False
        assert isinstance(controller.config, VoiceConfig)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def test_start_calls_manager_start(self, controller):
        mgr = self._make_manager()
        controller.registry.get.return_value = mgr
        controller.start()
        mgr.start.assert_called_once()

    def test_start_no_manager(self, controller):
        controller.registry.get.side_effect = KeyError("no voice_manager")
        controller.start()

    def test_start_fires_callback(self, controller):
        cb = MagicMock()
        controller.on_running_changed = cb
        mgr = self._make_manager()
        controller.registry.get.return_value = mgr
        controller.start()
        cb.assert_called_once_with(True)

    def test_stop_calls_manager_stop(self, controller):
        mgr = self._make_manager()
        controller.registry.get.return_value = mgr
        controller.stop()
        mgr.stop.assert_called_once()

    def test_stop_no_manager(self, controller):
        controller.registry.get.side_effect = KeyError("no voice_manager")
        controller.stop()

    def test_stop_fires_callback(self, controller):
        cb = MagicMock()
        controller.on_running_changed = cb
        mgr = self._make_manager()
        controller.registry.get.return_value = mgr
        controller.stop()
        cb.assert_called_once_with(False)

    def test_toggle_running_when_running(self, controller):
        mgr = self._make_manager(running=True)
        controller.registry.get.return_value = mgr
        result = controller.toggle_running()
        assert result is False
        mgr.stop.assert_called_once()

    def test_toggle_running_when_stopped(self, controller):
        mgr = self._make_manager(running=False)
        controller.registry.get.return_value = mgr
        result = controller.toggle_running()
        assert result is True
        mgr.start.assert_called_once()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def test_listen_once_returns_text(self, controller):
        mgr = self._make_manager()
        mgr.listen_once.return_value = "hello"
        controller.registry.get.return_value = mgr
        assert controller.listen_once() == "hello"

    def test_listen_once_no_manager(self, controller):
        controller.registry.get.side_effect = KeyError("no voice_manager")
        assert controller.listen_once() is None

    def test_speak_calls_manager_speak(self, controller):
        mgr = self._make_manager()
        controller.registry.get.return_value = mgr
        controller.speak("hello world")
        mgr.speak.assert_called_once_with("hello world")

    def test_speak_empty_string(self, controller):
        mgr = self._make_manager()
        controller.registry.get.return_value = mgr
        controller.speak("")
        mgr.speak.assert_not_called()

    def test_speak_whitespace(self, controller):
        mgr = self._make_manager()
        controller.registry.get.return_value = mgr
        controller.speak("   ")
        mgr.speak.assert_not_called()

    def test_speak_no_manager(self, controller):
        controller.registry.get.side_effect = KeyError("no voice_manager")
        controller.speak("hello")

    # ------------------------------------------------------------------
    # EventBus integration
    # ------------------------------------------------------------------

    def test_subscribe_events_registers_callbacks(self, controller):
        bus = MagicMock()
        controller.subscribe_events(bus)
        assert bus.subscribe.call_count == 4

    def test_unsubscribe_events_removes_callbacks(self, controller):
        bus = MagicMock()
        controller.subscribe_events(bus)
        controller.unsubscribe_events()
        assert bus.unsubscribe.call_count == 4
        assert controller._event_bus is None

    def test_unsubscribe_events_no_bus(self, controller):
        controller.unsubscribe_events()

    def test_on_transcript_calls_callback(self, controller):
        cb = MagicMock()
        controller.on_transcript = cb
        controller._on_transcript("hello")
        cb.assert_called_once_with("hello")

    def test_on_transcript_no_callback(self, controller):
        controller._on_transcript("hello")

    def test_on_response_calls_callback(self, controller):
        cb = MagicMock()
        controller.on_response = cb
        controller._on_response("response")
        cb.assert_called_once_with("response")

    def test_on_response_no_callback(self, controller):
        controller._on_response("response")

    def test_on_error_calls_callback(self, controller):
        cb = MagicMock()
        controller.on_error = cb
        controller._on_voice_error("error msg")
        cb.assert_called_once_with("error msg")

    def test_on_error_no_callback(self, controller):
        controller._on_voice_error("error msg")

    def test_on_wake_calls_callback(self, controller):
        cb = MagicMock()
        controller.on_wake = cb
        controller._on_wake()
        cb.assert_called_once()

    def test_on_wake_no_callback(self, controller):
        controller._on_wake()
