from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AnalysisResult:
    analysis_id: str = ""
    target_area: str = ""
    issues_found: int = 0
    improvement_potential: float = 0.0
    details: list[dict[str, Any]] = field(default_factory=list)
    timestamp: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "analysis_id": self.analysis_id,
            "target_area": self.target_area,
            "issues_found": self.issues_found,
            "improvement_potential": self.improvement_potential,
            "details": list(self.details),
            "timestamp": self.timestamp,
        }


EVOLUTION_AREAS = [
    "system_evolution",
    "framework_evolution",
    "ads_evolution",
    "tool_evolution",
    "simulation_evolution",
    "meta_evolution_itself",
]


class MetaEvolutionAnalyzer:
    """Analyzes the effectiveness of the evolution system itself.

    Scans all evolution areas to identify bottlenecks,
    redundant efforts, and opportunities for cross-area
    optimization.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._results: dict[str, AnalysisResult] = {}
        self._area_metrics: dict[str, dict[str, float]] = {}

    def record_metric(self, area: str, metric: str, value: float) -> None:
        with self._lock:
            if area not in self._area_metrics:
                self._area_metrics[area] = {}
            self._area_metrics[area][metric] = value

    def analyze_area(self, area: str) -> AnalysisResult:
        analysis_id = uuid.uuid4().hex[:16]
        issues: list[dict[str, Any]] = []

        with self._lock:
            metrics = self._area_metrics.get(area, {})

        if metrics.get("patch_success_rate", 1.0) < 0.5:
            issues.append({
                "severity": "high",
                "description": f"Low patch success rate ({metrics['patch_success_rate']:.0%})",
            })
        if metrics.get("avg_iterations", 0) > 10:
            issues.append({
                "severity": "medium",
                "description": f"High average iterations ({metrics['avg_iterations']})",
            })
        if metrics.get("test_failure_rate", 0) > 0.2:
            issues.append({
                "severity": "high",
                "description": f"High test failure rate ({metrics['test_failure_rate']:.0%})",
            })
        if metrics.get("rollback_rate", 0) > 0.3:
            issues.append({
                "severity": "critical",
                "description": f"High rollback rate ({metrics['rollback_rate']:.0%}) — consider reverting recent changes",
            })

        potential = self._compute_potential(metrics, len(issues))

        result = AnalysisResult(
            analysis_id=analysis_id,
            target_area=area,
            issues_found=len(issues),
            improvement_potential=potential,
            details=issues,
            timestamp=time.time(),
        )

        with self._lock:
            self._results[analysis_id] = result
        return result

    def _compute_potential(self, metrics: dict[str, float], issues: int) -> float:
        base = 0.1
        if metrics.get("patch_success_rate", 1.0) < 0.5:
            base += 0.3
        if metrics.get("avg_iterations", 0) > 10:
            base += 0.2
        if metrics.get("test_failure_rate", 0) > 0.2:
            base += 0.2
        if metrics.get("rollback_rate", 0) > 0.3:
            base += 0.3
        return min(base + issues * 0.05, 1.0)

    def analyze_all(self) -> list[AnalysisResult]:
        return [self.analyze_area(area) for area in EVOLUTION_AREAS]

    def get_result(self, analysis_id: str) -> AnalysisResult | None:
        with self._lock:
            return self._results.get(analysis_id)

    def get_statistics(self) -> dict[str, Any]:
        with self._lock:
            total = len(self._results)
            high_issues = sum(
                1 for r in self._results.values()
                if any(d.get("severity") == "high" for d in r.details)
            )
        return {
            "total_analyses": total,
            "areas_with_high_issues": high_issues,
        }

    def health(self) -> dict[str, Any]:
        return {"alive": True}
