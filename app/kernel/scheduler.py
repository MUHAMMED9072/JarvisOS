from __future__ import annotations

import json
import os
import queue
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from app.core.event_bus import EventBus
from app.core.logger import JarvisLogger
from app.kernel.task import Priority, Task, TaskStatus, TaskTrigger


class CronParseError(ValueError):
    """Raised when a cron expression cannot be parsed."""

    pass


def _cron_dow(python_weekday: int) -> int:
    """Convert Python weekday (Monday=0) to cron weekday (Sunday=0)."""
    return (python_weekday + 1) % 7


def _python_dow(cron_weekday: int) -> int:
    """Convert cron weekday (Sunday=0) to Python weekday (Monday=0)."""
    return (cron_weekday - 1) % 7


@dataclass
class CronField:
    """Represents a single parsed cron field with allowed values."""

    values: set[int] = field(default_factory=set)

    @classmethod
    def parse(cls, field: str, min_val: int, max_val: int, names: dict[str, int] | None = None) -> CronField:
        """Parse a single cron field (*, N, N-M, N,M,O, */N, N-M/M, etc.)."""
        field = field.strip()
        result: set[int] = set()

        if field == "*":
            return cls(values=set(range(min_val, max_val + 1)))

        if names:
            for name, num in names.items():
                field = field.replace(name.upper(), str(num))
                field = field.replace(name.lower(), str(num))
                field = field.replace(name.capitalize(), str(num))

        for part in field.split(","):
            part = part.strip()
            if not part:
                raise CronParseError(f"Empty field value in cron expression")
            if "/" in part:
                base, step = part.split("/", 1)
                step_val = int(step)
                if base == "*":
                    values = range(min_val, max_val + 1, step_val)
                elif "-" in base:
                    low, high = base.split("-", 1)
                    if not low or not high:
                        raise CronParseError(f"Invalid range '{base}' in cron field")
                    values = range(int(low), int(high) + 1, step_val)
                else:
                    values = range(int(base), max_val + 1, step_val)
                result.update(values)
            elif "-" in part:
                if part.startswith("-"):
                    low = part
                    high = None
                else:
                    segments = part.split("-", 1)
                    low, high = segments[0], segments[1]
                if high is None or not low or not high:
                    raise CronParseError(f"Invalid value '{part}' in cron field")
                result.update(range(int(low), int(high) + 1))
            else:
                try:
                    result.add(int(part))
                except ValueError:
                    raise CronParseError(f"Invalid value '{part}' in cron field")

        if not result:
            raise CronParseError(f"Field '{field}' produced no valid values")

        bad = {v for v in result if v < min_val or v > max_val}
        if bad:
            raise CronParseError(
                f"Values {bad} out of range [{min_val}, {max_val}] in field"
            )

        return cls(values=result)


class CronExpression:
    """Standard 5-field cron expression parser.

    Fields: minute (0-59), hour (0-23), day-of-month (1-31),
            month (1-12), day-of-week (0-6, 0=Sunday).

    Supports:
      - Numbers: ``5``
      - Ranges: ``1-5``
      - Lists: ``1,3,5``
      - Steps: ``*/5``, ``1-10/2``
      - Wildcards: ``*``
      - Named months: ``JAN``-``DEC`` (case-insensitive)
      - Named weekdays: ``SUN``-``SAT`` (case-insensitive)
    """

    MONTH_NAMES: dict[str, int] = {
        "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
        "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
    }
    WEEKDAY_NAMES: dict[str, int] = {
        "SUN": 0, "MON": 1, "TUE": 2, "WED": 3, "THU": 4, "FRI": 5, "SAT": 6,
    }

    def __init__(self, expression: str) -> None:
        parts = expression.strip().split()
        if len(parts) != 5:
            raise CronParseError(
                f"Expected 5 fields, got {len(parts)}: '{expression}'"
            )
        self._expression = expression
        self._minute = CronField.parse(parts[0], 0, 59)
        self._hour = CronField.parse(parts[1], 0, 23)
        self._day_of_month = CronField.parse(parts[2], 1, 31)
        self._month = CronField.parse(parts[3], 1, 12, self.MONTH_NAMES)
        self._day_of_week = CronField.parse(parts[4], 0, 6, self.WEEKDAY_NAMES)

    @property
    def expression(self) -> str:
        return self._expression

    def next_after(self, after: float | None = None) -> Optional[float]:
        """Return the next UTC timestamp (seconds) that matches the cron expression
        after the given timestamp (defaults to now).  Returns ``None`` if no
        future match exists."""
        dt = datetime.fromtimestamp(after or time.time(), tz=timezone.utc)
        for _ in range(366 * 1440):
            dt = dt.replace(second=0, microsecond=0) + timedelta(minutes=1)
            cron_dow = _cron_dow(dt.weekday())
            if (
                dt.month in self._month.values
                and dt.day in self._day_of_month.values
                and cron_dow in self._day_of_week.values
                and dt.hour in self._hour.values
                and dt.minute in self._minute.values
            ):
                return dt.timestamp()
        return None

    def matches(self, timestamp: float | None = None) -> bool:
        """Check if the given timestamp matches the cron expression."""
        dt = datetime.fromtimestamp(timestamp or time.time(), tz=timezone.utc)
        cron_dow = _cron_dow(dt.weekday())
        return (
            dt.minute in self._minute.values
            and dt.hour in self._hour.values
            and dt.day in self._day_of_month.values
            and dt.month in self._month.values
            and cron_dow in self._day_of_week.values
        )


class SchedulerHealth:
    """Snapshot of scheduler health for the Health Monitor."""

    def __init__(
        self,
        alive: bool,
        queued: int,
        running: int,
        completed: int,
        failed: int,
        thread_pool_size: int,
        uptime: float,
    ) -> None:
        self.alive = alive
        self.queued = queued
        self.running = running
        self.completed = completed
        self.failed = failed
        self.thread_pool_size = thread_pool_size
        self.uptime = uptime

    def to_dict(self) -> dict[str, Any]:
        return {
            "alive": self.alive,
            "queued": self.queued,
            "running": self.running,
            "completed": self.completed,
            "failed": self.failed,
            "thread_pool_size": self.thread_pool_size,
            "uptime_seconds": self.uptime,
        }


class SchedulerEvents:
    """Event name constants published by the scheduler."""

    TASK_SUBMITTED = "scheduler.task.submitted"
    TASK_STARTED = "scheduler.task.started"
    TASK_COMPLETED = "scheduler.task.completed"
    TASK_FAILED = "scheduler.task.failed"
    TASK_CANCELLED = "scheduler.task.cancelled"
    TASK_RETRYING = "scheduler.task.retrying"
    SCHEDULER_STARTED = "scheduler.started"
    SCHEDULER_STOPPED = "scheduler.stopped"
    SCHEDULER_HEARTBEAT = "scheduler.heartbeat"


class SystemScheduler:
    """System-level task scheduler with priority queue, cron support,
    thread pool execution, and persistence.

    Usage::

        scheduler = SystemScheduler(event_bus=bus)

        # One-shot task
        scheduler.schedule_once("my-task", my_func, delay=5.0)

        # Recurring interval
        scheduler.schedule_interval("heartbeat", ping, interval=30.0)

        # Cron task
        scheduler.schedule_cron("daily-cleanup", clean, "0 3 * * *")

        scheduler.start()
        # ...
        scheduler.stop()
    """

    def __init__(
        self,
        event_bus: EventBus | None = None,
        max_workers: int = 4,
        persistence_path: str | Path | None = None,
        poll_interval: float = 0.1,
    ) -> None:
        self._event_bus = event_bus
        self._max_workers = max_workers
        self._poll_interval = poll_interval
        self._persistence_path = Path(persistence_path) if persistence_path else None

        self._tasks: dict[str, Task] = {}
        self._queue: queue.PriorityQueue = queue.PriorityQueue()
        self._running_tasks: dict[str, Task] = {}

        self._lock = threading.RLock()
        self._running = False
        self._started_at: float = 0.0

        self._dispatch_thread: threading.Thread | None = None
        self._worker_threads: list[threading.Thread] = []
        self._work_queue: queue.Queue = queue.Queue()

        self._metrics_lock = threading.Lock()
        self._completed_count = 0
        self._failed_count = 0

        self._callable_registry: dict[str, Callable[..., Any]] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the scheduler's dispatch loop and worker threads."""
        with self._lock:
            if self._running:
                return
            self._running = True
            self._started_at = time.time()

        self._restore_persisted_tasks()

        self._dispatch_thread = threading.Thread(
            target=self._dispatch_loop, daemon=True, name="sched-dispatch"
        )
        self._dispatch_thread.start()

        for i in range(self._max_workers):
            t = threading.Thread(
                target=self._worker_loop, daemon=True, name=f"sched-worker-{i}"
            )
            t.start()
            self._worker_threads.append(t)

        self._publish(SchedulerEvents.SCHEDULER_STARTED)

    def stop(self, timeout: float = 5.0) -> None:
        """Gracefully stop the scheduler, persisting pending tasks."""
        with self._lock:
            if not self._running:
                return
            self._running = False

        self._persist_tasks()
        self._publish(SchedulerEvents.SCHEDULER_STOPPED)

    def schedule_once(
        self,
        name: str,
        callable: Callable[..., Any],
        delay: float = 0.0,
        priority: Priority = Priority.NORMAL,
        args: tuple[Any, ...] = (),
        kwargs: dict[str, Any] | None = None,
        max_retries: int = 0,
        retry_delay: float = 1.0,
        tags: set[str] | None = None,
    ) -> Task:
        """Schedule a one-shot task after an optional delay (seconds)."""
        scheduled_at = time.time() + delay
        task = Task(
            name=name,
            callable=callable,
            args=args,
            kwargs=kwargs or {},
            trigger=TaskTrigger.ONCE,
            priority=priority,
            status=TaskStatus.SCHEDULED,
            scheduled_at=scheduled_at,
            max_retries=max_retries,
            retry_delay_seconds=retry_delay,
            tags=tags or set(),
        )
        return self._submit(task)

    def schedule_interval(
        self,
        name: str,
        callable: Callable[..., Any],
        interval: float,
        delay: float = 0.0,
        priority: Priority = Priority.NORMAL,
        args: tuple[Any, ...] = (),
        kwargs: dict[str, Any] | None = None,
        max_retries: int = 0,
        retry_delay: float = 1.0,
        tags: set[str] | None = None,
    ) -> Task:
        """Schedule a recurring interval task."""
        scheduled_at = time.time() + delay
        task = Task(
            name=name,
            callable=callable,
            args=args,
            kwargs=kwargs or {},
            trigger=TaskTrigger.INTERVAL,
            interval_seconds=interval,
            priority=priority,
            status=TaskStatus.SCHEDULED,
            scheduled_at=scheduled_at,
            max_retries=max_retries,
            retry_delay_seconds=retry_delay,
            tags=tags or set(),
        )
        return self._submit(task)

    def schedule_cron(
        self,
        name: str,
        callable: Callable[..., Any],
        cron_expression: str,
        priority: Priority = Priority.NORMAL,
        args: tuple[Any, ...] = (),
        kwargs: dict[str, Any] | None = None,
        max_retries: int = 0,
        retry_delay: float = 1.0,
        tags: set[str] | None = None,
    ) -> Task:
        """Schedule a task using a standard 5-field cron expression."""
        parsed = CronExpression(cron_expression)
        next_run = parsed.next_after()
        if next_run is None:
            raise CronParseError(f"Cron expression '{cron_expression}' never matches")
        task = Task(
            name=name,
            callable=callable,
            args=args,
            kwargs=kwargs or {},
            trigger=TaskTrigger.CRON,
            cron_expression=cron_expression,
            priority=priority,
            status=TaskStatus.SCHEDULED,
            scheduled_at=next_run,
            max_retries=max_retries,
            retry_delay_seconds=retry_delay,
            tags=tags or set(),
        )
        return self._submit(task)

    def cancel(self, task_id: str) -> bool:
        """Cancel a scheduled or pending task. Returns ``True`` if cancelled."""
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None or task.status not in (TaskStatus.PENDING, TaskStatus.SCHEDULED):
                return False
            task.status = TaskStatus.CANCELLED
        self._publish(SchedulerEvents.TASK_CANCELLED, task_id=task_id)
        return True

    def get_task(self, task_id: str) -> Task | None:
        with self._lock:
            return self._tasks.get(task_id)

    def list_tasks(
        self,
        status: TaskStatus | None = None,
        tags: set[str] | None = None,
    ) -> list[Task]:
        with self._lock:
            tasks = list(self._tasks.values())
        if status is not None:
            tasks = [t for t in tasks if t.status == status]
        if tags:
            tasks = [t for t in tasks if tags & t.tags]
        return tasks

    def health(self) -> SchedulerHealth:
        """Return a health snapshot for the Health Monitor."""
        with self._lock:
            queued = self._queue.qsize()
            running = len(self._running_tasks)
        with self._metrics_lock:
            completed = self._completed_count
            failed = self._failed_count
        return SchedulerHealth(
            alive=self._running,
            queued=queued,
            running=running,
            completed=completed,
            failed=failed,
            thread_pool_size=self._max_workers,
            uptime=time.time() - self._started_at if self._started_at else 0.0,
        )

    def register_callable(self, name: str, callable: Callable[..., Any]) -> None:
        """Register a named callable for task deserialization."""
        with self._lock:
            self._callable_registry[name] = callable

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _submit(self, task: Task) -> Task:
        task.status = TaskStatus.SCHEDULED
        with self._lock:
            self._tasks[task.id] = task
            self._queue.put((task.priority.value * -1, task.scheduled_at or 0.0, task.id))
        self._publish(SchedulerEvents.TASK_SUBMITTED, task_id=task.id, name=task.name)
        return task

    def _dispatch_loop(self) -> None:
        """Main loop: check for due tasks and submit them to the work queue."""
        while self._running:
            now = time.time()
            due: list[Task] = []
            with self._lock:
                ids_to_remove: list[str] = []
                for task_id, task in self._tasks.items():
                    if task.is_due(now):
                        due.append(task)
                        ids_to_remove.append(task_id)
                for tid in ids_to_remove:
                    self._tasks.pop(tid, None)

            due.sort(key=lambda t: t.priority.value, reverse=True)
            for task in due:
                task.status = TaskStatus.RUNNING
                task.started_at = time.time()
                with self._lock:
                    self._running_tasks[task.id] = task
                self._work_queue.put(task)
                self._publish(SchedulerEvents.TASK_STARTED, task_id=task.id, name=task.name)

            self._publish_heartbeat()
            time.sleep(self._poll_interval)

    def _worker_loop(self) -> None:
        """Worker: pull tasks from the work queue, execute, and handle results."""
        while self._running:
            try:
                task: Task = self._work_queue.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                result = task.callable(*task.args, **task.kwargs)
                task.result = result
                task.status = TaskStatus.COMPLETED
                task.completed_at = time.time()
                with self._metrics_lock:
                    self._completed_count += 1
                self._publish(SchedulerEvents.TASK_COMPLETED, task_id=task.id, name=task.name)

                if task.is_recurring:
                    self._reschedule(task)

            except Exception as exc:
                task.error = str(exc)
                if task.retry_count < task.max_retries:
                    task.retry_count += 1
                    task.status = TaskStatus.SCHEDULED
                    task.scheduled_at = time.time() + task.retry_delay_seconds
                    self._publish(
                        SchedulerEvents.TASK_RETRYING,
                        task_id=task.id,
                        name=task.name,
                        attempt=task.retry_count,
                        max_retries=task.max_retries,
                    )
                    with self._lock:
                        self._tasks[task.id] = task
                        self._queue.put(
                            (task.priority.value * -1, task.scheduled_at or 0.0, task.id)
                        )
                else:
                    task.status = TaskStatus.FAILED
                    task.completed_at = time.time()
                    with self._metrics_lock:
                        self._failed_count += 1
                    self._publish(SchedulerEvents.TASK_FAILED, task_id=task.id, name=task.name, error=task.error)

            finally:
                with self._lock:
                    self._running_tasks.pop(task.id, None)
                self._work_queue.task_done()

    def _reschedule(self, task: Task) -> None:
        """Reschedule a recurring task for its next run."""
        if task.trigger == TaskTrigger.INTERVAL:
            task.scheduled_at = time.time() + task.interval_seconds
        elif task.trigger == TaskTrigger.CRON and task.cron_expression:
            parsed = CronExpression(task.cron_expression)
            task.scheduled_at = parsed.next_after(time.time()) or (time.time() + 3600)
        task.status = TaskStatus.SCHEDULED
        task.retry_count = 0
        task.started_at = None
        task.completed_at = None
        task.result = None
        task.error = None
        with self._lock:
            self._tasks[task.id] = task
            self._queue.put(
                (task.priority.value * -1, task.scheduled_at or 0.0, task.id)
            )

    def _publish_heartbeat(self) -> None:
        """Periodically publish scheduler heartbeat (every ~5 seconds)."""
        if not hasattr(self, "_last_heartbeat"):
            self._last_heartbeat = 0.0
        now = time.time()
        if now - self._last_heartbeat >= 5.0:
            self._last_heartbeat = now
            self._publish(SchedulerEvents.SCHEDULER_HEARTBEAT, health=self.health().to_dict())

    def _publish(self, event: str, **data: Any) -> None:
        if self._event_bus:
            self._event_bus.publish(event, **data)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _persist_tasks(self) -> None:
        """Save pending recurring tasks to disk so they survive restarts."""
        if not self._persistence_path:
            return
        with self._lock:
            recurring = [
                t.to_dict()
                for t in self._tasks.values()
                if t.is_recurring and t.status in (TaskStatus.SCHEDULED, TaskStatus.PENDING)
            ]
        try:
            self._persistence_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = str(self._persistence_path) + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"tasks": recurring, "version": 1}, f)
            os.replace(tmp, str(self._persistence_path))
        except Exception:
            JarvisLogger.exception("Scheduler: failed to persist tasks")

    def _restore_persisted_tasks(self) -> None:
        """Load persisted recurring tasks and reschedule them."""
        if not self._persistence_path or not self._persistence_path.exists():
            return
        try:
            with open(self._persistence_path, encoding="utf-8") as f:
                data = json.load(f)
            for task_data in data.get("tasks", []):
                task = Task.from_dict(task_data, self._callable_registry)
                task.status = TaskStatus.SCHEDULED
                if task.trigger == TaskTrigger.CRON and task.cron_expression:
                    parsed = CronExpression(task.cron_expression)
                    task.scheduled_at = parsed.next_after()
                elif task.trigger == TaskTrigger.INTERVAL:
                    task.scheduled_at = time.time() + task.interval_seconds
                if task.scheduled_at is not None:
                    self._submit(task)
        except Exception:
            JarvisLogger.exception("Scheduler: failed to restore persisted tasks")
