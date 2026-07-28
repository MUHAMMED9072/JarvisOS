from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from app.executive_controller.incident import Incident, IncidentSeverity, IncidentStore


class RecoveryStrategy(Enum):
    RESTART = "restart"
    ESCALATE = "escalate"
    DEGRADE = "degrade"
    IGNORE = "ignore"


class FailureSeverity(Enum):
    MINOR = "minor"
    MODERATE = "moderate"
    SEVERE = "severe"
    CRITICAL = "critical"


@dataclass
class RecoveryPolicy:
    strategy: RecoveryStrategy = RecoveryStrategy.RESTART
    max_retries: int = 3
    retry_delay_seconds: float = 1.0
    backoff_multiplier: float = 2.0
    failure_threshold: int = 2
    degrade_on_failure: bool = True


@dataclass
class ComponentStatus:
    component_id: str
    healthy: bool = True
    consecutive_failures: int = 0
    recovery_attempts: int = 0
    last_failure: float | None = None
    last_recovery: float | None = None
    degraded: bool = False
    escalated: bool = False
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "component_id": self.component_id,
            "healthy": self.healthy,
            "consecutive_failures": self.consecutive_failures,
            "recovery_attempts": self.recovery_attempts,
            "last_failure": self.last_failure,
            "last_recovery": self.last_recovery,
            "degraded": self.degraded,
            "escalated": self.escalated,
            "error": self.error,
        }


class FailureRecovery:
    """Monitors component health and performs automatic recovery.

    Recovery strategies:
      - RESTART: re-invoke the component's startup hook
      - ESCALATE: notify the escalation callback (e.g., Supervisor)
      - DEGRADE: mark component as degraded (reduced functionality)
      - IGNORE: no automatic action, just record the failure

    Thread-safe.
    """

    def __init__(
        self,
        incident_store: IncidentStore | None = None,
        default_policy: RecoveryPolicy | None = None,
    ) -> None:
        self._incident_store = incident_store or IncidentStore()
        self._default_policy = default_policy or RecoveryPolicy()

        self._lock = threading.RLock()
        self._policies: dict[str, RecoveryPolicy] = {}
        self._statuses: dict[str, ComponentStatus] = {}
        self._restart_hooks: dict[str, Callable[[], None]] = {}
        self._escalation_hooks: list[Callable[[str, str], None]] = []
        self._recovery_count: int = 0
        self._failure_count: int = 0

    def register(
        self,
        component_id: str,
        restart_hook: Callable[[], None] | None = None,
        policy: RecoveryPolicy | None = None,
    ) -> None:
        with self._lock:
            self._statuses[component_id] = ComponentStatus(component_id=component_id)
            if restart_hook:
                self._restart_hooks[component_id] = restart_hook
            if policy:
                self._policies[component_id] = policy

    def unregister(self, component_id: str) -> bool:
        with self._lock:
            self._statuses.pop(component_id, None)
            self._restart_hooks.pop(component_id, None)
            self._policies.pop(component_id, None)
            return True

    def register_escalation_hook(self, hook: Callable[[str, str], None]) -> None:
        with self._lock:
            self._escalation_hooks.append(hook)

    def report_failure(
        self,
        component_id: str,
        error: str = "",
        severity: FailureSeverity = FailureSeverity.MODERATE,
    ) -> str | None:
        with self._lock:
            self._failure_count += 1
            status = self._get_or_create_status(component_id)
            status.healthy = False
            status.consecutive_failures += 1
            status.last_failure = time.time()
            status.error = error

            incident = Incident(
                component_id=component_id,
                severity=self._to_incident_severity(severity),
                title=f"Component failure: {component_id}",
                description=error or "No error details",
            )
            self._incident_store.record(incident)

            policy = self._policies.get(component_id, self._default_policy)

            if status.consecutive_failures < policy.failure_threshold:
                return None

            return self._attempt_recovery(component_id, status, policy)

    def report_success(self, component_id: str) -> None:
        with self._lock:
            status = self._get_or_create_status(component_id)
            status.healthy = True
            status.consecutive_failures = 0
            status.error = None

    def get_status(self, component_id: str) -> ComponentStatus | None:
        with self._lock:
            return self._statuses.get(component_id)

    def get_all_statuses(self) -> list[ComponentStatus]:
        with self._lock:
            return list(self._statuses.values())

    def get_stats(self) -> dict[str, Any]:
        with self._lock:
            tracked = len(self._statuses)
            unhealthy = sum(1 for s in self._statuses.values() if not s.healthy)
            degraded = sum(1 for s in self._statuses.values() if s.degraded)
            return {
                "components_tracked": tracked,
                "unhealthy": unhealthy,
                "degraded": degraded,
                "recovery_attempts": self._recovery_count,
                "failures_recorded": self._failure_count,
            }

    def _attempt_recovery(
        self,
        component_id: str,
        status: ComponentStatus,
        policy: RecoveryPolicy,
    ) -> str | None:
        if policy.strategy == RecoveryStrategy.IGNORE:
            return None

        if status.recovery_attempts >= policy.max_retries:
            status.escalated = True
            self._do_escalate(component_id, status.error or "Max retries exceeded")
            return "escalated"

        delay = policy.retry_delay_seconds * (policy.backoff_multiplier ** status.recovery_attempts)
        status.recovery_attempts += 1
        self._recovery_count += 1

        if policy.strategy == RecoveryStrategy.RESTART:
            hook = self._restart_hooks.get(component_id)
            if hook:
                time.sleep(delay)
                try:
                    hook()
                    status.healthy = True
                    status.consecutive_failures = 0
                    status.last_recovery = time.time()
                    return "restarted"
                except Exception as exc:
                    status.error = f"Restart failed: {exc}"
                    return self._attempt_recovery(component_id, status, policy)
            else:
                status.escalated = True
                self._do_escalate(component_id, "No restart hook registered")
                return "escalated"

        if policy.strategy == RecoveryStrategy.DEGRADE:
            status.degraded = True
            return "degraded"

        if policy.strategy == RecoveryStrategy.ESCALATE:
            status.escalated = True
            self._do_escalate(component_id, status.error or "Escalated by policy")
            return "escalated"

        return None

    def _do_escalate(self, component_id: str, reason: str) -> None:
        for hook in self._escalation_hooks:
            try:
                hook(component_id, reason)
            except Exception:
                pass

    def _get_or_create_status(self, component_id: str) -> ComponentStatus:
        if component_id not in self._statuses:
            self._statuses[component_id] = ComponentStatus(component_id=component_id)
        return self._statuses[component_id]

    @staticmethod
    def _to_incident_severity(severity: FailureSeverity) -> IncidentSeverity:
        mapping = {
            FailureSeverity.MINOR: IncidentSeverity.INFO,
            FailureSeverity.MODERATE: IncidentSeverity.WARNING,
            FailureSeverity.SEVERE: IncidentSeverity.ERROR,
            FailureSeverity.CRITICAL: IncidentSeverity.CRITICAL,
        }
        return mapping.get(severity, IncidentSeverity.WARNING)

    def health(self) -> dict[str, Any]:
        stats = self.get_stats()
        return {
            "alive": True,
            "tracked_components": stats["components_tracked"],
            "unhealthy_components": stats["unhealthy"],
            "degraded_components": stats["degraded"],
            "recovery_attempts": stats["recovery_attempts"],
            "failures_recorded": stats["failures_recorded"],
        }
