from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable

from app.kernel.health.probe import ProbeResult

import psutil

from app.core.event_bus import EventBus
from app.core.logger import JarvisLogger
from app.kernel.health.heartbeat import HeartbeatRegistry, HeartbeatStatus
from app.kernel.health.probe import ProbeRegistry, ProbeResult


class HealthState(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DOWN = "down"
    RECOVERED = "recovered"


@dataclass
class ResourceUsage:
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    memory_rss: int = 0
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "cpu_percent": self.cpu_percent,
            "memory_percent": self.memory_percent,
            "memory_rss_bytes": self.memory_rss,
            "timestamp": self.timestamp,
        }


@dataclass
class ComponentHealth:
    component_id: str
    state: HealthState = HealthState.HEALTHY
    alive: bool = True
    ready: bool = True
    liveness_result: ProbeResult | None = None
    readiness_result: ProbeResult | None = None
    resource_usage: ResourceUsage | None = None
    last_heartbeat_ago: float | None = None
    consecutive_failures: int = 0
    last_state_change: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "component_id": self.component_id,
            "state": self.state.value,
            "alive": self.alive,
            "ready": self.ready,
            "liveness_error": self.liveness_result.error if self.liveness_result else None,
            "readiness_error": self.readiness_result.error if self.readiness_result else None,
            "liveness_latency_ms": self.liveness_result.latency_ms if self.liveness_result else None,
            "readiness_latency_ms": self.readiness_result.latency_ms if self.readiness_result else None,
            "resource_usage": self.resource_usage.to_dict() if self.resource_usage else None,
            "last_heartbeat_ago": self.last_heartbeat_ago,
            "consecutive_failures": self.consecutive_failures,
            "last_state_change": self.last_state_change,
        }


@dataclass
class HealthEvent:
    component_id: str
    previous_state: HealthState
    new_state: HealthState
    timestamp: float = field(default_factory=time.time)
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "component_id": self.component_id,
            "previous_state": self.previous_state.value,
            "new_state": self.new_state.value,
            "timestamp": self.timestamp,
            "message": self.message,
        }


class HealthMonitor:
    """Periodically checks registered components for liveness, readiness,
    resource usage, and heartbeat freshness. Publishes health state
    transition events via the EventBus.
    """

    def __init__(
        self,
        event_bus: EventBus | None = None,
        check_interval: float = 30.0,
        failure_threshold: int = 2,
        heartbeat_timeout: float = 30.0,
        enable_resource_tracking: bool = True,
    ) -> None:
        self._event_bus = event_bus
        self._check_interval = check_interval
        self._failure_threshold = failure_threshold
        self._heartbeat_timeout = heartbeat_timeout
        self._enable_resource_tracking = enable_resource_tracking

        self._probe_registry = ProbeRegistry()
        self._heartbeat_registry = HeartbeatRegistry(default_timeout=heartbeat_timeout)
        self._component_states: dict[str, ComponentHealth] = {}
        self._previous_states: dict[str, HealthState] = {}

        self._lock = threading.RLock()
        self._running = False
        self._started_at: float = 0.0
        self._check_count = 0
        self._monitor_thread: threading.Thread | None = None
        self._custom_checks: dict[str, Callable[[], ProbeResult]] = {}

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def event_bus(self) -> EventBus | None:
        return self._event_bus

    @property
    def probe_registry(self) -> ProbeRegistry:
        return self._probe_registry

    @property
    def heartbeat_registry(self) -> HeartbeatRegistry:
        return self._heartbeat_registry

    @property
    def check_interval(self) -> float:
        return self._check_interval

    @property
    def failure_threshold(self) -> int:
        return self._failure_threshold

    @property
    def running(self) -> bool:
        return self._running

    @property
    def uptime(self) -> float:
        if not self._started_at:
            return 0.0
        return time.time() - self._started_at

    @property
    def check_count(self) -> int:
        return self._check_count

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register_component(
        self,
        component_id: str,
        liveness_check: Callable[[], ProbeResult] | None = None,
        readiness_check: Callable[[], ProbeResult] | None = None,
    ) -> None:
        from app.kernel.health.probe import LivenessProbe, ReadinessProbe

        with self._lock:
            lp = LivenessProbe(liveness_check) if liveness_check else None
            rp = ReadinessProbe(readiness_check) if readiness_check else None
            self._probe_registry.register(component_id, lp, rp)
            self._heartbeat_registry.register(component_id)
            if component_id not in self._component_states:
                state = HealthState.HEALTHY
                self._component_states[component_id] = ComponentHealth(
                    component_id=component_id, state=state
                )
                self._previous_states[component_id] = state

    def unregister_component(self, component_id: str) -> bool:
        with self._lock:
            probe_removed = self._probe_registry.unregister(component_id)
            hb_removed = self._heartbeat_registry.unregister(component_id)
            self._component_states.pop(component_id, None)
            self._previous_states.pop(component_id, None)
            self._custom_checks.pop(component_id, None)
            return probe_removed or hb_removed

    def register_custom_check(
        self, component_id: str, check: Callable[[], ProbeResult]
    ) -> None:
        with self._lock:
            self._custom_checks[component_id] = check

    # ------------------------------------------------------------------
    # Heartbeat helpers
    # ------------------------------------------------------------------

    def record_heartbeat(
        self,
        component_id: str,
        status: HeartbeatStatus = HeartbeatStatus.ALIVE,
        message: str = "",
    ) -> None:
        self._heartbeat_registry.beat(component_id, status=status, message=message)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        with self._lock:
            if self._running:
                return
            self._running = True
            self._started_at = time.time()

        self._monitor_thread = threading.Thread(
            target=self._monitor_loop,
            daemon=True,
            name="health-monitor",
        )
        self._monitor_thread.start()
        self._publish_event("health.monitor.started")

    def stop(self) -> None:
        with self._lock:
            self._running = False
        self._publish_event("health.monitor.stopped")

    def check_once(self) -> list[ComponentHealth]:
        """Run a single health check cycle on all registered components."""
        with self._lock:
            component_ids = list(self._component_states.keys())

        results: list[ComponentHealth] = []
        for cid in component_ids:
            health = self._check_component(cid)
            results.append(health)
        return results

    def get_component_health(self, component_id: str) -> ComponentHealth | None:
        with self._lock:
            return self._component_states.get(component_id)

    def get_all_component_health(self) -> list[ComponentHealth]:
        with self._lock:
            return list(self._component_states.values())

    def health(self) -> dict[str, Any]:
        """Self-probe: return health monitor's own health snapshot."""
        with self._lock:
            total = len(self._component_states)
            healthy = sum(
                1 for c in self._component_states.values() if c.state == HealthState.HEALTHY
            )
            degraded = sum(
                1 for c in self._component_states.values() if c.state == HealthState.DEGRADED
            )
            down = sum(
                1 for c in self._component_states.values() if c.state == HealthState.DOWN
            )

        return {
            "alive": self._running,
            "uptime_seconds": self.uptime,
            "check_interval": self._check_interval,
            "failure_threshold": self._failure_threshold,
            "heartbeat_timeout": self._heartbeat_timeout,
            "check_count": self._check_count,
            "components": {
                "total": total,
                "healthy": healthy,
                "degraded": degraded,
                "down": down,
            },
            "resource_usage": self._get_resource_usage().to_dict(),
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _monitor_loop(self) -> None:
        while self._running:
            try:
                self.check_once()
                self._check_count += 1
            except Exception:
                JarvisLogger.exception("HealthMonitor: error in check cycle")
            time.sleep(self._check_interval)

    def _check_component(self, component_id: str) -> ComponentHealth:
        custom = self._custom_checks.get(component_id)
        if custom is not None:
            lp_result = custom()
            rp_result = lp_result
        else:
            lp_result = self._probe_registry.probe_liveness(component_id)
            rp_result = self._probe_registry.probe_readiness(component_id)

        hb = self._heartbeat_registry.get(component_id)
        if hb is not None:
            heartbeat_ago = time.time() - hb.timestamp
        else:
            heartbeat_ago = None

        resources = self._get_component_resource_usage(component_id)

        alive = lp_result.alive
        ready = rp_result.ready and alive
        is_failing = not alive or not ready

        with self._lock:
            current = self._component_states.get(component_id)
            if current is None:
                return ComponentHealth(component_id=component_id)

            if is_failing:
                current.consecutive_failures += 1
            else:
                current.consecutive_failures = 0

            current.alive = alive
            current.ready = ready
            current.liveness_result = lp_result
            current.readiness_result = rp_result
            current.resource_usage = resources
            current.last_heartbeat_ago = heartbeat_ago

            new_state = self._determine_state(current)
            old_state = current.state
            if new_state != old_state:
                current.state = new_state
                current.last_state_change = datetime.now(timezone.utc).isoformat()
                self._publish_health_event(component_id, old_state, new_state, lp_result.error)

        return current

    def _determine_state(self, health: ComponentHealth) -> HealthState:
        if health.consecutive_failures >= self._failure_threshold:
            return HealthState.DOWN
        if health.consecutive_failures > 0:
            return HealthState.DEGRADED
        return HealthState.HEALTHY

    def _publish_health_event(
        self,
        component_id: str,
        old_state: HealthState,
        new_state: HealthState,
        error: str | None = None,
    ) -> None:
        message = ""
        if new_state == HealthState.DOWN:
            message = f"Component '{component_id}' is DOWN: {error or 'no heartbeat'}"
        elif new_state == HealthState.DEGRADED:
            message = f"Component '{component_id}' is DEGRADED"
        elif new_state == HealthState.RECOVERED:
            message = f"Component '{component_id}' has RECOVERED"

        ev = HealthEvent(
            component_id=component_id,
            previous_state=old_state,
            new_state=new_state,
            message=message,
        )
        self._publish_event("health.component.state_changed", event_data=ev.to_dict())
        if new_state == HealthState.DOWN:
            self._publish_event("health.component.down", component_id=component_id, error=error)
        elif new_state == HealthState.RECOVERED:
            self._publish_event("health.component.recovered", component_id=component_id)

    def _get_resource_usage(self) -> ResourceUsage:
        try:
            proc = psutil.Process()
            return ResourceUsage(
                cpu_percent=proc.cpu_percent(interval=0),
                memory_percent=proc.memory_percent(),
                memory_rss=proc.memory_info().rss,
            )
        except Exception:
            return ResourceUsage()

    def _get_component_resource_usage(self, component_id: str) -> ResourceUsage | None:
        if not self._enable_resource_tracking:
            return None
        try:
            proc = psutil.Process()
            return ResourceUsage(
                cpu_percent=proc.cpu_percent(interval=0),
                memory_percent=proc.memory_percent(),
                memory_rss=proc.memory_info().rss,
            )
        except Exception:
            return ResourceUsage()

    def _publish_event(self, event: str, **data: Any) -> None:
        if self._event_bus:
            self._event_bus.publish(event, **data)
