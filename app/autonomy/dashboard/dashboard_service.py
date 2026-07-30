from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AlertLevel(Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class AlertConfig:
    alert_id: str = ""
    name: str = ""
    metric: str = ""
    threshold: float = 0.0
    level: AlertLevel = AlertLevel.INFO
    enabled: bool = True
    created_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "alert_id": self.alert_id,
            "name": self.name,
            "metric": self.metric,
            "threshold": self.threshold,
            "level": self.level.value,
            "enabled": self.enabled,
            "created_at": self.created_at,
        }


@dataclass
class PolicyConfig:
    policy_id: str = ""
    name: str = ""
    description: str = ""
    scope: str = "system"
    enabled: bool = True
    parameters: dict[str, Any] = field(default_factory=dict)
    updated_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "name": self.name,
            "description": self.description,
            "scope": self.scope,
            "enabled": self.enabled,
            "parameters": dict(self.parameters),
            "updated_at": self.updated_at,
        }


@dataclass
class EvolutionRequest:
    request_id: str = ""
    target_component: str = ""
    description: str = ""
    risk_score: float = 0.0
    status: str = "pending"
    submitted_at: float = 0.0
    resolved_at: float = 0.0
    approved: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "target_component": self.target_component,
            "description": self.description,
            "risk_score": self.risk_score,
            "status": self.status,
            "submitted_at": self.submitted_at,
            "resolved_at": self.resolved_at,
            "approved": self.approved,
        }


@dataclass
class InterventionResult:
    intervention_id: str = ""
    action: str = ""
    target: str = ""
    status: str = ""
    message: str = ""
    timestamp: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "intervention_id": self.intervention_id,
            "action": self.action,
            "target": self.target,
            "status": self.status,
            "message": self.message,
            "timestamp": self.timestamp,
        }


@dataclass
class SystemSnapshot:
    snapshot_id: str = ""
    timestamp: float = 0.0
    agents: dict[str, Any] = field(default_factory=dict)
    projects: dict[str, Any] = field(default_factory=dict)
    workflows: dict[str, Any] = field(default_factory=dict)
    health: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "timestamp": self.timestamp,
            "agents": dict(self.agents),
            "projects": dict(self.projects),
            "workflows": dict(self.workflows),
            "health": dict(self.health),
            "metrics": dict(self.metrics),
        }


class DashboardService:
    """Provides human oversight dashboard capabilities.

    Aggregates system state from all subsystems, supports
    intervention controls, policy/alert configuration, and
    evolution request oversight. Designed to be consumed
    by a CLI or future web UI.
    """

    def __init__(
        self,
        graph_store: Any = None,
        event_bus: Any = None,
        project_manager: Any = None,
        orchestrator: Any = None,
        governance: Any = None,
        executive_controller: Any = None,
        evolution_manager: Any = None,
    ) -> None:
        self._graph = graph_store
        self._bus = event_bus
        self._pm = project_manager
        self._orchestrator = orchestrator
        self._gov = governance
        self._ec = executive_controller
        self._evolution = evolution_manager
        self._lock = threading.RLock()
        self._alerts: dict[str, AlertConfig] = {}
        self._policies: dict[str, PolicyConfig] = {}
        self._evolution_requests: dict[str, EvolutionRequest] = {}
        self._interventions: dict[str, InterventionResult] = {}
        self._snapshots: list[SystemSnapshot] = []
        self._system_health: dict[str, str] = {}

    # ── Snapshot / Monitoring ──────────────────────────────────────────

    def take_snapshot(self) -> SystemSnapshot:
        snapshot = SystemSnapshot(
            snapshot_id=uuid.uuid4().hex[:16],
            timestamp=time.time(),
        )

        if self._pm:
            try:
                snapshot.projects = self._pm.get_statistics()
            except Exception:
                pass
        if self._orchestrator:
            try:
                snapshot.workflows = self._orchestrator.get_statistics()
            except Exception:
                pass
        if self._ec:
            try:
                snapshot.health = self._ec.health()
            except Exception:
                pass
        if self._gov:
            try:
                if hasattr(self._gov, "get_statistics"):
                    snapshot.metrics["policies"] = (
                        self._gov.get_statistics().get("total_policies", 0)
                    )
            except Exception:
                pass

        snapshot.agents = {
            "total": len(self._get_connected_agents()),
            "healthy": sum(
                1 for s in self._system_health.values()
                if s == "healthy"
            ),
        }
        snapshot.health["overall"] = self._compute_overall_health()

        with self._lock:
            self._snapshots.append(snapshot)
            if len(self._snapshots) > 100:
                self._snapshots = self._snapshots[-100:]

        if self._bus:
            self._bus.publish("dashboard.snapshot.taken", snapshot.to_dict())
        return snapshot

    def get_latest_snapshot(self) -> SystemSnapshot | None:
        with self._lock:
            return self._snapshots[-1] if self._snapshots else None

    def _get_connected_agents(self) -> list[str]:
        agents: list[str] = []
        if self._orchestrator:
            try:
                agents = list(getattr(self._orchestrator, "_available_agents", []))
            except Exception:
                pass
        return agents

    def _compute_overall_health(self) -> str:
        if not self._system_health:
            return "unknown"
        if any(s == "critical" for s in self._system_health.values()):
            return "critical"
        if any(s == "degraded" for s in self._system_health.values()):
            return "degraded"
        if all(s == "healthy" for s in self._system_health.values()):
            return "healthy"
        return "degraded"

    def update_component_health(self, component: str, status: str) -> None:
        with self._lock:
            self._system_health[component] = status
        if self._bus:
            self._bus.publish("dashboard.health.updated", {
                "component": component,
                "status": status,
            })

    def get_component_health(self, component: str) -> str:
        with self._lock:
            return self._system_health.get(component, "unknown")

    def get_all_health(self) -> dict[str, str]:
        with self._lock:
            return dict(self._system_health)

    # ── Intervention Controls ─────────────────────────────────────────

    def execute_intervention(
        self,
        action: str,
        target: str,
        parameters: dict[str, Any] | None = None,
    ) -> InterventionResult:
        intervention_id = uuid.uuid4().hex[:16]
        result = InterventionResult(
            intervention_id=intervention_id,
            action=action,
            target=target,
            timestamp=time.time(),
        )

        status = "completed"
        message = ""

        try:
            if action == "pause_project" and self._pm:
                ok = self._pm.pause_project(target)
                status = "completed" if ok else "failed"
                message = f"Project {target} paused" if ok else f"Project {target} not found"

            elif action == "resume_project" and self._pm:
                ok = self._pm.resume_project(target)
                status = "completed" if ok else "failed"
                message = f"Project {target} resumed" if ok else f"Project {target} not found"

            elif action == "cancel_project" and self._pm:
                ok = self._pm.cancel_project(target)
                status = "completed" if ok else "failed"
                message = f"Project {target} cancelled" if ok else f"Project {target} not found"

            elif action == "pause_workflow" and self._orchestrator:
                ok = self._orchestrator.pause_workflow(target)
                status = "completed" if ok else "failed"
                message = f"Workflow {target} paused" if ok else f"Workflow {target} not found"

            elif action == "resume_workflow" and self._orchestrator:
                ok = self._orchestrator.resume_workflow(target)
                status = "completed" if ok else "failed"
                message = f"Workflow {target} resumed" if ok else f"Workflow {target} not found"

            elif action == "emergency_shutdown" and self._ec:
                if hasattr(self._ec, "emergency_shutdown"):
                    self._ec.emergency_shutdown()
                status = "completed"
                message = "Emergency shutdown initiated"

            elif action == "safe_mode" and self._ec:
                if hasattr(self._ec, "safe_mode"):
                    self._ec.safe_mode()
                status = "completed"
                message = "Safe mode activated"

            else:
                status = "failed"
                message = f"Unknown action '{action}' or missing dependency"

        except Exception as e:
            status = "failed"
            message = str(e)

        result.status = status
        result.message = message

        with self._lock:
            self._interventions[intervention_id] = result

        if self._bus:
            self._bus.publish("dashboard.intervention.executed", result.to_dict())
        return result

    def get_intervention(self, intervention_id: str) -> InterventionResult | None:
        with self._lock:
            return self._interventions.get(intervention_id)

    def list_interventions(self) -> list[InterventionResult]:
        with self._lock:
            return list(self._interventions.values())

    # ── Alert Configuration ────────────────────────────────────────────

    def create_alert_config(
        self,
        name: str,
        metric: str,
        threshold: float,
        level: AlertLevel = AlertLevel.WARNING,
    ) -> AlertConfig:
        alert = AlertConfig(
            alert_id=uuid.uuid4().hex[:16],
            name=name,
            metric=metric,
            threshold=threshold,
            level=level,
            created_at=time.time(),
        )
        with self._lock:
            self._alerts[alert.alert_id] = alert
        return alert

    def get_alert_config(self, alert_id: str) -> AlertConfig | None:
        with self._lock:
            return self._alerts.get(alert_id)

    def update_alert_config(
        self,
        alert_id: str,
        enabled: bool | None = None,
        threshold: float | None = None,
    ) -> bool:
        with self._lock:
            alert = self._alerts.get(alert_id)
            if not alert:
                return False
            if enabled is not None:
                alert.enabled = enabled
            if threshold is not None:
                alert.threshold = threshold
        return True

    def delete_alert_config(self, alert_id: str) -> bool:
        with self._lock:
            return self._alerts.pop(alert_id, None) is not None

    def list_alert_configs(self) -> list[AlertConfig]:
        with self._lock:
            return list(self._alerts.values())

    def evaluate_alerts(self, current_metrics: dict[str, float]) -> list[dict[str, Any]]:
        triggered: list[dict[str, Any]] = []
        with self._lock:
            for alert in self._alerts.values():
                if not alert.enabled:
                    continue
                value = current_metrics.get(alert.metric)
                if value is not None and value > alert.threshold:
                    triggered.append({
                        "alert_id": alert.alert_id,
                        "name": alert.name,
                        "metric": alert.metric,
                        "value": value,
                        "threshold": alert.threshold,
                        "level": alert.level.value,
                    })
        return triggered

    # ── Policy Configuration ───────────────────────────────────────────

    def create_policy_config(
        self,
        name: str,
        description: str = "",
        scope: str = "system",
        parameters: dict[str, Any] | None = None,
    ) -> PolicyConfig:
        policy = PolicyConfig(
            policy_id=uuid.uuid4().hex[:16],
            name=name,
            description=description,
            scope=scope,
            parameters=parameters or {},
            updated_at=time.time(),
        )
        with self._lock:
            self._policies[policy.policy_id] = policy
        return policy

    def get_policy_config(self, policy_id: str) -> PolicyConfig | None:
        with self._lock:
            return self._policies.get(policy_id)

    def update_policy_config(
        self,
        policy_id: str,
        enabled: bool | None = None,
        parameters: dict[str, Any] | None = None,
    ) -> bool:
        with self._lock:
            policy = self._policies.get(policy_id)
            if not policy:
                return False
            if enabled is not None:
                policy.enabled = enabled
            if parameters is not None:
                policy.parameters.update(parameters)
            policy.updated_at = time.time()
        return True

    def delete_policy_config(self, policy_id: str) -> bool:
        with self._lock:
            return self._policies.pop(policy_id, None) is not None

    def list_policy_configs(self) -> list[PolicyConfig]:
        with self._lock:
            return list(self._policies.values())

    # ── Evolution Oversight ────────────────────────────────────────────

    def submit_evolution_request(
        self,
        target_component: str,
        description: str,
        risk_score: float = 0.5,
    ) -> EvolutionRequest:
        request = EvolutionRequest(
            request_id=uuid.uuid4().hex[:16],
            target_component=target_component,
            description=description,
            risk_score=risk_score,
            submitted_at=time.time(),
        )
        with self._lock:
            self._evolution_requests[request.request_id] = request
        if self._bus:
            self._bus.publish("dashboard.evolution.requested", request.to_dict())
        return request

    def approve_evolution(self, request_id: str) -> bool:
        with self._lock:
            request = self._evolution_requests.get(request_id)
            if not request:
                return False
            request.approved = True
            request.status = "approved"
            request.resolved_at = time.time()
        if self._bus:
            self._bus.publish("dashboard.evolution.approved", {
                "request_id": request_id,
            })
        return True

    def reject_evolution(self, request_id: str) -> bool:
        with self._lock:
            request = self._evolution_requests.get(request_id)
            if not request:
                return False
            request.approved = False
            request.status = "rejected"
            request.resolved_at = time.time()
        if self._bus:
            self._bus.publish("dashboard.evolution.rejected", {
                "request_id": request_id,
            })
        return True

    def list_evolution_requests(
        self,
        status: str | None = None,
    ) -> list[EvolutionRequest]:
        with self._lock:
            requests = list(self._evolution_requests.values())
        if status:
            requests = [r for r in requests if r.status == status]
        return requests

    # ── Audit Log Viewer ───────────────────────────────────────────────

    def query_audit_log(
        self,
        search_term: str = "",
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        if self._graph:
            try:
                all_entities = self._graph.list_entities()
                for entity in all_entities:
                    props = entity.to_dict()
                    if search_term:
                        name_match = search_term.lower() in props.get("name", "").lower()
                        type_match = search_term.lower() in props.get("type", "").lower()
                        if not name_match and not type_match:
                            continue
                    entries.append(props)
                    if len(entries) >= limit:
                        break
            except Exception:
                pass
        return entries

    def get_system_overview(self) -> dict[str, Any]:
        snapshot = self.take_snapshot()
        return {
            "timestamp": snapshot.timestamp,
            "health": self._compute_overall_health(),
            "agents": snapshot.agents.get("total", 0),
            "active_projects": self._pm.list_active_projects() if self._pm else [],
            "active_workflows": (
                self._orchestrator.get_statistics().get("running", 0)
                if self._orchestrator else 0
            ),
            "pending_evolution_requests": len(
                self.list_evolution_requests(status="pending")
            ),
            "alert_count": len(self._alerts),
            "policy_count": len(self._policies),
        }

    def get_statistics(self) -> dict[str, Any]:
        with self._lock:
            return {
                "total_snapshots": len(self._snapshots),
                "total_interventions": len(self._interventions),
                "total_alerts": len(self._alerts),
                "total_policies": len(self._policies),
                "total_evolution_requests": len(self._evolution_requests),
            }

    def health(self) -> dict[str, Any]:
        return {"alive": True}
