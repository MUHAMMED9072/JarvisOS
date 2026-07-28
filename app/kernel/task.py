from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Callable, Optional


class Priority(Enum):
    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


class TaskStatus(Enum):
    PENDING = auto()
    SCHEDULED = auto()
    RUNNING = auto()
    COMPLETED = auto()
    FAILED = auto()
    CANCELLED = auto()


class TaskTrigger(Enum):
    """Describes what triggers a task's execution."""

    ONCE = "once"
    INTERVAL = "interval"
    CRON = "cron"
    IMMEDIATE = "immediate"


@dataclass
class Task:
    """A schedulable unit of work.

    Every task has a unique ID, a callable, scheduling metadata, and
    a priority.  Tasks are immutable after creation except for their
    status and result fields.
    """

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    name: str = ""
    callable: Callable[..., Any] = lambda: None
    args: tuple[Any, ...] = ()
    kwargs: dict[str, Any] = field(default_factory=dict)

    trigger: TaskTrigger = TaskTrigger.ONCE

    # Interval (seconds) for INTERVAL tasks
    interval_seconds: float = 0.0

    # Cron expression for CRON tasks (standard 5-field)
    cron_expression: str = ""

    # Priority determines execution order
    priority: Priority = Priority.NORMAL

    # Current lifecycle status
    status: TaskStatus = TaskStatus.PENDING

    # Retry policy
    max_retries: int = 0
    retry_delay_seconds: float = 1.0
    retry_count: int = 0

    # Timestamps
    created_at: float = field(default_factory=lambda: datetime.now().timestamp())
    scheduled_at: Optional[float] = None  # Unix timestamp for first/next run
    started_at: Optional[float] = None
    completed_at: Optional[float] = None

    # Outcome
    result: Any = None
    error: Optional[str] = None

    # Tags for filtering / grouping
    tags: set[str] = field(default_factory=set)

    @property
    def is_recurring(self) -> bool:
        return self.trigger in (TaskTrigger.INTERVAL, TaskTrigger.CRON)

    def is_due(self, now: float | None = None) -> bool:
        if self.scheduled_at is None:
            return False
        if self.status != TaskStatus.SCHEDULED:
            return False
        return (now or datetime.now().timestamp()) >= self.scheduled_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "trigger": self.trigger.value,
            "interval_seconds": self.interval_seconds,
            "cron_expression": self.cron_expression,
            "priority": self.priority.value,
            "status": self.status.name,
            "max_retries": self.max_retries,
            "retry_delay_seconds": self.retry_delay_seconds,
            "retry_count": self.retry_count,
            "created_at": self.created_at,
            "scheduled_at": self.scheduled_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "error": self.error,
            "tags": list(self.tags),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], callable_map: dict[str, Callable[..., Any]]) -> Task:
        cb = callable_map.get(data.get("name", ""), lambda: None)
        return cls(
            id=data.get("id", uuid.uuid4().hex[:16]),
            name=data.get("name", ""),
            callable=cb,
            trigger=TaskTrigger(data.get("trigger", "once")),
            interval_seconds=data.get("interval_seconds", 0.0),
            cron_expression=data.get("cron_expression", ""),
            priority=Priority(data.get("priority", 1)),
            status=TaskStatus[data.get("status", "PENDING")],
            max_retries=data.get("max_retries", 0),
            retry_delay_seconds=data.get("retry_delay_seconds", 1.0),
            retry_count=data.get("retry_count", 0),
            created_at=data.get("created_at", 0.0),
            scheduled_at=data.get("scheduled_at"),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            error=data.get("error"),
            tags=set(data.get("tags", [])),
        )
