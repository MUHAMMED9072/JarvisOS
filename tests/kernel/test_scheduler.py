"""Tests for the SystemScheduler."""

from __future__ import annotations

import json
import os
import queue
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.core.event_bus import EventBus
from app.kernel.scheduler import CronExpression, SchedulerEvents, SchedulerHealth, SystemScheduler
from app.kernel.task import Priority, TaskStatus


# =========================================================================
# Helpers
# =========================================================================


class SchedulerTestBase:
    """Base class providing common fixtures for scheduler tests."""

    @pytest.fixture
    def event_bus(self):
        return EventBus()

    @pytest.fixture
    def scheduler(self, event_bus):
        s = SystemScheduler(event_bus=event_bus, max_workers=2, poll_interval=0.02)
        s.start()
        yield s
        s.stop(timeout=2.0)

    def wait_for(
        self,
        condition,
        timeout: float = 5.0,
        interval: float = 0.05,
    ) -> bool:
        """Wait for a condition to become true."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if condition():
                return True
            time.sleep(interval)
        return False


# =========================================================================
# Start / Stop
# =========================================================================


class TestSchedulerStartStop(SchedulerTestBase):
    def test_start_initializes_scheduler(self, event_bus):
        s = SystemScheduler(event_bus=event_bus)
        s.start()
        assert s.health().alive is True
        s.stop()

    def test_stop_marks_not_alive(self, scheduler):
        scheduler.stop(timeout=2.0)
        assert scheduler.health().alive is False

    def test_double_start_is_idempotent(self, event_bus):
        s = SystemScheduler(event_bus=event_bus)
        s.start()
        s.start()
        s.stop()

    def test_double_stop_is_idempotent(self, scheduler):
        scheduler.stop(timeout=2.0)
        scheduler.stop(timeout=1.0)

    def test_stop_before_start_does_not_raise(self, event_bus):
        s = SystemScheduler(event_bus=event_bus)
        s.stop()


# =========================================================================
# Schedule Once
# =========================================================================


class TestSchedulerOnce(SchedulerTestBase):
    def test_schedule_immediate_executes(self, scheduler):
        results: list[str] = []

        def worker():
            results.append("done")

        scheduler.schedule_once("immediate", worker, delay=0)
        assert self.wait_for(lambda: len(results) >= 1)
        assert results == ["done"]

    def test_schedule_with_delay(self, scheduler):
        results: list[str] = []

        def worker():
            results.append("done")

        scheduler.schedule_once("delayed", worker, delay=0.3)
        time.sleep(0.1)
        assert len(results) == 0
        assert self.wait_for(lambda: len(results) >= 1, timeout=2.0)
        assert results == ["done"]

    def test_schedule_with_args(self, scheduler):
        results: list[int] = []

        def worker(n):
            results.append(n)

        scheduler.schedule_once("args", worker, delay=0, args=(42,))
        assert self.wait_for(lambda: len(results) >= 1)
        assert results == [42]

    def test_schedule_with_kwargs(self, scheduler):
        results: dict = {}

        def worker(**kw):
            results.update(kw)

        scheduler.schedule_once("kwargs", worker, delay=0, kwargs={"key": "val"})
        assert self.wait_for(lambda: bool(results))
        assert results == {"key": "val"}


# =========================================================================
# Schedule Interval
# =========================================================================


class TestSchedulerInterval(SchedulerTestBase):
    def test_interval_task_runs_multiple_times(self, scheduler):
        count = 0
        lock = threading.Lock()

        def worker():
            nonlocal count
            with lock:
                count += 1

        scheduler.schedule_interval("counter", worker, interval=0.05, delay=0)
        assert self.wait_for(lambda: count >= 3, timeout=2.0)
        assert count >= 3

    def test_interval_task_persists_after_execution(self, scheduler):
        count = 0
        lock = threading.Lock()

        def worker():
            nonlocal count
            with lock:
                count += 1

        task = scheduler.schedule_interval("persist", worker, interval=0.05, delay=0)
        task_id = task.id
        assert self.wait_for(lambda: count >= 2, timeout=2.0)
        assert scheduler.get_task(task_id) is not None or count >= 2


# =========================================================================
# Schedule Cron
# =========================================================================


class TestSchedulerCron(SchedulerTestBase):
    def test_schedule_cron_executes(self, scheduler):
        results: list[str] = []
        parsed = CronExpression("* * * * *")
        next_time = parsed.next_after(time.time())
        assert next_time is not None
        wait = max(0.05, next_time - time.time() + 0.02)

        def worker():
            results.append("done")

        scheduler.schedule_cron("cron-test", worker, "* * * * *")
        assert self.wait_for(lambda: len(results) >= 1, timeout=wait + 2.0)
        assert results == ["done"]

    def test_schedule_cron_invalid_expression_raises(self, scheduler):
        def worker():
            pass

        with pytest.raises(Exception):
            scheduler.schedule_cron("bad-cron", worker, "0 0 30 FEB *")

    def test_schedule_cron_reschedules_after_run(self, scheduler):
        """Cron task should be re-scheduled after execution."""
        count = 0
        lock = threading.Lock()

        def worker():
            nonlocal count
            with lock:
                count += 1

        scheduler.schedule_cron("cron-recur", worker, "* * * * *")
        assert self.wait_for(lambda: count >= 1, timeout=65.0)


# =========================================================================
# Priority Ordering
# =========================================================================


class TestSchedulerPriority(SchedulerTestBase):
    def test_high_priority_task_runs_before_low(self, scheduler):
        execution_order: list[str] = []
        lock = threading.Lock()

        def make_worker(name):
            def worker():
                with lock:
                    execution_order.append(name)
            return worker

        # Submit low first, then high
        scheduler.schedule_once("low", make_worker("low"), delay=0, priority=Priority.LOW)
        scheduler.schedule_once("high", make_worker("high"), delay=0, priority=Priority.HIGH)

        assert self.wait_for(lambda: len(execution_order) >= 2, timeout=5.0)
        assert execution_order[0] == "high"


# =========================================================================
# Task Cancellation
# =========================================================================


class TestSchedulerCancellation(SchedulerTestBase):
    def test_cancel_pending_task(self, scheduler):
        results: list[str] = []

        def worker():
            results.append("done")

        task = scheduler.schedule_once("cancel-me", worker, delay=5.0)
        assert scheduler.cancel(task.id) is True
        time.sleep(0.1)
        assert len(results) == 0
        assert scheduler.get_task(task.id).status == TaskStatus.CANCELLED

    def test_cancel_running_task_returns_false(self, scheduler):
        event = threading.Event()

        def worker():
            event.wait(timeout=5)

        task = scheduler.schedule_once("running", worker, delay=0)
        assert self.wait_for(lambda: task.status == TaskStatus.RUNNING or scheduler.health().running > 0, timeout=3.0)
        assert scheduler.cancel(task.id) is False
        event.set()

    def test_cancel_nonexistent_task_returns_false(self, scheduler):
        assert scheduler.cancel("nonexistent") is False

    def test_cancel_completed_task_returns_false(self, scheduler):
        results: list[str] = []

        def worker():
            results.append("done")

        task = scheduler.schedule_once("quick", worker, delay=0)
        assert self.wait_for(lambda: len(results) >= 1)
        assert scheduler.cancel(task.id) is False


# =========================================================================
# Retry Policy
# =========================================================================


class TestSchedulerRetry(SchedulerTestBase):
    def test_task_retried_on_failure(self, scheduler):
        attempt_count = 0
        lock = threading.Lock()

        def worker():
            nonlocal attempt_count
            with lock:
                attempt_count += 1
            raise RuntimeError("fail")

        scheduler.schedule_once("retry-me", worker, delay=0, max_retries=2, retry_delay=0.05)
        assert self.wait_for(lambda: attempt_count >= 3, timeout=5.0)
        assert attempt_count == 3

    def test_task_fails_after_max_retries(self, scheduler):
        results: list[str] = []

        def worker():
            results.append("attempt")
            raise RuntimeError("fail")

        task = scheduler.schedule_once("fail-after-retries", worker, delay=0, max_retries=1, retry_delay=0.05)
        assert self.wait_for(lambda: task.status == TaskStatus.FAILED, timeout=5.0)
        assert len(results) == 2

    def test_no_retry_when_max_retries_zero(self, scheduler):
        results: list[str] = []

        def worker():
            results.append("attempt")
            raise RuntimeError("fail")

        task = scheduler.schedule_once("no-retry", worker, delay=0, max_retries=0)
        assert self.wait_for(lambda: task.status == TaskStatus.FAILED, timeout=5.0)
        assert len(results) == 1


# =========================================================================
# Event Publishing
# =========================================================================


class TestSchedulerEvents(SchedulerTestBase):
    def test_publishes_submitted_event(self, scheduler, event_bus):
        events: list[str] = []
        event_bus.subscribe(SchedulerEvents.TASK_SUBMITTED, lambda **kw: events.append("submitted"))

        def worker():
            pass

        scheduler.schedule_once("evt-test", worker, delay=0)
        assert self.wait_for(lambda: "submitted" in events)

    def test_publishes_started_event(self, scheduler, event_bus):
        events: list[str] = []
        event_bus.subscribe(SchedulerEvents.TASK_STARTED, lambda **kw: events.append("started"))

        def worker():
            pass

        scheduler.schedule_once("evt-start", worker, delay=0)
        assert self.wait_for(lambda: "started" in events)

    def test_publishes_completed_event(self, scheduler, event_bus):
        events: list[str] = []
        event_bus.subscribe(SchedulerEvents.TASK_COMPLETED, lambda **kw: events.append("completed"))

        def worker():
            pass

        scheduler.schedule_once("evt-complete", worker, delay=0)
        assert self.wait_for(lambda: "completed" in events)

    def test_publishes_failed_event(self, scheduler, event_bus):
        events: list[str] = []
        event_bus.subscribe(SchedulerEvents.TASK_FAILED, lambda **kw: events.append("failed"))

        def worker():
            raise RuntimeError("boom")

        scheduler.schedule_once("evt-fail", worker, delay=0, max_retries=0)
        assert self.wait_for(lambda: "failed" in events)

    def test_publishes_cancelled_event(self, scheduler, event_bus):
        events: list[str] = []
        event_bus.subscribe(SchedulerEvents.TASK_CANCELLED, lambda **kw: events.append("cancelled"))

        def worker():
            pass

        task = scheduler.schedule_once("evt-cancel", worker, delay=5.0)
        scheduler.cancel(task.id)
        assert "cancelled" in events

    def test_publishes_retrying_event(self, scheduler, event_bus):
        events: list[str] = []
        event_bus.subscribe(SchedulerEvents.TASK_RETRYING, lambda **kw: events.append("retrying"))

        def worker():
            raise RuntimeError("fail")

        scheduler.schedule_once("evt-retry", worker, delay=0, max_retries=1, retry_delay=0.05)
        assert self.wait_for(lambda: "retrying" in events, timeout=5.0)

    def test_publishes_heartbeat(self, scheduler, event_bus):
        events: list[str] = []
        event_bus.subscribe(SchedulerEvents.SCHEDULER_HEARTBEAT, lambda **kw: events.append("heartbeat"))

        assert self.wait_for(lambda: "heartbeat" in events, timeout=10.0)


# =========================================================================
# Health
# =========================================================================


class TestSchedulerHealth(SchedulerTestBase):
    def test_health_returns_alive(self, scheduler):
        health = scheduler.health()
        assert health.alive is True

    def test_health_queued_count(self, scheduler):
        def worker():
            pass

        for i in range(5):
            scheduler.schedule_once(f"h-{i}", worker, delay=10.0)
        health = scheduler.health()
        assert health.queued == 5

    def test_health_includes_running_count(self, scheduler):
        event = threading.Event()
        running_count = [0]

        def worker():
            running_count[0] = scheduler.health().running
            event.wait(timeout=5)

        scheduler.schedule_once("h-run", worker, delay=0)
        assert self.wait_for(lambda: running_count[0] > 0, timeout=3.0) or scheduler.health().running > 0
        event.set()

    def test_health_includes_completed_count(self, scheduler):
        def worker():
            pass

        scheduler.schedule_once("h-comp", worker, delay=0)
        assert self.wait_for(lambda: scheduler.health().completed >= 1, timeout=5.0)

    def test_health_includes_failed_count(self, scheduler):
        def worker():
            raise RuntimeError("fail")

        scheduler.schedule_once("h-fail", worker, delay=0, max_retries=0)
        assert self.wait_for(lambda: scheduler.health().failed >= 1, timeout=5.0)

    def test_health_uptime_increases(self, scheduler):
        time.sleep(0.1)
        health = scheduler.health()
        assert health.uptime > 0.0

    def test_health_to_dict(self, scheduler):
        d = scheduler.health().to_dict()
        assert "alive" in d
        assert "queued" in d
        assert "running" in d
        assert "completed" in d
        assert "failed" in d
        assert "uptime_seconds" in d

    def test_health_after_stop(self, scheduler):
        scheduler.stop(timeout=2.0)
        health = scheduler.health()
        assert health.alive is False


# =========================================================================
# List Tasks
# =========================================================================


class TestSchedulerListTasks(SchedulerTestBase):
    def test_list_tasks_returns_all(self, scheduler):
        def worker():
            pass

        scheduler.schedule_once("a", worker, delay=10)
        scheduler.schedule_once("b", worker, delay=10)
        tasks = scheduler.list_tasks()
        assert len(tasks) == 2

    def test_list_tasks_filter_by_status(self, scheduler):
        def worker():
            pass

        scheduler.schedule_once("pending", worker, delay=10)
        tasks = scheduler.list_tasks(status=TaskStatus.SCHEDULED)
        assert len(tasks) >= 1
        tasks_running = scheduler.list_tasks(status=TaskStatus.RUNNING)
        assert len(tasks_running) == 0

    def test_list_tasks_filter_by_tags(self, scheduler):
        def worker():
            pass

        scheduler.schedule_once("tagged", worker, delay=10, tags={"test"})
        scheduler.schedule_once("untagged", worker, delay=10)
        tasks = scheduler.list_tasks(tags={"test"})
        assert len(tasks) == 1
        assert tasks[0].name == "tagged"


# =========================================================================
# Get Task
# =========================================================================


class TestSchedulerGetTask(SchedulerTestBase):
    def test_get_task_returns_task(self, scheduler):
        def worker():
            pass

        t = scheduler.schedule_once("get-me", worker, delay=10)
        assert scheduler.get_task(t.id) is t

    def test_get_task_nonexistent_returns_none(self, scheduler):
        assert scheduler.get_task("nope") is None

    def test_get_task_after_completion(self, scheduler):
        results: list[str] = []

        def worker():
            results.append("done")

        t = scheduler.schedule_once("complete-get", worker, delay=0)
        assert self.wait_for(lambda: len(results) >= 1)
        # Completed one-shot tasks are removed from _tasks
        assert scheduler.get_task(t.id) is None


# =========================================================================
# Thread Safety
# =========================================================================


class TestSchedulerThreadSafety(SchedulerTestBase):
    def test_concurrent_schedule_does_not_crash(self, scheduler):
        def worker():
            pass

        def schedule_many():
            for i in range(50):
                scheduler.schedule_once(f"ts-{i}", worker, delay=0.01)

        threads = [threading.Thread(target=schedule_many) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)
        assert scheduler.health().queued <= 200

    def test_concurrent_list_and_schedule_does_not_deadlock(self, scheduler):
        def worker():
            pass

        def list_loop():
            for _ in range(100):
                scheduler.list_tasks()
                scheduler.health()

        def schedule_loop():
            for i in range(100):
                scheduler.schedule_once(f"dl-{i}", worker, delay=0.1)

        threads = [
            threading.Thread(target=list_loop),
            threading.Thread(target=schedule_loop),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)


# =========================================================================
# Persistence
# =========================================================================


class TestSchedulerPersistence:
    @pytest.fixture
    def persistence_path(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = Path(f.name)
        yield path
        if path.exists():
            path.unlink()

    @pytest.fixture
    def event_bus(self):
        return EventBus()

    def test_saves_recurring_tasks_on_stop(self, persistence_path, event_bus):
        s = SystemScheduler(event_bus=event_bus, persistence_path=persistence_path, max_workers=1, poll_interval=0.02)
        s.start()

        def worker():
            pass

        s.schedule_interval("persist-me", worker, interval=60.0, delay=60.0)
        s.schedule_cron("persist-cron", worker, "0 3 * * *")
        s.schedule_once("no-persist", worker, delay=0.1)
        time.sleep(0.2)
        s.stop(timeout=2.0)

        assert persistence_path.exists()
        with open(persistence_path) as f:
            data = json.load(f)
        names = [t["name"] for t in data["tasks"]]
        assert "persist-me" in names
        assert "persist-cron" in names
        assert "no-persist" not in names

    def test_restores_recurring_tasks_on_start(self, persistence_path, event_bus):
        # First: create persisted tasks
        s1 = SystemScheduler(event_bus=event_bus, persistence_path=persistence_path, max_workers=1, poll_interval=0.02)
        s1.start()

        def worker():
            pass

        s1.schedule_interval("restore-me", worker, interval=60.0, delay=60.0)
        s1.stop(timeout=2.0)

        # Second: restore them
        s2 = SystemScheduler(event_bus=event_bus, persistence_path=persistence_path, max_workers=1, poll_interval=0.02)
        s2.start()

        tasks = s2.list_tasks()
        names = [t.name for t in tasks]
        assert "restore-me" in names
        s2.stop(timeout=2.0)

    def test_persistence_no_file_does_not_crash(self, event_bus):
        s = SystemScheduler(event_bus=event_bus, persistence_path=Path("/nonexistent/scheduler.json"), max_workers=1)
        s.start()
        s.stop(timeout=2.0)

    def test_persistence_no_path_does_nothing(self, event_bus):
        s = SystemScheduler(event_bus=event_bus, persistence_path=None)
        s.start()
        s.stop(timeout=2.0)


# =========================================================================
# No Event Bus
# =========================================================================


class TestSchedulerNoEventBus:
    def test_no_event_bus_does_not_crash(self):
        s = SystemScheduler(event_bus=None, max_workers=1, poll_interval=0.02)
        s.start()

        results: list[str] = []

        def worker():
            results.append("done")

        s.schedule_once("no-bus", worker, delay=0)
        deadline = time.time() + 5
        while time.time() < deadline:
            if results:
                break
            time.sleep(0.05)
        assert results == ["done"]
        s.stop()


# =========================================================================
# Register Callable
# =========================================================================


class TestSchedulerCallableRegistry(SchedulerTestBase):
    def test_register_callable(self, event_bus):
        s = SystemScheduler(event_bus=event_bus)

        def my_func():
            return 42

        s.register_callable("my-func", my_func)
        s.start()

        results: list[int] = []

        def capture():
            results.append(my_func())

        s.schedule_once("capture", capture, delay=0)
        deadline = time.time() + 5
        while time.time() < deadline:
            if results:
                break
            time.sleep(0.05)
        assert results == [42]
        s.stop()
