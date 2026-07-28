"""Tests for the Task model."""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from app.kernel.task import Priority, Task, TaskStatus, TaskTrigger


class TestTaskModel:
    def test_default_id_is_generated(self):
        t = Task()
        assert len(t.id) == 16

    def test_unique_ids(self):
        ids = {Task().id for _ in range(100)}
        assert len(ids) == 100

    def test_default_priority_is_normal(self):
        assert Task().priority == Priority.NORMAL

    def test_default_status_is_pending(self):
        assert Task().status == TaskStatus.PENDING

    def test_is_recurring_false_for_once(self):
        t = Task(trigger=TaskTrigger.ONCE)
        assert t.is_recurring is False

    def test_is_recurring_true_for_interval(self):
        t = Task(trigger=TaskTrigger.INTERVAL)
        assert t.is_recurring is True

    def test_is_recurring_true_for_cron(self):
        t = Task(trigger=TaskTrigger.CRON)
        assert t.is_recurring is True

    def test_is_due_false_when_not_scheduled(self):
        t = Task(status=TaskStatus.PENDING)
        assert t.is_due() is False

    def test_is_due_false_when_scheduled_in_future(self):
        t = Task(status=TaskStatus.SCHEDULED, scheduled_at=time.time() + 3600)
        assert t.is_due() is False

    def test_is_due_true_when_scheduled_in_past(self):
        t = Task(status=TaskStatus.SCHEDULED, scheduled_at=time.time() - 1)
        assert t.is_due() is True

    def test_is_due_false_when_not_scheduled_status(self):
        t = Task(status=TaskStatus.RUNNING, scheduled_at=time.time() - 1)
        assert t.is_due() is False

    def test_to_dict_roundtrip(self):
        cb = MagicMock()
        original = Task(
            name="test",
            callable=cb,
            trigger=TaskTrigger.INTERVAL,
            interval_seconds=30.0,
            priority=Priority.HIGH,
            status=TaskStatus.SCHEDULED,
            max_retries=3,
            retry_delay_seconds=5.0,
            retry_count=1,
            scheduled_at=1000.0,
            tags={"system", "monitoring"},
        )
        d = original.to_dict()
        restored = Task.from_dict(d, {"test": cb})
        assert restored.id == original.id
        assert restored.name == "test"
        assert restored.trigger == TaskTrigger.INTERVAL
        assert restored.interval_seconds == 30.0
        assert restored.priority == Priority.HIGH
        assert restored.status == TaskStatus.SCHEDULED
        assert restored.max_retries == 3
        assert restored.retry_delay_seconds == 5.0
        assert restored.retry_count == 1
        assert restored.scheduled_at == 1000.0
        assert restored.tags == {"system", "monitoring"}

    def test_to_dict_includes_all_fields(self):
        t = Task(name="test")
        d = t.to_dict()
        for key in ("id", "name", "trigger", "priority", "status", "created_at"):
            assert key in d

    def test_from_dict_unknown_callable_uses_noop(self):
        d = {"name": "unknown", "trigger": "once"}
        t = Task.from_dict(d, {})
        assert t.name == "unknown"
        t.callable()  # should not raise

    def test_scheduled_at_none_persistence(self):
        cb = MagicMock()
        t = Task(name="test", callable=cb)
        d = t.to_dict()
        restored = Task.from_dict(d, {"test": cb})
        assert restored.scheduled_at is None

    def test_priority_ordering(self):
        assert Priority.LOW.value < Priority.NORMAL.value < Priority.HIGH.value < Priority.CRITICAL.value
