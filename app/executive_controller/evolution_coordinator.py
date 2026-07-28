from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from app.core.event_bus import EventBus
from app.core.logger import JarvisLogger


class EvolutionStatus(Enum):
    IDLE = "idle"
    PLANNING = "planning"
    WINDOW_OPEN = "window_open"
    EVOLVING = "evolving"
    VERIFYING = "verifying"
    COMMITTED = "committed"
    ROLLING_BACK = "rolling_back"
    FAILED = "failed"


@dataclass
class EvolutionPlan:
    component_id: str
    description: str = ""
    version: str = ""
    created_at: float = field(default_factory=time.time)
    status: EvolutionStatus = EvolutionStatus.PLANNING
    dependents: list[str] = field(default_factory=list)
    backup_version: str = ""
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "component_id": self.component_id,
            "description": self.description,
            "version": self.version,
            "created_at": self.created_at,
            "status": self.status.value,
            "dependents": list(self.dependents),
            "backup_version": self.backup_version,
            "error": self.error,
        }


@dataclass
class EvolutionWindow:
    component_id: str
    opened_at: float = field(default_factory=time.time)
    closes_at: float = 0.0
    duration_seconds: float = 60.0
    active: bool = False
    dependents_completed: list[str] = field(default_factory=list)

    @property
    def is_expired(self) -> bool:
        return time.time() > self.closes_at

    @property
    def remaining(self) -> float:
        remaining = self.closes_at - time.time()
        return max(0.0, remaining)

    def to_dict(self) -> dict[str, Any]:
        return {
            "component_id": self.component_id,
            "opened_at": self.opened_at,
            "closes_at": self.closes_at,
            "duration_seconds": self.duration_seconds,
            "active": self.active,
            "is_expired": self.is_expired,
            "remaining_seconds": self.remaining,
        }


class EvolutionCoordinator:
    """Coordinates the safe evolution of system components.

    Determines safe evolution windows, checks for running dependents,
    manages hot-reload of live components, and triggers rollback on
    failure.

    Thread-safe.
    """

    def __init__(
        self,
        event_bus: EventBus | None = None,
        default_window_duration: float = 60.0,
        verification_timeout: float = 30.0,
    ) -> None:
        self._event_bus = event_bus
        self._default_window_duration = default_window_duration
        self._verification_timeout = verification_timeout

        self._lock = threading.RLock()
        self._status: EvolutionStatus = EvolutionStatus.IDLE
        self._active_plan: EvolutionPlan | None = None
        self._active_window: EvolutionWindow | None = None
        self._dependency_map: dict[str, list[str]] = {}
        self._hot_swap_hooks: dict[str, Callable[[], None]] = {}
        self._rollback_hooks: dict[str, Callable[[], None]] = {}
        self._completed_evolutions: list[EvolutionPlan] = []
        self._blocked_components: set[str] = set()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def status(self) -> EvolutionStatus:
        return self._status

    @property
    def active_plan(self) -> EvolutionPlan | None:
        return self._active_plan

    @property
    def active_window(self) -> EvolutionWindow | None:
        return self._active_window

    # ------------------------------------------------------------------
    # Dependency tracking
    # ------------------------------------------------------------------

    def register_dependency(self, component_id: str, depends_on: str) -> None:
        with self._lock:
            if depends_on not in self._dependency_map:
                self._dependency_map[depends_on] = []
            if component_id not in self._dependency_map[depends_on]:
                self._dependency_map[depends_on].append(component_id)

    def unregister_dependency(self, component_id: str, depends_on: str) -> bool:
        with self._lock:
            deps = self._dependency_map.get(depends_on)
            if deps and component_id in deps:
                deps.remove(component_id)
                return True
            return False

    def get_dependents(self, component_id: str) -> list[str]:
        with self._lock:
            return list(self._dependency_map.get(component_id, []))

    def register_hot_swap_hook(self, component_id: str, hook: Callable[[], None]) -> None:
        with self._lock:
            self._hot_swap_hooks[component_id] = hook

    def register_rollback_hook(self, component_id: str, hook: Callable[[], None]) -> None:
        with self._lock:
            self._rollback_hooks[component_id] = hook

    # ------------------------------------------------------------------
    # Evolution window
    # ------------------------------------------------------------------

    def open_window(
        self,
        component_id: str,
        duration: float | None = None,
    ) -> EvolutionWindow:
        with self._lock:
            if self._status not in (EvolutionStatus.IDLE, EvolutionStatus.PLANNING):
                raise RuntimeError(
                    f"Cannot open evolution window: current status is {self._status.value}"
                )

            dependents = self.get_dependents(component_id)
            window = EvolutionWindow(
                component_id=component_id,
                duration_seconds=duration or self._default_window_duration,
                closes_at=time.time() + (duration or self._default_window_duration),
                active=True,
                dependents_completed=list(dependents),
            )
            self._active_window = window
            self._status = EvolutionStatus.WINDOW_OPEN

        self._publish("ec.evolution.window_open", window=window.to_dict())
        return window

    def close_window(self) -> None:
        with self._lock:
            if self._active_window:
                self._active_window.active = False
            self._active_window = None
            if self._status == EvolutionStatus.WINDOW_OPEN:
                self._status = EvolutionStatus.IDLE

        self._publish("ec.evolution.window_closed")

    def window_available(self, component_id: str) -> bool:
        with self._lock:
            if self._status not in (EvolutionStatus.IDLE, EvolutionStatus.PLANNING):
                return False
            if component_id in self._blocked_components:
                return False
            return True

    # ------------------------------------------------------------------
    # Evolution workflow
    # ------------------------------------------------------------------

    def plan(
        self,
        component_id: str,
        description: str = "",
        version: str = "",
    ) -> EvolutionPlan:
        with self._lock:
            if not self.window_available(component_id):
                raise RuntimeError(f"Cannot plan evolution for '{component_id}': window not available")

            plan = EvolutionPlan(
                component_id=component_id,
                description=description,
                version=version,
            )
            plan.dependents = self.get_dependents(component_id)
            self._active_plan = plan
            self._status = EvolutionStatus.PLANNING

        self._publish("ec.evolution.planned", plan=plan.to_dict())
        return plan

    def evolve(self) -> EvolutionPlan | None:
        with self._lock:
            plan = self._active_plan
            if plan is None:
                return None
            if self._status != EvolutionStatus.WINDOW_OPEN:
                raise RuntimeError(
                    f"Cannot evolve: evolution window not open (status={self._status.value})"
                )

            window = self._active_window
            if window and window.is_expired:
                self._status = EvolutionStatus.FAILED
                plan.status = EvolutionStatus.FAILED
                plan.error = "Evolution window expired"
                self._publish("ec.evolution.failed", plan=plan.to_dict(), reason="window_expired")
                return plan

            self._status = EvolutionStatus.EVOLVING
            plan.status = EvolutionStatus.EVOLVING

        self._publish("ec.evolution.started", plan=plan.to_dict() if plan else {})

        with self._lock:
            plan = self._active_plan
            if plan is None:
                return None
            cid = plan.component_id
            hook = self._hot_swap_hooks.get(cid)
            if hook:
                try:
                    hook()
                    self._status = EvolutionStatus.VERIFYING
                    plan.status = EvolutionStatus.VERIFYING
                    self._publish("ec.evolution.hot_swapped", component_id=cid)
                except Exception as exc:
                    self._status = EvolutionStatus.FAILED
                    plan.status = EvolutionStatus.FAILED
                    plan.error = str(exc)
                    self._publish("ec.evolution.failed", component_id=cid, error=str(exc))

        return plan

    def commit(self) -> EvolutionPlan | None:
        with self._lock:
            plan = self._active_plan
            if plan is None:
                return None
            if self._status != EvolutionStatus.VERIFYING:
                raise RuntimeError(
                    f"Cannot commit evolution: status is {self._status.value}"
                )

            plan.status = EvolutionStatus.COMMITTED
            self._completed_evolutions.append(plan)
            self._active_plan = None
            self._status = EvolutionStatus.IDLE

        self._publish("ec.evolution.committed", component_id=plan.component_id if plan else "")
        return plan

    def rollback(self, reason: str = "") -> EvolutionPlan | None:
        with self._lock:
            plan = self._active_plan
            if plan is None:
                return None

            plan.status = EvolutionStatus.ROLLING_BACK
            self._status = EvolutionStatus.ROLLING_BACK

            cid = plan.component_id
            hook = self._rollback_hooks.get(cid)
            if hook:
                try:
                    hook()
                except Exception as exc:
                    JarvisLogger.exception(f"Rollback hook failed for '{cid}': {exc}")

            plan.error = reason or "Rolled back"
            plan.status = EvolutionStatus.FAILED
            self._completed_evolutions.append(plan)
            self._active_plan = None
            self._status = EvolutionStatus.IDLE

        self._publish("ec.evolution.rolled_back", component_id=plan.component_id if plan else "", reason=reason)
        return plan

    def block_component(self, component_id: str) -> None:
        with self._lock:
            self._blocked_components.add(component_id)

    def unblock_component(self, component_id: str) -> bool:
        with self._lock:
            if component_id in self._blocked_components:
                self._blocked_components.discard(component_id)
                return True
            return False

    def is_blocked(self, component_id: str) -> bool:
        with self._lock:
            return component_id in self._blocked_components

    def get_completed_evolutions(self) -> list[EvolutionPlan]:
        with self._lock:
            return list(self._completed_evolutions)

    def _publish(self, event: str, **data: Any) -> None:
        if self._event_bus:
            try:
                self._event_bus.publish(event, **data)
            except Exception:
                JarvisLogger.exception("EvolutionCoordinator: event publish failed")

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    def health(self) -> dict[str, Any]:
        with self._lock:
            return {
                "status": self._status.value,
                "has_active_plan": self._active_plan is not None,
                "has_active_window": self._active_window is not None,
                "registered_hooks": len(self._hot_swap_hooks),
                "registered_rollback_hooks": len(self._rollback_hooks),
                "completed_evolutions": len(self._completed_evolutions),
                "blocked_components": len(self._blocked_components),
                "dependencies_tracked": sum(len(deps) for deps in self._dependency_map.values()),
            }
