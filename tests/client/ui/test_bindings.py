"""Tests for StateBinding."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.client.events import EventDispatcher
from app.client.state import ClientState
from app.client.ui.bindings import StateBinding
from app.client.ui.theme import ThemeManager


class TestStateBindingInit:
    def test_default_construction(self):
        state = ClientState()
        events = EventDispatcher()
        sb = StateBinding(state, events)
        assert sb._state is state
        assert sb._events is events
        assert sb._subscriptions == {}
        assert sb._bound_widgets == {}

    def test_with_theme(self):
        state = ClientState()
        events = EventDispatcher()
        theme = ThemeManager(events)
        sb = StateBinding(state, events, theme)
        assert sb._theme is theme


class TestStateBindingBind:
    def test_bind_calls_safe_update(self):
        state = ClientState()
        events = EventDispatcher()
        widget = MagicMock()
        sb = StateBinding(state, events)

        with patch.object(sb, "_safe_update") as mock_update:
            sb.bind(widget, "connection_status")
            assert "connection_status" in sb._subscriptions
            assert len(sb._subscriptions["connection_status"]) == 1
            assert "connection_status" in sb._bound_widgets
            mock_update.assert_called()

    def test_bind_text_emits_event(self):
        state = ClientState()
        events = EventDispatcher()
        widget = MagicMock()
        sb = StateBinding(state, events)

        sb.bind_text(widget, "connection_status")
        assert "connection_status" in sb._subscriptions
        assert len(sb._subscriptions["connection_status"]) == 1

    def test_bind_enabled(self):
        state = ClientState()
        events = EventDispatcher()
        widget = MagicMock()
        sb = StateBinding(state, events)

        sb.bind_enabled(widget, "connection_status")
        assert "connection_status" in sb._subscriptions

    def test_bind_enabled_inverted(self):
        state = ClientState()
        events = EventDispatcher()
        widget = MagicMock()
        sb = StateBinding(state, events)

        sb.bind_enabled(widget, "connection_status", invert=True)
        assert "connection_status" in sb._subscriptions

    def test_bind_visible(self):
        state = ClientState()
        events = EventDispatcher()
        widget = MagicMock()
        sb = StateBinding(state, events)

        sb.bind_visible(widget, "connection_status")
        assert "connection_status" in sb._subscriptions

    def test_bind_visible_inverted(self):
        state = ClientState()
        events = EventDispatcher()
        widget = MagicMock()
        sb = StateBinding(state, events)

        sb.bind_visible(widget, "connection_status", invert=True)
        assert "connection_status" in sb._subscriptions


class TestStateBindingUnbind:
    def test_unbind_all_clears(self):
        state = ClientState()
        events = EventDispatcher()
        widget = MagicMock()
        sb = StateBinding(state, events)

        sb.bind(widget, "connection_status")
        sb.bind_text(widget, "auth_state")
        assert len(sb._subscriptions) == 2

        sb.unbind_all()
        assert sb._subscriptions == {}
        assert sb._bound_widgets == {}

    def test_unbind_widget_removes_only_that_widget(self):
        state = ClientState()
        events = EventDispatcher()
        w1 = MagicMock()
        w2 = MagicMock()
        sb = StateBinding(state, events)

        sb.bind(w1, "connection_status")
        sb.bind(w2, "connection_status")
        assert len(sb._bound_widgets["connection_status"]) == 2

        sb.unbind_widget(w1)
        assert len(sb._bound_widgets["connection_status"]) == 1
        assert sb._bound_widgets["connection_status"][0][0] is w2

    def test_unbind_all_on_empty_is_safe(self):
        state = ClientState()
        events = EventDispatcher()
        sb = StateBinding(state, events)
        sb.unbind_all()
        assert sb._subscriptions == {}


class TestStateBindingStateChanges:
    def test_state_change_triggers_bind_handler(self):
        state = ClientState()
        events = EventDispatcher()
        widget = MagicMock()
        sb = StateBinding(state, events)

        sb.bind(widget, "connection_status")
        assert "connection_status" in sb._subscriptions
        assert len(sb._subscriptions["connection_status"]) == 1

        state.connection_status = "connected"
        assert state.connection_status == "connected"
