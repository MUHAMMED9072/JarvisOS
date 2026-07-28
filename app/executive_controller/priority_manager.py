from __future__ import annotations

import threading
from enum import IntEnum
from typing import Any


class PriorityLevel(IntEnum):
    CRITICAL = 0
    HIGH = 1
    MEDIUM = 2
    LOW = 3
    BACKGROUND = 4


class PriorityManager:
    """Manages execution priorities for components and agents.

    Supports priority inheritance so that a child agent spawned by a
    high-priority parent automatically inherits the same priority.

    Thread-safe.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._priorities: dict[str, PriorityLevel] = {}
        self._inheritance: dict[str, str] = {}

    def set_priority(self, component_id: str, priority: PriorityLevel) -> None:
        with self._lock:
            self._priorities[component_id] = priority

    def get_priority(self, component_id: str) -> PriorityLevel:
        with self._lock:
            resolved = self._resolve(component_id)
            return resolved

    def unset_priority(self, component_id: str) -> bool:
        with self._lock:
            if component_id in self._priorities:
                del self._priorities[component_id]
                return True
            return False

    def inherit(self, child_id: str, parent_id: str) -> None:
        with self._lock:
            self._inheritance[child_id] = parent_id

    def uninherit(self, child_id: str) -> bool:
        with self._lock:
            if child_id in self._inheritance:
                del self._inheritance[child_id]
                return True
            return False

    def get_children(self, parent_id: str) -> list[str]:
        with self._lock:
            return [cid for cid, pid in self._inheritance.items() if pid == parent_id]

    def get_all(self) -> dict[str, PriorityLevel]:
        with self._lock:
            return {cid: self._resolve(cid) for cid in list(self._priorities.keys())}

    def _resolve(self, component_id: str) -> PriorityLevel:
        visited: set[str] = set()
        current = component_id
        while current in self._inheritance:
            if current in visited:
                return PriorityLevel.MEDIUM
            visited.add(current)
            current = self._inheritance[current]
        return self._priorities.get(current, PriorityLevel.MEDIUM)

    def to_dict(self) -> dict[str, Any]:
        return {
            "priorities": {cid: p.name for cid, p in self.get_all().items()},
            "inheritance": dict(self._inheritance),
        }
