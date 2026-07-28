from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from app.core.event_bus import EventBus
from app.core.logger import JarvisLogger
from app.executive_controller.priority_manager import PriorityLevel, PriorityManager
from app.executive_controller.resource_manager import ResourceManager


class SubsystemStatus(Enum):
    UNREGISTERED = "unregistered"
    PENDING = "pending"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"


@dataclass
class SubsystemInfo:
    id: str
    name: str
    status: SubsystemStatus = SubsystemStatus.PENDING
    dependencies: list[str] = field(default_factory=list)
    priority: PriorityLevel = PriorityLevel.MEDIUM
    started_at: float | None = None
    stopped_at: float | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "status": self.status.value,
            "dependencies": list(self.dependencies),
            "priority": self.priority.name,
            "started_at": self.started_at,
            "stopped_at": self.stopped_at,
            "error": self.error,
        }


class ExecutiveController:
    """System-level orchestrator managing the startup/shutdown sequence of
    all subsystems.

    Subsystems register with their dependencies.  On start(), subsystems
    are launched in topological order (dependencies first).  On stop(),
    subsystems are shut down in reverse dependency order with a
    configurable timeout for graceful shutdown.  Events are published
    for every lifecycle transition.

    Integrates with:
      - EventBus (publishes lifecycle events)
      - ResourceManager (tracks per-subsystem resource usage)
      - PriorityManager (manages execution priorities)

    Thread-safe.
    """

    def __init__(
        self,
        event_bus: EventBus | None = None,
        shutdown_timeout: float = 5.0,
        state_preserved: bool = True,
    ) -> None:
        self._event_bus = event_bus
        self._shutdown_timeout = shutdown_timeout
        self._state_preserved = state_preserved

        self._lock = threading.RLock()
        self._subsystems: dict[str, SubsystemInfo] = {}
        self._startup_hooks: dict[str, Callable[[], None]] = {}
        self._shutdown_hooks: dict[str, Callable[[], None]] = {}
        self._running = False

        self.resource_manager = ResourceManager()
        self.priority_manager = PriorityManager()

        self._started_at: float = 0.0
        self._startup_order: list[str] = []

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def running(self) -> bool:
        return self._running

    @property
    def uptime(self) -> float:
        if not self._started_at:
            return 0.0
        return time.time() - self._started_at

    @property
    def startup_order(self) -> list[str]:
        with self._lock:
            return list(self._startup_order)

    @property
    def subsystem_count(self) -> int:
        with self._lock:
            return len(self._subsystems)

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(
        self,
        subsystem_id: str,
        name: str = "",
        dependencies: list[str] | None = None,
        startup: Callable[[], None] | None = None,
        shutdown: Callable[[], None] | None = None,
        priority: PriorityLevel = PriorityLevel.MEDIUM,
    ) -> None:
        with self._lock:
            if subsystem_id in self._subsystems:
                raise ValueError(f"Subsystem '{subsystem_id}' already registered")
            self._subsystems[subsystem_id] = SubsystemInfo(
                id=subsystem_id,
                name=name or subsystem_id,
                dependencies=dependencies or [],
                priority=priority,
            )
            if startup:
                self._startup_hooks[subsystem_id] = startup
            if shutdown:
                self._shutdown_hooks[subsystem_id] = shutdown
            self.priority_manager.set_priority(subsystem_id, priority)
            self.resource_manager.track(subsystem_id)

    def unregister(self, subsystem_id: str) -> bool:
        with self._lock:
            self._subsystems.pop(subsystem_id, None)
            self._startup_hooks.pop(subsystem_id, None)
            self._shutdown_hooks.pop(subsystem_id, None)
            self.priority_manager.unset_priority(subsystem_id)
            self.resource_manager.untrack(subsystem_id)
            return True

    def get_subsystem(self, subsystem_id: str) -> SubsystemInfo | None:
        with self._lock:
            return self._subsystems.get(subsystem_id)

    def get_all_subsystems(self) -> list[SubsystemInfo]:
        with self._lock:
            return list(self._subsystems.values())

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> list[str]:
        with self._lock:
            if self._running:
                return list(self._startup_order)
            self._running = True
            self._started_at = time.time()

        self._publish_event("ec.starting")

        order = self._resolve_startup_order()
        failed: list[str] = []
        started: list[str] = []

        for sid in order:
            info = self._subsystems.get(sid)
            if info is None:
                continue
            try:
                self._set_status(sid, SubsystemStatus.STARTING)
                self._publish_event("ec.subsystem.starting", subsystem_id=sid)

                hook = self._startup_hooks.get(sid)
                if hook:
                    hook()

                self._set_status(sid, SubsystemStatus.RUNNING, started_at=time.time())
                self._publish_event("ec.subsystem.started", subsystem_id=sid)
                started.append(sid)
            except Exception as exc:
                msg = f"Subsystem '{sid}' startup failed: {exc}"
                JarvisLogger.exception(msg)
                self._set_status(sid, SubsystemStatus.FAILED, error=msg)
                self._publish_event("ec.subsystem.failed", subsystem_id=sid, error=msg)
                failed.append(sid)

        self._startup_order = started
        if failed:
            self._publish_event("ec.startup_partial", failed=failed, started=started)
        else:
            self._publish_event("ec.started")
        return failed

    def stop(self) -> list[str]:
        with self._lock:
            if not self._running:
                return []
            self._running = False

        self._publish_event("ec.shutdown_starting")

        order = list(reversed(self._startup_order))
        failed: list[str] = []
        deadline = time.time() + self._shutdown_timeout

        for sid in order:
            info = self._subsystems.get(sid)
            if info is None:
                continue
            remaining = deadline - time.time()
            if remaining <= 0:
                msg = f"Shutdown timeout exceeded, forcing stop for '{sid}'"
                JarvisLogger.warning(msg)
                self._set_status(sid, SubsystemStatus.STOPPED, stopped_at=time.time())
                self._publish_event("ec.subsystem.force_stopped", subsystem_id=sid)
                continue
            try:
                self._set_status(sid, SubsystemStatus.STOPPING)
                self._publish_event("ec.subsystem.stopping", subsystem_id=sid)

                hook = self._shutdown_hooks.get(sid)
                if hook:
                    hook()

                self._set_status(sid, SubsystemStatus.STOPPED, stopped_at=time.time())
                self._publish_event("ec.subsystem.stopped", subsystem_id=sid)
            except Exception as exc:
                msg = f"Subsystem '{sid}' shutdown failed: {exc}"
                JarvisLogger.exception(msg)
                self._set_status(sid, SubsystemStatus.FAILED, error=msg)
                self._publish_event("ec.subsystem.shutdown_failed", subsystem_id=sid, error=msg)
                failed.append(sid)

        if failed:
            self._publish_event("ec.shutdown_partial", failed=failed)
        else:
            self._publish_event("ec.shutdown_complete")
        return failed

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _resolve_startup_order(self) -> list[str]:
        with self._lock:
            graph: dict[str, set[str]] = {}
            for sid, info in self._subsystems.items():
                graph[sid] = set(info.dependencies)
            order: list[str] = []
            visited: set[str] = set()
            temp_mark: set[str] = set()

            def _visit(node: str) -> None:
                if node in temp_mark:
                    raise ValueError(f"Circular dependency detected involving '{node}'")
                if node not in visited:
                    temp_mark.add(node)
                    for dep in graph.get(node, set()):
                        if dep not in graph and dep not in self._subsystems:
                            continue
                        _visit(dep)
                    temp_mark.discard(node)
                    visited.add(node)
                    order.append(node)

            for sid in list(graph.keys()):
                if sid not in visited:
                    _visit(sid)
            return order

    def _set_status(
        self,
        subsystem_id: str,
        status: SubsystemStatus,
        started_at: float | None = None,
        stopped_at: float | None = None,
        error: str | None = None,
    ) -> None:
        with self._lock:
            info = self._subsystems.get(subsystem_id)
            if info is None:
                return
            info.status = status
            if started_at is not None:
                info.started_at = started_at
            if stopped_at is not None:
                info.stopped_at = stopped_at
            if error is not None:
                info.error = error

    def _publish_event(self, event: str, **data: Any) -> None:
        if self._event_bus:
            try:
                self._event_bus.publish(event, **data)
            except Exception:
                JarvisLogger.exception("ExecutiveController: event publish failed")

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    def health(self) -> dict[str, Any]:
        with self._lock:
            total = len(self._subsystems)
            running_count = sum(
                1 for s in self._subsystems.values() if s.status == SubsystemStatus.RUNNING
            )
            failed_count = sum(
                1 for s in self._subsystems.values() if s.status == SubsystemStatus.FAILED
            )
        return {
            "alive": self._running,
            "uptime_seconds": self.uptime,
            "subsystems": {
                "total": total,
                "running": running_count,
                "failed": failed_count,
            },
            "shutdown_timeout": self._shutdown_timeout,
            "state_preserved": self._state_preserved,
            "resource_usage": self.resource_manager.get_system_usage().to_dict(),
        }
