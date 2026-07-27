"""Tests for Navigator and NavigationHistory."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.client.events import EventDispatcher
from app.client.ui.navigation import NavigationHistory, Navigator


class FakeView:
    def __init__(self, **kwargs):
        self._shown = False
        self._hidden = False
        self._refreshed = False
        self._destroyed = False

    def grid(self, **kwargs):
        pass
    def grid_remove(self):
        pass
    def on_load(self):
        pass
    def on_show(self, **kwargs):
        self._shown = True
    def on_hide(self):
        self._hidden = True
    def on_refresh(self):
        self._refreshed = True
    def on_destroy(self):
        self._destroyed = True


class TestNavigationHistory:
    def test_push_and_current(self):
        h = NavigationHistory()
        assert h.current is None
        h.push("a")
        assert h.current == "a"
        h.push("b")
        assert h.current == "b"

    def test_can_go_back(self):
        h = NavigationHistory()
        assert h.can_go_back() is False
        h.push("a")
        assert h.can_go_back() is True

    def test_can_go_forward(self):
        h = NavigationHistory()
        assert h.can_go_forward() is False
        h.push("a")
        h._forward.append("b")
        assert h.can_go_forward() is True

    def test_go_back(self):
        h = NavigationHistory()
        h.push("a")
        result = h.go_back()
        assert result == "a"
        assert h.current is None

    def test_go_forward(self):
        h = NavigationHistory()
        h._forward.append("b")
        result = h.go_forward()
        assert result == "b"
        assert h.current is None

    def test_go_back_empty(self):
        h = NavigationHistory()
        assert h.go_back() is None

    def test_go_forward_empty(self):
        h = NavigationHistory()
        assert h.go_forward() is None

    def test_clear(self):
        h = NavigationHistory()
        h.push("a")
        h.push("b")
        h.clear()
        assert h.current is None
        assert h.can_go_back() is False
        assert h.can_go_forward() is False

    def test_maxlen(self):
        h = NavigationHistory(maxlen=3)
        for i in range(5):
            h.push(str(i))
        assert h.length <= 3

    def test_forward_cleared_on_push(self):
        h = NavigationHistory()
        h.push("a")
        h.push("b")
        h._forward.append("a")
        assert h.can_go_forward() is True
        h.push("c")
        assert h.can_go_forward() is False

    @property
    def length(self):
        return len(self._back)


class TestNavigatorInit:
    def test_default_construction(self):
        nav = Navigator()
        assert nav.active_view is None
        assert nav.can_go_back is False
        assert nav.can_go_forward is False
        assert len(nav) == 0

    def test_with_events(self):
        events = EventDispatcher()
        nav = Navigator(events=events)
        assert nav._events is events


class TestNavigatorRegister:
    def test_register_view(self):
        nav = Navigator()
        nav.register_view("test", FakeView, title="Test View", icon="🔬")
        assert len(nav) == 1
        assert nav.get_title("test") == "Test View"

    def test_register_publishes_event(self):
        events = EventDispatcher()
        nav = Navigator(events=events)
        received = []

        def handler(event, **data):
            received.append({"event": event, **data})

        events.subscribe("navigation.view.registered", handler)
        nav.register_view("test", FakeView)
        assert len(received) == 1

    def test_unregister_view(self):
        nav = Navigator()
        nav.register_view("test", FakeView)
        assert len(nav) == 1
        nav.unregister_view("test")
        assert len(nav) == 0

    def test_registered_views(self):
        nav = Navigator()
        nav.register_view("a", FakeView, title="A", icon="🅰")
        nav.register_view("b", FakeView, title="B", icon="🅱")
        views = nav.registered_views()
        assert len(views) == 2
        titles = {v["id"] for v in views}
        assert "a" in titles
        assert "b" in titles


class TestNavigatorNavigate:
    def test_navigate_unregistered_returns_false(self):
        nav = Navigator()
        result = nav.navigate("nonexistent")
        assert result is False

    def test_navigate_sets_active(self):
        container = MagicMock()
        container.winfo_children.return_value = []
        nav = Navigator()
        nav.set_container(container)
        nav.register_view("test", FakeView)
        result = nav.navigate("test")
        assert result is True
        assert nav.active_view == "test"

    def test_navigate_triggers_on_show(self):
        container = MagicMock()
        container.winfo_children.return_value = []
        nav = Navigator()
        nav.set_container(container)
        nav.register_view("test", FakeView)
        nav.navigate("test")
        instance = nav.get_view("test")
        assert instance._shown is True

    def test_navigate_hides_previous(self):
        container = MagicMock()
        container.winfo_children.return_value = []
        nav = Navigator()
        nav.set_container(container)
        nav.register_view("a", FakeView)
        nav.register_view("b", FakeView)
        nav.navigate("a")
        nav.navigate("b")
        view_a = nav.get_view("a")
        assert view_a._hidden is True

    def test_navigate_publishes_event(self):
        events = EventDispatcher()
        container = MagicMock()
        container.winfo_children.return_value = []
        nav = Navigator(events=events)
        nav.set_container(container)
        nav.register_view("test", FakeView)
        received = []

        def handler(event, **data):
            received.append({"event": event, **data})

        events.subscribe("navigation.changed", handler)
        nav.navigate("test")
        assert len(received) >= 1


class TestNavigatorBackForward:
    def test_go_back_works(self):
        container = MagicMock()
        container.winfo_children.return_value = []
        nav = Navigator()
        nav.set_container(container)
        nav.register_view("a", FakeView)
        nav.register_view("b", FakeView)
        nav.navigate("a")
        nav.navigate("b")
        result = nav.go_back()
        assert result is True
        assert nav.active_view == "a"

    def test_go_back_no_history(self):
        nav = Navigator()
        result = nav.go_back()
        assert result is False

    def test_go_forward_works(self):
        container = MagicMock()
        container.winfo_children.return_value = []
        nav = Navigator()
        nav.set_container(container)
        nav.register_view("a", FakeView)
        nav.register_view("b", FakeView)
        nav.navigate("a")
        nav.navigate("b")
        nav.go_back()
        result = nav.go_forward()
        assert result is True
        assert nav.active_view == "b"

    def test_go_forward_no_history(self):
        nav = Navigator()
        result = nav.go_forward()
        assert result is False


class TestNavigatorDestroy:
    def test_destroy_all_clears(self):
        nav = Navigator()
        nav.register_view("a", FakeView)
        nav.register_view("b", FakeView)
        nav.destroy_all()
        assert len(nav) == 0
        assert nav.active_view is None

    def test_destroy_all_calls_on_destroy(self):
        nav = Navigator()
        nav.register_view("a", FakeView)
        nav.navigate("a")
        instance = nav.get_view("a")
        assert instance is not None
        nav.destroy_all()
        assert instance._destroyed is True

    def test_refresh_active(self):
        container = MagicMock()
        container.winfo_children.return_value = []
        nav = Navigator()
        nav.set_container(container)
        nav.register_view("test", FakeView)
        nav.navigate("test")
        instance = nav.get_view("test")
        nav.refresh_active()
        assert instance._refreshed is True


class TestNavigatorActiveInstance:
    def test_active_instance_returns_none_when_no_active(self):
        nav = Navigator()
        assert nav.active_instance is None

    def test_active_instance_returns_view(self):
        container = MagicMock()
        container.winfo_children.return_value = []
        nav = Navigator()
        nav.set_container(container)
        nav.register_view("test", FakeView)
        nav.navigate("test")
        assert nav.active_instance is not None
