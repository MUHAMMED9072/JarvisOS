from __future__ import annotations

import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TaskStatus(Enum):
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    SKIPPED = "skipped"


class TaskPriority(Enum):
    CRITICAL = 0
    HIGH = 1
    MEDIUM = 2
    LOW = 3


@dataclass
class ResourceEstimate:
    compute: float = 0.0
    memory_mb: float = 0.0
    time_seconds: float = 0.0
    network: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "compute": round(self.compute, 4),
            "memory_mb": round(self.memory_mb, 2),
            "time_seconds": round(self.time_seconds, 2),
            "network": round(self.network, 4),
        }


@dataclass
class Task:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    name: str = ""
    description: str = ""
    status: TaskStatus = TaskStatus.PENDING
    priority: TaskPriority = TaskPriority.MEDIUM
    depends_on: list[str] = field(default_factory=list)
    resource_estimate: ResourceEstimate = field(default_factory=ResourceEstimate)
    sub_tasks: list[str] = field(default_factory=list)
    agent_id: str = ""
    result: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    completed_at: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "status": self.status.value,
            "priority": self.priority.name,
            "depends_on": list(self.depends_on),
            "resource_estimate": self.resource_estimate.to_dict(),
            "sub_tasks": list(self.sub_tasks),
            "agent_id": self.agent_id,
            "result": dict(self.result),
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "metadata": dict(self.metadata),
        }


class TaskGraph:
    """Directed acyclic graph of tasks with dependency resolution.

    Supports:
      - Adding tasks with dependencies
      - Topological sort (Kahn's algorithm)
      - Parallelizable work identification (tasks with no inter-dependency)
      - Critical path analysis
      - Serialization/deserialization

    Thread-safe.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._tasks: dict[str, Task] = {}

    def add_task(self, task: Task) -> str:
        with self._lock:
            self._tasks[task.id] = task
            return task.id

    def get_task(self, task_id: str) -> Task | None:
        with self._lock:
            return self._tasks.get(task_id)

    def remove_task(self, task_id: str) -> bool:
        with self._lock:
            if task_id in self._tasks:
                del self._tasks[task_id]
                return True
            return False

    def list_tasks(self, status: TaskStatus | None = None) -> list[Task]:
        with self._lock:
            result = list(self._tasks.values())
            if status:
                result = [t for t in result if t.status == status]
            return sorted(result, key=lambda t: (t.priority.value, t.created_at))

    def count(self) -> int:
        with self._lock:
            return len(self._tasks)

    def clear(self) -> None:
        with self._lock:
            self._tasks.clear()

    def update_task_status(self, task_id: str, status: TaskStatus) -> bool:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return False
            task.status = status
            if status == TaskStatus.RUNNING:
                task.started_at = time.time()
            elif status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
                task.completed_at = time.time()
            return True

    # ------------------------------------------------------------------
    # Topological sort (Kahn's algorithm)
    # ------------------------------------------------------------------

    def topological_sort(self) -> list[list[str]]:
        """Return tasks in topological order, grouped by level.

        Each level contains tasks that can be executed in parallel.
        Returns a list of levels, where each level is a list of task IDs.
        """
        with self._lock:
            in_degree: dict[str, int] = {}
            adj: dict[str, list[str]] = {tid: [] for tid in self._tasks}
            for tid, task in self._tasks.items():
                in_degree.setdefault(tid, 0)
                for dep_id in task.depends_on:
                    if dep_id in self._tasks:
                        adj.setdefault(dep_id, []).append(tid)
                        in_degree[tid] = in_degree.get(tid, 0) + 1

            levels: list[list[str]] = []
            queue = deque([tid for tid, deg in in_degree.items() if deg == 0])

            while queue:
                level: list[str] = []
                for _ in range(len(queue)):
                    tid = queue.popleft()
                    level.append(tid)
                    for neighbor in adj.get(tid, []):
                        in_degree[neighbor] -= 1
                        if in_degree[neighbor] == 0:
                            queue.append(neighbor)
                levels.append(level)

            return levels

    # ------------------------------------------------------------------
    # Parallelizable work
    # ------------------------------------------------------------------

    def find_parallelizable(self) -> list[list[str]]:
        """Identify groups of tasks that can be executed in parallel.

        Each group contains tasks with no dependency chain between them.
        """
        levels = self.topological_sort()
        return [level for level in levels if len(level) > 1]

    # ------------------------------------------------------------------
    # Critical path analysis
    # ------------------------------------------------------------------

    def critical_path(self) -> list[str]:
        """Find the longest dependency chain (critical path).

        Returns list of task IDs from start to end of the critical path.
        """
        with self._lock:
            topo_levels = self.topological_sort()
            flat_order = [tid for level in topo_levels for tid in level]

            # earliest_finish per task
            ef: dict[str, float] = {}
            predecessor: dict[str, str | None] = {}

            for tid in flat_order:
                task = self._tasks.get(tid)
                duration = task.resource_estimate.time_seconds if task else 1.0
                best_pred = None
                best_ef = 0.0

                if task:
                    for dep_id in task.depends_on:
                        dep_ef = ef.get(dep_id, 0.0)
                        if dep_ef > best_ef:
                            best_ef = dep_ef
                            best_pred = dep_id

                ef[tid] = best_ef + duration
                predecessor[tid] = best_pred

            if not ef:
                return []

            # Trace back from the task with the latest EF
            end_task = max(ef, key=ef.get)
            path: list[str] = []
            current: str | None = end_task
            while current is not None:
                path.append(current)
                current = predecessor.get(current)
            path.reverse()
            return path

    def critical_path_duration(self) -> float:
        path = self.critical_path()
        if not path:
            return 0.0
        return sum(
            self._tasks[tid].resource_estimate.time_seconds
            if tid in self._tasks and self._tasks[tid].resource_estimate
            else 1.0
            for tid in path
        )

    # ------------------------------------------------------------------
    # Visualization
    # ------------------------------------------------------------------

    def to_text(self) -> str:
        """Produce a text-based visualization of the task graph."""
        with self._lock:
            if not self._tasks:
                return "Task graph: empty"

            lines: list[str] = ["Task Graph"]
            levels = self.topological_sort()

            for i, level in enumerate(levels):
                tasks_in_level = []
                for tid in level:
                    task = self._tasks.get(tid)
                    if task:
                        est = task.resource_estimate
                        tasks_in_level.append(
                            f"{task.name} ({est.time_seconds}s, {est.memory_mb}MB)"
                        )
                    else:
                        tasks_in_level.append(tid)
                indent = "  " * i if i > 0 else ""
                prefix = "└─ " if i > 0 else ""
                lines.append(f"{indent}{prefix}Level {i}: {', '.join(tasks_in_level)}")

            cp = self.critical_path()
            cp_names = []
            for tid in cp:
                task = self._tasks.get(tid)
                cp_names.append(task.name if task else tid)
            lines.append(f"\nCritical Path: {' → '.join(cp_names)}")
            lines.append(f"Critical Path Duration: {self.critical_path_duration():.1f}s")

            return "\n".join(lines)

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        with self._lock:
            return {
                "tasks": {tid: task.to_dict() for tid, task in self._tasks.items()},
                "levels": [list(level) for level in self.topological_sort()],
                "critical_path": self.critical_path(),
            }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TaskGraph:
        graph = cls()
        for tid, task_data in data.get("tasks", {}).items():
            est = ResourceEstimate(**task_data.get("resource_estimate", {}))
            task = Task(
                id=tid,
                name=task_data.get("name", ""),
                description=task_data.get("description", ""),
                status=TaskStatus(task_data.get("status", "pending")),
                priority=TaskPriority[task_data.get("priority", "MEDIUM")],
                depends_on=list(task_data.get("depends_on", [])),
                resource_estimate=est,
                sub_tasks=list(task_data.get("sub_tasks", [])),
                agent_id=task_data.get("agent_id", ""),
                result=dict(task_data.get("result", {})),
                created_at=task_data.get("created_at", 0.0),
                started_at=task_data.get("started_at"),
                completed_at=task_data.get("completed_at"),
                metadata=dict(task_data.get("metadata", {})),
            )
            graph._tasks[tid] = task
        return graph
