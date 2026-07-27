"""Tests for client-side EventDispatcher."""

from __future__ import annotations

import threading

import pytest

from app.client.events import EventDispatcher


class TestEventDispatcher:
    def test_subscribe_and_publish(self):
        d = EventDispatcher()
        received = []

        def handler(event, **data):
            received.append((event, data))

        d.subscribe("test.event", handler)
        d.publish("test.event", value=42)
        assert len(received) == 1
        assert received[0] == ("test.event", {"value": 42})

    def test_unsubscribe(self):
        d = EventDispatcher()
        received = []

        def handler(event, **data):
            received.append(event)

        d.subscribe("test.event", handler)
        d.unsubscribe("test.event", handler)
        d.publish("test.event")
        assert len(received) == 0

    def test_unsubscribe_nonexistent(self):
        d = EventDispatcher()

        def handler(event, **data):
            pass

        result = d.unsubscribe("nonexistent", handler)
        assert result is False

    def test_wildcard_match(self):
        d = EventDispatcher()
        received = []

        def handler(event, **data):
            received.append(event)

        d.subscribe("test.*", handler)
        d.publish("test.foo")
        d.publish("test.bar")
        d.publish("other.baz")
        assert received == ["test.foo", "test.bar"]

    def test_multiple_handlers_same_event(self):
        d = EventDispatcher()
        results = []

        def h1(event, **data):
            results.append("h1")

        def h2(event, **data):
            results.append("h2")

        d.subscribe("evt", h1)
        d.subscribe("evt", h2)
        d.publish("evt")
        assert sorted(results) == ["h1", "h2"]

    def test_handler_exception_does_not_block(self):
        d = EventDispatcher()
        results = []

        def bad_handler(event, **data):
            raise ValueError("boom")

        def good_handler(event, **data):
            results.append("ok")

        d.subscribe("evt", bad_handler)
        d.subscribe("evt", good_handler)
        d.publish("evt")
        assert results == ["ok"]

    def test_clear(self):
        d = EventDispatcher()

        def handler(event, **data):
            pass

        d.subscribe("a", handler)
        d.subscribe("b", handler)
        assert d.listener_count == 2
        d.clear()
        assert d.listener_count == 0
        assert d.event_count == 0

    def test_listener_and_event_counts(self):
        d = EventDispatcher()

        def h1(event, **data):
            pass

        def h2(event, **data):
            pass

        assert d.listener_count == 0
        d.subscribe("evt", h1)
        assert d.listener_count == 1
        assert d.event_count == 1
        d.subscribe("evt", h2)
        assert d.listener_count == 2
        assert d.event_count == 1

    def test_thread_safety(self):
        d = EventDispatcher()
        errors = []

        def worker():
            try:
                for i in range(100):
                    d.publish("test", i=i)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(errors) == 0

    def test_subscribe_invalid_callback(self):
        d = EventDispatcher()
        with pytest.raises(ValueError, match="callable"):
            d.subscribe("evt", "not_callable")  # type: ignore

    def test_publish_no_listeners(self):
        d = EventDispatcher()
        d.publish("nonexistent")  # Should not raise

    def test_wildcard_matches_multiple_levels(self):
        d = EventDispatcher()
        received = []

        def handler(event, **data):
            received.append(event)

        d.subscribe("message.*", handler)
        d.publish("message.auth.success")
        d.publish("message.auth.failure")
        assert len(received) == 2
