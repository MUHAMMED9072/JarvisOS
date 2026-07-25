from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.core.event_bus import EventBus


class TestEventBus:
    @pytest.fixture
    def bus(self):
        return EventBus()

    # ------------------------------------------------------------------
    # Subscribe / Publish
    # ------------------------------------------------------------------

    def test_subscribe_and_publish(self, bus):
        cb = MagicMock()
        bus.subscribe("test.event", cb)
        bus.publish("test.event")
        cb.assert_called_once()

    def test_publish_with_args(self, bus):
        cb = MagicMock()
        bus.subscribe("evt", cb)
        bus.publish("evt", "arg1", key="val")
        cb.assert_called_once_with("arg1", key="val")

    def test_publish_no_subscribers(self, bus):
        bus.publish("nonexistent")

    def test_multiple_subscribers_same_event(self, bus):
        cb1 = MagicMock()
        cb2 = MagicMock()
        bus.subscribe("evt", cb1)
        bus.subscribe("evt", cb2)
        bus.publish("evt", "data")
        cb1.assert_called_once_with("data")
        cb2.assert_called_once_with("data")

    def test_multiple_events_isolated(self, bus):
        cb_a = MagicMock()
        cb_b = MagicMock()
        bus.subscribe("event.a", cb_a)
        bus.subscribe("event.b", cb_b)
        bus.publish("event.a")
        cb_a.assert_called_once()
        cb_b.assert_not_called()

    # ------------------------------------------------------------------
    # Unsubscribe
    # ------------------------------------------------------------------

    def test_unsubscribe_removes_callback(self, bus):
        cb = MagicMock()
        bus.subscribe("evt", cb)
        bus.unsubscribe("evt", cb)
        bus.publish("evt")
        cb.assert_not_called()

    def test_unsubscribe_unknown_event(self, bus):
        cb = MagicMock()
        bus.unsubscribe("nonexistent", cb)

    def test_unsubscribe_unknown_callback(self, bus):
        cb = MagicMock()
        bus.subscribe("evt", cb)
        bus.unsubscribe("evt", MagicMock())
        bus.publish("evt")
        cb.assert_called_once()

    def test_unsubscribe_leaves_other_subscribers(self, bus):
        cb1 = MagicMock()
        cb2 = MagicMock()
        bus.subscribe("evt", cb1)
        bus.subscribe("evt", cb2)
        bus.unsubscribe("evt", cb1)
        bus.publish("evt")
        cb1.assert_not_called()
        cb2.assert_called_once()

    # ------------------------------------------------------------------
    # Ordering
    # ------------------------------------------------------------------

    def test_callbacks_invoked_in_subscribe_order(self, bus):
        order: list[int] = []

        def cb1():
            order.append(1)

        def cb2():
            order.append(2)

        bus.subscribe("evt", cb1)
        bus.subscribe("evt", cb2)
        bus.publish("evt")
        assert order == [1, 2]

    # ------------------------------------------------------------------
    # Error isolation
    # ------------------------------------------------------------------

    def test_failing_subscriber_does_not_block_others(self, bus):
        """One failing subscriber must never prevent remaining
        subscribers from receiving the event."""
        calls: list[str] = []

        def fails(*a, **kw):
            raise RuntimeError("subscriber failed")

        def after_fail(*a, **kw):
            calls.append("reached")

        bus.subscribe("evt", fails)
        bus.subscribe("evt", after_fail)

        bus.publish("evt")

        assert calls == ["reached"]

    def test_failing_subscriber_does_not_raise(self, bus):
        """publish() must not raise when a subscriber fails."""

        def fails(*a, **kw):
            raise RuntimeError("boom")

        bus.subscribe("evt", fails)
        bus.publish("evt")

    def test_multiple_failing_subscribers(self, bus):
        """All remaining subscribers run after multiple failures."""
        calls: list[str] = []

        def fail1(*a, **kw):
            raise RuntimeError("fail1")

        def fail2(*a, **kw):
            raise RuntimeError("fail2")

        def ok(*a, **kw):
            calls.append("ok")

        bus.subscribe("evt", fail1)
        bus.subscribe("evt", fail2)
        bus.subscribe("evt", ok)

        bus.publish("evt")

        assert calls == ["ok"]
