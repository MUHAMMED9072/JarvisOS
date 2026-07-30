from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from app.evolution.meta.analyzer import AnalysisResult


@dataclass
class ImprovementPlan:
    plan_id: str = ""
    target_area: str = ""
    changes: list[str] = field(default_factory=list)
    expected_gain: float = 0.0
    risk_score: float = 0.0
    error: str = ""
    timestamp: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "target_area": self.target_area,
            "changes": list(self.changes),
            "expected_gain": self.expected_gain,
            "risk_score": self.risk_score,
            "error": self.error,
            "timestamp": self.timestamp,
        }


class MetaImprovementEngine:
    """Generates improvement plans based on analysis results.

    Translates analysis findings into concrete code changes
    for each evolution area, with risk assessment.
    """

    def __init__(self, graph_store: Any = None, event_bus: Any = None) -> None:
        self._graph = graph_store
        self._bus = event_bus
        self._lock = threading.RLock()
        self._plans: dict[str, ImprovementPlan] = {}

    def generate_plan(self, analysis: AnalysisResult) -> ImprovementPlan:
        plan_id = uuid.uuid4().hex[:16]
        changes: list[str] = []
        risk_score = 0.3

        for issue in analysis.details:
            severity = issue.get("severity", "low")
            if severity == "critical":
                changes.append(f"CRITICAL: {issue['description']}")
                risk_score = min(risk_score + 0.3, 1.0)
            elif severity == "high":
                changes.append(f"High: {issue['description']}")
                risk_score = min(risk_score + 0.15, 1.0)
            elif severity == "medium":
                changes.append(f"Medium: {issue['description']}")
                risk_score = min(risk_score + 0.05, 1.0)

        if not changes:
            changes.append("No critical issues — consider performance micro-optimizations")

        plan = ImprovementPlan(
            plan_id=plan_id,
            target_area=analysis.target_area,
            changes=changes,
            expected_gain=analysis.improvement_potential,
            risk_score=risk_score,
            timestamp=time.time(),
        )

        if self._graph:
            try:
                self._graph.create_entity(
                    type="evolution_attempt",
                    name=f"meta_plan_{plan_id}",
                    properties=plan.to_dict(),
                )
            except Exception:
                pass
        if self._bus:
            try:
                self._bus.publish("meta.improvement.plan_generated", plan.to_dict())
            except Exception:
                pass

        with self._lock:
            self._plans[plan_id] = plan
        return plan

    def get_plan(self, plan_id: str) -> ImprovementPlan | None:
        with self._lock:
            return self._plans.get(plan_id)

    def get_statistics(self) -> dict[str, Any]:
        with self._lock:
            total = len(self._plans)
            total_gain = sum(p.expected_gain for p in self._plans.values())
            avg_risk = (sum(p.risk_score for p in self._plans.values()) / total) if total else 0.0
        return {
            "total_plans": total,
            "total_expected_gain": round(total_gain, 4),
            "average_risk": round(avg_risk, 4),
        }

    def health(self) -> dict[str, Any]:
        return {"alive": True}
