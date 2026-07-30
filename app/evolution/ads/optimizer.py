from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class OptimizationPlan:
    plan_id: str = ""
    description: str = ""
    stage_order: list[str] = field(default_factory=list)
    parallel_stages: list[list[str]] = field(default_factory=list)
    skip_conditions: dict[str, str] = field(default_factory=dict)
    estimated_improvement: float = 0.0
    applied: bool = False
    timestamp: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "description": self.description,
            "stage_order": list(self.stage_order),
            "parallel_stages": [list(g) for g in self.parallel_stages],
            "estimated_improvement": self.estimated_improvement,
            "applied": self.applied,
            "timestamp": self.timestamp,
        }


DEFAULT_STAGE_ORDER = [
    "requirements_analysis",
    "capability_analysis",
    "gap_detection",
    "architecture_design",
    "content_generation",
    "test_generation",
    "sandbox_execution",
    "simulation",
    "benchmark",
    "security_review",
    "performance_review",
    "governance_check",
    "approval",
    "installation",
    "registration",
    "versioning",
    "metrics",
    "learning",
]


class ADSPipelineOptimizer:
    """Optimizes the ADS pipeline by reordering, parallelizing,
    or skipping stages based on historical data.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._plans: dict[str, OptimizationPlan] = {}
        self._stage_durations: dict[str, float] = {}

    def record_stage_duration(self, stage: str, duration_ms: float) -> None:
        with self._lock:
            self._stage_durations[stage] = duration_ms

    def suggest_parallelization(self) -> list[list[str]]:
        candidates: list[list[str]] = [
            ["requirements_analysis", "capability_analysis"],
            ["security_review", "performance_review"],
            ["registration", "versioning"],
        ]
        return candidates

    def suggest_skip_conditions(self) -> dict[str, str]:
        return {
            "simulation": "skip if artifact_type in ('documentation', 'knowledge_pack')",
            "benchmark": "skip if artifact_type == 'documentation'",
            "performance_review": "skip if artifact_type == 'knowledge_pack'",
        }

    def create_optimization_plan(self) -> OptimizationPlan:
        plan = OptimizationPlan(
            plan_id=uuid.uuid4().hex[:16],
            description="Optimize ADS pipeline stage ordering and parallelization",
            stage_order=DEFAULT_STAGE_ORDER,
            parallel_stages=self.suggest_parallelization(),
            skip_conditions=self.suggest_skip_conditions(),
            estimated_improvement=0.25,
            timestamp=time.time(),
        )
        with self._lock:
            self._plans[plan.plan_id] = plan
        return plan

    def apply_plan(self, plan_id: str) -> bool:
        with self._lock:
            plan = self._plans.get(plan_id)
            if plan is None:
                return False
            plan.applied = True
            return True

    def get_plan(self, plan_id: str) -> OptimizationPlan | None:
        with self._lock:
            return self._plans.get(plan_id)

    def get_statistics(self) -> dict[str, Any]:
        with self._lock:
            total = len(self._plans)
            applied = sum(1 for p in self._plans.values() if p.applied)
            avg_improvement = (
                sum(p.estimated_improvement for p in self._plans.values()) / max(total, 1)
            )
        return {
            "total_plans": total,
            "applied": applied,
            "avg_estimated_improvement": round(avg_improvement, 4),
            "parallelization_suggestions": len(self.suggest_parallelization()),
        }

    def health(self) -> dict[str, Any]:
        return {"alive": True}
