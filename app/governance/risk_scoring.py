from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable


RISK_FACTORS = [
    "scope_impact",
    "permission_escalation",
    "resource_impact",
    "dependency_depth",
    "modification_risk",
    "rollback_complexity",
    "historical_failures",
]

DEFAULT_WEIGHTS: dict[str, float] = {
    "scope_impact": 0.20,
    "permission_escalation": 0.20,
    "resource_impact": 0.10,
    "dependency_depth": 0.10,
    "modification_risk": 0.15,
    "rollback_complexity": 0.10,
    "historical_failures": 0.15,
}


@dataclass
class RiskFactor:
    name: str
    score: float = 0.0
    weight: float = 0.0
    evidence: str = ""

    @property
    def weighted_score(self) -> float:
        return self.score * self.weight

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "score": self.score,
            "weight": self.weight,
            "weighted_score": self.weighted_score,
            "evidence": self.evidence,
        }


@dataclass
class RiskScore:
    total: float = 0.0
    factors: dict[str, float] = field(default_factory=dict)
    breakdown: list[RiskFactor] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": round(self.total, 4),
            "factors": dict(self.factors),
            "breakdown": [f.to_dict() for f in self.breakdown],
            "level": self.level,
        }

    @property
    def level(self) -> str:
        if self.total >= 0.8:
            return "critical"
        if self.total >= 0.6:
            return "high"
        if self.total >= 0.4:
            return "medium"
        if self.total >= 0.2:
            return "low"
        return "minimal"


class RiskScorer:
    """Evaluates risk factors and produces a 0.0-1.0 risk score.

    Supports custom factor scorers and configurable weights.

    Thread-safe.
    """

    def __init__(self, weights: dict[str, float] | None = None) -> None:
        self._lock = threading.RLock()
        self._weights: dict[str, float] = dict(weights or DEFAULT_WEIGHTS)
        self._custom_scorers: dict[str, Callable[[dict[str, Any]], float]] = {}

    def set_weight(self, factor: str, weight: float) -> None:
        with self._lock:
            self._weights[factor] = max(0.0, min(1.0, weight))

    def get_weight(self, factor: str) -> float:
        with self._lock:
            return self._weights.get(factor, 0.0)

    def register_scorer(self, factor: str, scorer: Callable[[dict[str, Any]], float]) -> None:
        with self._lock:
            self._custom_scorers[factor] = scorer

    def compute(self, context: dict[str, Any]) -> RiskScore:
        with self._lock:
            breakdown: list[RiskFactor] = []
            for factor in RISK_FACTORS:
                weight = self._weights.get(factor, 0.0)
                if factor in self._custom_scorers:
                    try:
                        score = self._custom_scorers[factor](context)
                    except Exception:
                        score = 0.0
                else:
                    score = self._default_scorer(factor, context)
                score = max(0.0, min(1.0, score))
                breakdown.append(RiskFactor(
                    name=factor, score=score, weight=weight,
                    evidence=self._generate_evidence(factor, score, context),
                ))

            total = sum(f.weighted_score for f in breakdown)
            if breakdown:
                total = total / sum(f.weight for f in breakdown if f.weight > 0) if sum(f.weight for f in breakdown if f.weight > 0) > 0 else 0.0
            else:
                total = 0.0

            return RiskScore(
                total=min(1.0, total),
                factors={f.name: f.score for f in breakdown},
                breakdown=breakdown,
            )

    def _default_scorer(self, factor: str, context: dict[str, Any]) -> float:
        mapping: dict[str, Callable[[dict[str, Any]], float]] = {
            "scope_impact": self._score_scope_impact,
            "permission_escalation": self._score_permission_escalation,
            "resource_impact": self._score_resource_impact,
            "dependency_depth": self._score_dependency_depth,
            "modification_risk": self._score_modification_risk,
            "rollback_complexity": self._score_rollback_complexity,
            "historical_failures": self._score_historical_failures,
        }
        scorer = mapping.get(factor, lambda _: 0.5)
        return scorer(context)

    def _score_scope_impact(self, ctx: dict[str, Any]) -> float:
        systems = ctx.get("affected_systems", 1)
        return min(1.0, systems / 10.0)

    def _score_permission_escalation(self, ctx: dict[str, Any]) -> float:
        return 0.8 if ctx.get("requests_new_permissions", False) else 0.2

    def _score_resource_impact(self, ctx: dict[str, Any]) -> float:
        cpu = ctx.get("estimated_cpu", 0)
        mem = ctx.get("estimated_memory_mb", 0)
        return min(1.0, (cpu / 80.0 + mem / 1024.0) / 2.0)

    def _score_dependency_depth(self, ctx: dict[str, Any]) -> float:
        depth = ctx.get("dependency_depth", 0)
        return min(1.0, depth / 10.0)

    def _score_modification_risk(self, ctx: dict[str, Any]) -> float:
        return 0.7 if ctx.get("modifies_existing", False) else 0.1

    def _score_rollback_complexity(self, ctx: dict[str, Any]) -> float:
        return 0.8 if ctx.get("irreversible", False) else 0.2

    def _score_historical_failures(self, ctx: dict[str, Any]) -> float:
        rate = ctx.get("historical_failure_rate", 0.0)
        return min(1.0, rate * 3.0)

    def _generate_evidence(self, factor: str, score: float, ctx: dict[str, Any]) -> str:
        if score >= 0.8:
            return f"High {factor.replace('_', ' ')} detected"
        if score >= 0.4:
            return f"Moderate {factor.replace('_', ' ')}"
        return f"Low {factor.replace('_', ' ')}"

    def health(self) -> dict[str, Any]:
        with self._lock:
            return {
                "alive": True,
                "factors": list(RISK_FACTORS),
                "weights": dict(self._weights),
                "custom_scorers": list(self._custom_scorers.keys()),
            }
