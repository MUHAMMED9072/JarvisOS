"""Tests for EventBus (thread-safe enhanced version)."""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock

import pytest

from app.core.event_bus import EventBus


class TestEventBusThreadSafety:
    @pytest.fixture
    def bus(self):
        return EventBus()

    def test_concurrent_subscribe_is_safe(self, bus):
        """Multiple threads can subscribe concurrently."""
        def sub(i):
            bus.subscribe(f"evt.{i}", lambda: None)

        threads = [threading.Thread(target=sub, args=(i,)) for i in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert bus.pattern_count == 50
        assert bus.listener_count == 50

    def test_concurrent_publish_is_safe(self, bus):
        """Multiple threads can publish concurrently."""
        results: list[int] = []
        lock = threading.Lock()

        def collector(n):
            with lock:
                results.append(n)

        for i in range(10):
            bus.subscribe(f"evt.{i}", lambda n=i: collector(n))

        def pub(i):
            bus.publish(f"evt.{i}")

        threads = [threading.Thread(target=pub, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 10
        assert sorted(results) == list(range(10))

    def test_concurrent_subscribe_and_publish_no_deadlock(self, bus):
        """Subscribing while publishing does not deadlock."""
        bus.subscribe("hot", lambda: None)

        def publish_loop():
            for _ in range(100):
                bus.publish("hot")

        def subscribe_loop():
            for i in range(100):
                bus.subscribe(f"dyn.{i}", lambda: None)

        threads = [
            threading.Thread(target=publish_loop),
            threading.Thread(target=subscribe_loop),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

    def test_concurrent_unsubscribe_does_not_break_publish(self, bus):
        """Unsubscribing while publishing does not cause errors."""
        cbs = [MagicMock() for _ in range(20)]
        for cb in cbs:
            bus.subscribe("evt", cb)

        def unsub():
            for cb in cbs[10:]:
                bus.unsubscribe("evt", cb)

        def pub():
            bus.publish("evt")

        threads = [threading.Thread(target=unsub), threading.Thread(target=pub)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    def test_reentrant_lock_used(self, bus):
        """Lock must be reentrant for nested operations."""
        bus.subscribe("evt", lambda: bus.subscribe("nested", lambda: None))
        bus.publish("evt")
        assert bus.pattern_count >= 2


class TestEventBusNewFeatures:
    @pytest.fixture
    def bus(self):
        return EventBus()

    def test_listener_count(self, bus):
        assert bus.listener_count == 0
        bus.subscribe("a", lambda: None)
        bus.subscribe("a", lambda: None)
        bus.subscribe("b", lambda: None)
        assert bus.listener_count == 3

    def test_pattern_count(self, bus):
        assert bus.pattern_count == 0
        bus.subscribe("a", lambda: None)
        bus.subscribe("b", lambda: None)
        assert bus.pattern_count == 2

    def test_clear_removes_all(self, bus):
        bus.subscribe("a", lambda: None)
        bus.subscribe("b", lambda: None)
        bus.clear()
        assert bus.listener_count == 0
        assert bus.pattern_count == 0

    def test_clear_allows_new_subscriptions(self, bus):
        bus.subscribe("a", lambda: None)
        bus.clear()
        cb = MagicMock()
        bus.subscribe("b", cb)
        bus.publish("b")
        cb.assert_called_once()


class TestEventBusExistingBehavior:
    """Verify all existing tests still pass with the enhanced bus."""

    @pytest.fixture
    def bus(self):
        return EventBus()

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

    def test_wildcard_subscribe(self, bus):
        cb = MagicMock()
        bus.subscribe_wildcard("ai.*", cb)
        bus.publish("ai.request", "data")
        cb.assert_called_once_with("ai.request", "data")

    def test_wildcard_no_match(self, bus):
        cb = MagicMock()
        bus.subscribe_wildcard("ai.*", cb)
        bus.publish("system.health")
        cb.assert_not_called()

    def test_unsubscribe(self, bus):
        cb = MagicMock()
        bus.subscribe("evt", cb)
        bus.unsubscribe("evt", cb)
        bus.publish("evt")
        cb.assert_not_called()

    def test_unsubscribe_unknown_event(self, bus):
        bus.unsubscribe("nonexistent", lambda: None)

    def test_unsubscribe_unknown_callback(self, bus):
        cb = MagicMock()
        bus.subscribe("evt", cb)
        bus.unsubscribe("evt", MagicMock())
        bus.publish("evt")
        cb.assert_called_once()

    def test_callbacks_invoked_in_order(self, bus):
        order: list[int] = []

        def cb1():
            order.append(1)

        def cb2():
            order.append(2)

        bus.subscribe("evt", cb1)
        bus.subscribe("evt", cb2)
        bus.publish("evt")
        assert order == [1, 2]

    def test_failing_subscriber_does_not_block_others(self, bus):
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
        def fails(*a, **kw):
            raise RuntimeError("boom")

        bus.subscribe("evt", fails)
        bus.publish("evt")


class TestEventBusPerformance:
    """Performance benchmark: 10K events/sec with <1ms median latency."""

    def test_throughput_benchmark(self):
        bus = EventBus()
        cb = MagicMock()
        bus.subscribe("perf", cb)

        count = 10_000
        start = time.perf_counter()
        for _ in range(count):
            bus.publish("perf")
        elapsed = time.perf_counter() - start

        events_per_sec = count / elapsed
        assert cb.call_count == count
        assert events_per_sec >= 10_000, (
            f"Throughput {events_per_sec:.0f} events/sec < 10,000"
        )

    def test_latency_benchmark(self):
        bus = EventBus()
        cb = MagicMock()
        bus.subscribe("perf", cb)

        count = 1_000
        latencies: list[float] = []
        for _ in range(count):
            start = time.perf_counter_ns()
            bus.publish("perf")
            elapsed_ns = time.perf_counter_ns() - start
            latencies.append(elapsed_ns / 1_000_000)

        latencies.sort()
        median = latencies[len(latencies) // 2]
        assert median < 1.0, f"Median latency {median:.3f}ms >= 1ms"

    def test_multiple_subscribers_benchmark(self):
        bus = EventBus()
        cbs = [MagicMock() for _ in range(10)]
        for cb in cbs:
            bus.subscribe("multi", cb)

        count = 1_000
        start = time.perf_counter()
        for _ in range(count):
            bus.publish("multi")
        elapsed = time.perf_counter() - start

        events_per_sec = count / elapsed
        for cb in cbs:
            assert cb.call_count == count
        assert events_per_sec >= 1_000, (
            f"Throughput with 10 subscribers: {events_per_sec:.0f} events/sec"
        )

    def test_wildcard_throughput_benchmark(self):
        bus = EventBus()
        cb = MagicMock()
        bus.subscribe_wildcard("ai.*", cb)

        count = 10_000
        start = time.perf_counter()
        for i in range(count):
            bus.publish(f"ai.event.{i}")
        elapsed = time.perf_counter() - start

        events_per_sec = count / elapsed
        assert cb.call_count == count
        assert events_per_sec >= 10_000, (
            f"Wildcard throughput {events_per_sec:.0f} events/sec < 10,000"
        )
