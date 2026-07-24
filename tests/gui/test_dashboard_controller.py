from __future__ import annotations

from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from app.gui.controllers.dashboard_controller import (
    DashboardController,
    QuickActionResult,
    ServiceStatus,
)


class TestDashboardController:
    @pytest.fixture
    def registry(self):
        r = MagicMock()
        r.list_services.return_value = ["event_bus", "memory", "ai_router"]
        r.get.side_effect = lambda name: MagicMock() if name in (
            "event_bus", "memory", "ai_router",
        ) else None
        return r

    @pytest.fixture
    def controller(self, registry):
        with patch(
            "app.gui.controllers.dashboard_controller.AIHandler",
        ), patch(
            "app.gui.controllers.dashboard_controller.AutomationHandler",
        ), patch(
            "app.gui.controllers.dashboard_controller.MemoryHandler",
        ):
            ctrl = DashboardController(registry)
            return ctrl

    # ------------------------------------------------------------------
    # Service status
    # ------------------------------------------------------------------

    def test_get_service_statuses(self, controller):
        statuses = controller.get_service_statuses()
        assert isinstance(statuses, list)
        assert len(statuses) == 3
        assert all(isinstance(s, ServiceStatus) for s in statuses)
        names = [s.name for s in statuses]
        assert "event_bus" in names
        assert "memory" in names
        assert "ai_router" in names

    def test_get_service_statuses_online(self, controller):
        for s in controller.get_service_statuses():
            assert s.online is True

    def test_get_service_statuses_missing_service(self, controller):
        controller.registry.get.side_effect = KeyError("not found")
        statuses = controller.get_service_statuses()
        for s in statuses:
            assert s.online is False

    # ------------------------------------------------------------------
    # Voice toggle
    # ------------------------------------------------------------------

    def test_voice_defaults_off(self, controller):
        assert controller.get_voice_status() is False

    def test_toggle_voice_turns_on(self, controller):
        result = controller.toggle_voice()
        assert result is True
        assert controller.get_voice_status() is True

    def test_toggle_voice_turns_off(self, controller):
        controller.toggle_voice()
        result = controller.toggle_voice()
        assert result is False
        assert controller.get_voice_status() is False

    def test_toggle_voice_adds_activity(self, controller):
        controller.toggle_voice()
        log = controller.get_activity_log()
        assert len(log) == 1
        assert "enabled" in log[0].summary

    # ------------------------------------------------------------------
    # Quick ask
    # ------------------------------------------------------------------

    def test_quick_ask_empty(self, controller):
        result = controller.quick_ask("")
        assert result.success is False

    def test_quick_ask_whitespace(self, controller):
        result = controller.quick_ask("   ")
        assert result.success is False

    def test_quick_ask_success(self, controller):
        controller._ai = MagicMock()
        controller._ai.chat.return_value = "Answer"
        result = controller.quick_ask("What is Python?")
        assert result.success is True
        assert result.message == "Answer"

    def test_quick_ask_calls_ai_chat(self, controller):
        controller._ai = MagicMock()
        controller.quick_ask("question")
        controller._ai.chat.assert_called_once_with("question")

    def test_quick_ask_adds_activity(self, controller):
        controller._ai = MagicMock()
        controller.quick_ask("question")
        log = controller.get_activity_log()
        assert any("AI quick-ask" in e.summary for e in log)

    def test_quick_ask_error(self, controller):
        controller._ai = MagicMock()
        controller._ai.chat.side_effect = RuntimeError("fail")
        result = controller.quick_ask("question")
        assert result.success is False
        assert "fail" in result.message

    # ------------------------------------------------------------------
    # Memory search
    # ------------------------------------------------------------------

    def test_search_memory_empty(self, controller):
        result = controller.search_memory("")
        assert result.success is False

    def test_search_memory_success(self, controller):
        controller._memory = MagicMock()
        controller._memory.recall.return_value = "found it"
        result = controller.search_memory("something")
        assert result.success is True
        assert result.message == "found it"

    def test_search_memory_adds_activity(self, controller):
        controller._memory = MagicMock()
        controller.search_memory("query")
        log = controller.get_activity_log()
        assert any("Memory search" in e.summary for e in log)

    # ------------------------------------------------------------------
    # Open app
    # ------------------------------------------------------------------

    def test_open_app_success(self, controller):
        controller._automation = MagicMock()
        controller._automation.open_application.return_value = "notepad opened"
        result = controller.open_app("notepad")
        assert result.success is True
        assert "notepad opened" in result.message

    def test_open_app_adds_activity(self, controller):
        controller._automation = MagicMock()
        controller.open_app("calc")
        log = controller.get_activity_log()
        assert any("Open app" in e.summary for e in log)

    def test_open_app_error(self, controller):
        controller._automation = MagicMock()
        controller._automation.open_application.side_effect = FileNotFoundError("not found")
        result = controller.open_app("unknown")
        assert result.success is False

    # ------------------------------------------------------------------
    # Activity log
    # ------------------------------------------------------------------

    def test_activity_log_type(self, controller):
        controller._add_activity("test activity")
        log = controller.get_activity_log()
        assert len(log) == 1
        assert log[0].summary == "test activity"
        assert hasattr(log[0], "timestamp")
        assert hasattr(log[0], "summary")

    def test_activity_log_empty_initially(self, controller):
        assert controller.get_activity_log() == []

    def test_activity_log_multiple_entries(self, controller):
        for i in range(5):
            controller._add_activity(f"entry {i}")
        assert len(controller.get_activity_log()) == 5

    # ------------------------------------------------------------------
    # EventBus integration
    # ------------------------------------------------------------------

    def test_subscribe_events_registers_callbacks(self, controller):
        bus = MagicMock()
        controller.subscribe_events(bus)
        assert bus.subscribe.call_count == 4

    def test_subscribe_events_subscribes_transcript(self, controller):
        bus = MagicMock()
        controller.subscribe_events(bus)
        bus.subscribe.assert_any_call("voice.transcript", controller._on_transcript)

    def test_subscribe_events_subscribes_wake(self, controller):
        bus = MagicMock()
        controller.subscribe_events(bus)
        bus.subscribe.assert_any_call("voice.wake", controller._on_wake)

    def test_subscribe_events_subscribes_response(self, controller):
        bus = MagicMock()
        controller.subscribe_events(bus)
        bus.subscribe.assert_any_call("voice.response", controller._on_response)

    def test_subscribe_events_subscribes_error(self, controller):
        bus = MagicMock()
        controller.subscribe_events(bus)
        bus.subscribe.assert_any_call("voice.error", controller._on_voice_error)

    def test_unsubscribe_events_removes_callbacks(self, controller):
        bus = MagicMock()
        controller.subscribe_events(bus)
        controller.unsubscribe_events()
        assert bus.unsubscribe.call_count == 4
        assert controller._event_bus is None

    def test_unsubscribe_events_no_bus(self, controller):
        controller.unsubscribe_events()

    def test_on_transcript_adds_activity(self, controller):
        bus = MagicMock()
        controller.subscribe_events(bus)
        controller._on_transcript("hello world")
        log = controller.get_activity_log()
        assert any("You said" in e.summary for e in log)
        assert any("hello world" in e.summary for e in log)

    def test_on_wake_adds_activity(self, controller):
        controller._on_wake()
        log = controller.get_activity_log()
        assert any("Wake word" in e.summary for e in log)

    def test_on_response_adds_activity(self, controller):
        controller._on_response("Sure thing")
        log = controller.get_activity_log()
        assert any("Assistant" in e.summary for e in log)

    def test_on_voice_error_adds_activity(self, controller):
        controller._on_voice_error("timeout")
        log = controller.get_activity_log()
        assert any("Voice error" in e.summary for e in log)

    def test_toggle_voice_publishes_event(self, controller):
        bus = MagicMock()
        controller.subscribe_events(bus)
        controller.toggle_voice()
        bus.publish.assert_called_once_with(
            "voice.toggle", enabled=True,
        )

    def test_toggle_voice_no_bus_still_toggles(self, controller):
        result = controller.toggle_voice()
        assert result is True
