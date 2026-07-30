from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Deployment:
    deployment_id: str = ""
    name: str = ""
    description: str = ""
    target_components: list[str] = field(default_factory=list)
    version: str = ""
    status: str = "pending"
    canary_percentage: float = 0.0
    canary_healthy: bool = False
    rolled_back: bool = False
    created_at: float = 0.0
    deployed_at: float = 0.0
    completed_at: float = 0.0
    result: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "deployment_id": self.deployment_id,
            "name": self.name,
            "description": self.description,
            "target_components": list(self.target_components),
            "version": self.version,
            "status": self.status,
            "canary_percentage": self.canary_percentage,
            "canary_healthy": self.canary_healthy,
            "rolled_back": self.rolled_back,
            "created_at": self.created_at,
            "deployed_at": self.deployed_at,
            "completed_at": self.completed_at,
            "result": dict(self.result),
        }


@dataclass
class CanaryResult:
    result_id: str = ""
    deployment_id: str = ""
    success_count: int = 0
    failure_count: int = 0
    metrics: dict[str, float] = field(default_factory=dict)
    healthy: bool = False
    checked_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "result_id": self.result_id,
            "deployment_id": self.deployment_id,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "metrics": dict(self.metrics),
            "healthy": self.healthy,
            "checked_at": self.checked_at,
        }


@dataclass
class DeploymentReport:
    report_id: str = ""
    deployment_id: str = ""
    name: str = ""
    version: str = ""
    status: str = ""
    target_components: list[str] = field(default_factory=list)
    canary_healthy: bool = False
    rolled_back: bool = False
    duration_seconds: float = 0.0
    summary: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_id": self.report_id,
            "deployment_id": self.deployment_id,
            "name": self.name,
            "version": self.version,
            "status": self.status,
            "target_components": list(self.target_components),
            "canary_healthy": self.canary_healthy,
            "rolled_back": self.rolled_back,
            "duration_seconds": self.duration_seconds,
            "summary": self.summary,
            "details": dict(self.details),
            "timestamp": self.timestamp,
        }


class ContinuousDeployment:
    """Manages continuous deployment with canary testing and automatic rollback.

    Deploys approved improvements to a subset of agents first (canary),
    monitors for issues, and automatically rolls back if problems detected.
    Produces deployment reports for audit and analysis.
    """

    def __init__(
        self,
        graph_store: Any = None,
        event_bus: Any = None,
        heal_engine: Any = None,
    ) -> None:
        self._graph = graph_store
        self._bus = event_bus
        self._heal_engine = heal_engine
        self._lock = threading.RLock()
        self._deployments: dict[str, Deployment] = {}
        self._canary_results: dict[str, CanaryResult] = {}
        self._reports: dict[str, DeploymentReport] = {}
        self._deployment_counter: int = 0

    def create_deployment(
        self,
        name: str,
        description: str = "",
        target_components: list[str] | None = None,
        canary_percentage: float = 10.0,
    ) -> Deployment:
        self._deployment_counter += 1
        deployment = Deployment(
            deployment_id=uuid.uuid4().hex[:16],
            name=name,
            description=description,
            target_components=target_components or [],
            version=f"1.{self._deployment_counter}.0",
            canary_percentage=max(1.0, min(50.0, canary_percentage)),
            created_at=time.time(),
        )
        with self._lock:
            self._deployments[deployment.deployment_id] = deployment
        if self._bus:
            self._bus.publish("deployment.created", deployment.to_dict())
        if self._graph:
            try:
                self._graph.create_entity(
                    type="deployment",
                    name=name,
                    properties=deployment.to_dict(),
                )
            except Exception:
                pass
        return deployment

    def get_deployment(self, deployment_id: str) -> Deployment | None:
        with self._lock:
            return self._deployments.get(deployment_id)

    def start_deployment(self, deployment_id: str) -> bool:
        deployment = self.get_deployment(deployment_id)
        if not deployment:
            return False
        with self._lock:
            if deployment.status != "pending":
                return False
            deployment.status = "canary"
            deployment.deployed_at = time.time()
        if self._bus:
            self._bus.publish("deployment.started", {
                "deployment_id": deployment_id,
            })
        return True

    def record_canary_result(
        self,
        deployment_id: str,
        success_count: int,
        failure_count: int,
        metrics: dict[str, float] | None = None,
    ) -> CanaryResult | None:
        deployment = self.get_deployment(deployment_id)
        if not deployment:
            return None

        healthy = failure_count == 0 and success_count > 0
        result = CanaryResult(
            result_id=uuid.uuid4().hex[:16],
            deployment_id=deployment_id,
            success_count=success_count,
            failure_count=failure_count,
            metrics=metrics or {},
            healthy=healthy,
            checked_at=time.time(),
        )

        with self._lock:
            self._canary_results[result.result_id] = result
            deployment.canary_healthy = healthy

        if healthy:
            with self._lock:
                deployment.status = "deploying"
            self._full_rollout(deployment_id)
        else:
            with self._lock:
                deployment.status = "canary_failed"
            self._rollback(deployment_id, "Canary test failed")

        if self._bus:
            self._bus.publish("deployment.canary.result", result.to_dict())
        return result

    def _full_rollout(self, deployment_id: str) -> bool:
        deployment = self.get_deployment(deployment_id)
        if not deployment:
            return False
        with self._lock:
            deployment.status = "completed"
            deployment.completed_at = time.time()
            deployment.result = {
                "rollout": "full",
                "components": list(deployment.target_components),
            }
        if self._bus:
            self._bus.publish("deployment.completed", {
                "deployment_id": deployment_id,
                "success": True,
            })
        self._generate_report(deployment_id)
        return True

    def _rollback(
        self,
        deployment_id: str,
        reason: str = "",
    ) -> bool:
        deployment = self.get_deployment(deployment_id)
        if not deployment:
            return False
        with self._lock:
            deployment.status = "rolled_back"
            deployment.rolled_back = True
            deployment.completed_at = time.time()
            deployment.result = {"rollback_reason": reason}
        if self._bus:
            self._bus.publish("deployment.rolled_back", {
                "deployment_id": deployment_id,
                "reason": reason,
            })
        self._generate_report(deployment_id)
        return True

    def trigger_rollback(
        self,
        deployment_id: str,
        reason: str,
    ) -> bool:
        deployment = self.get_deployment(deployment_id)
        if not deployment:
            return False
        return self._rollback(deployment_id, reason)

    def _generate_report(self, deployment_id: str) -> DeploymentReport | None:
        deployment = self.get_deployment(deployment_id)
        if not deployment:
            return None

        duration = time.time() - deployment.created_at
        report = DeploymentReport(
            report_id=uuid.uuid4().hex[:16],
            deployment_id=deployment_id,
            name=deployment.name,
            version=deployment.version,
            status=deployment.status,
            target_components=list(deployment.target_components),
            canary_healthy=deployment.canary_healthy,
            rolled_back=deployment.rolled_back,
            duration_seconds=round(duration, 2),
            summary=f"Deployment '{deployment.name}' ({deployment.version}): "
                    f"{deployment.status} in {duration:.1f}s",
            details={
                "description": deployment.description,
                "canary_percentage": deployment.canary_percentage,
                "result": dict(deployment.result),
            },
            timestamp=time.time(),
        )

        with self._lock:
            self._reports[report.report_id] = report

        if self._graph:
            try:
                self._graph.create_entity(
                    type="deployment_report",
                    name=f"report_{report.report_id}",
                    properties=report.to_dict(),
                )
            except Exception:
                pass
        return report

    def get_report(self, report_id: str) -> DeploymentReport | None:
        with self._lock:
            return self._reports.get(report_id)

    def get_deployment_report(self, deployment_id: str) -> DeploymentReport | None:
        with self._lock:
            for report in self._reports.values():
                if report.deployment_id == deployment_id:
                    return report
        return None

    def list_deployments(self) -> list[Deployment]:
        with self._lock:
            return list(self._deployments.values())

    def get_statistics(self) -> dict[str, Any]:
        with self._lock:
            total = len(self._deployments)
            completed = sum(
                1 for d in self._deployments.values()
                if d.status == "completed"
            )
            rolled_back = sum(
                1 for d in self._deployments.values()
                if d.rolled_back
            )
            active = sum(
                1 for d in self._deployments.values()
                if d.status in ("canary", "deploying")
            )
        return {
            "total_deployments": total,
            "completed": completed,
            "rolled_back": rolled_back,
            "active": active,
            "deployment_success_rate": round(
                (completed / max(total, 1)) * 100, 1
            ),
        }

    def health(self) -> dict[str, Any]:
        return {"alive": True}
