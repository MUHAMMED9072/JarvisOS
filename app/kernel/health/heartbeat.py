from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from threading import Lock
from typing import Any


class HeartbeatStatus(Enum):
    ALIVE = "alive"
    DEGRADED = "degraded"
    DOWN = "down"


@dataclass
class Heartbeat:
    component_id: str
    status: HeartbeatStatus = HeartbeatStatus.ALIVE
    timestamp: float = field(default_factory=time.time)
    message: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_stale(self, timeout: float) -> bool:
        return time.time() - self.timestamp > timeout


class HeartbeatRegistry:
    """Stores the latest heartbeat from each monitored component."""

    def __init__(self, default_timeout: float = 30.0) -> None:
        self._default_timeout = default_timeout
        self._heartbeats: dict[str, Heartbeat] = {}
        self._lock = Lock()

    @property
    def default_timeout(self) -> float:
        return self._default_timeout

    def register(self, component_id: str) -> None:
        with self._lock:
            if component_id not in self._heartbeats:
                self._heartbeats[component_id] = Heartbeat(
                    component_id=component_id,
                    status=HeartbeatStatus.ALIVE,
                )

    def unregister(self, component_id: str) -> bool:
        with self._lock:
            return self._heartbeats.pop(component_id, None) is not None

    def beat(
        self,
        component_id: str,
        status: HeartbeatStatus = HeartbeatStatus.ALIVE,
        message: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> Heartbeat:
        hb = Heartbeat(
            component_id=component_id,
            status=status,
            message=message,
            metadata=metadata or {},
        )
        with self._lock:
            self._heartbeats[component_id] = hb
        return hb

    def get(self, component_id: str) -> Heartbeat | None:
        with self._lock:
            return self._heartbeats.get(component_id)

    def is_alive(self, component_id: str) -> bool:
        hb = self.get(component_id)
        if hb is None:
            return False
        return hb.status == HeartbeatStatus.ALIVE and not hb.is_stale(self._default_timeout)

    def get_stale(self) -> list[Heartbeat]:
        with self._lock:
            return [
                hb for hb in self._heartbeats.values()
                if hb.is_stale(self._default_timeout)
            ]

    def get_all(self) -> list[Heartbeat]:
        with self._lock:
            return list(self._heartbeats.values())

    def count(self) -> int:
        with self._lock:
            return len(self._heartbeats)

    def clear(self) -> None:
        with self._lock:
            self._heartbeats.clear()
