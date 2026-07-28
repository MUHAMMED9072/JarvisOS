from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from app.intelligence.outcome_analyzer import OutcomeAnalyzer, TaskOutcome
from app.intelligence.heuristic_store import HeuristicStore, Heuristic


@dataclass
class ReflectionReport:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    timestamp: float = field(default_factory=time.time)
    total_outcomes: int = 0
    failure_rate: float = 0.0
    common_failures: list[str] = field(default_factory=list)
    updated_heuristics: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "total_outcomes": self.total_outcomes,
            "failure_rate": self.failure_rate,
            "common_failures": list(self.common_failures),
            "updated_heuristics": list(self.updated_heuristics),
            "recommendations": list(self.recommendations),
        }


class Reflection:
    """Reflection Engine that analyzes task execution outcomes, detects
    patterns, updates heuristics, and produces reports.

    Thread-safe.  Connects OutcomeAnalyzer and HeuristicStore into a
    feedback loop that can be consumed by the Planner and Reasoner.
    """

    def __init__(
        self,
        outcome_analyzer: OutcomeAnalyzer | None = None,
        heuristic_store: HeuristicStore | None = None,
    ) -> None:
        self._lock = threading.RLock()
        self.outcome_analyzer = outcome_analyzer or OutcomeAnalyzer()
        self.heuristic_store = heuristic_store or HeuristicStore()
        self._reports: list[ReflectionReport] = []

    def analyze(self, outcome: TaskOutcome) -> TaskOutcome:
        """Analyze a single outcome and optionally update heuristics."""
        analyzed = self.outcome_analyzer.analyze(outcome)
        if not analyzed.success:
            for heuristic in self.heuristic_store.list_heuristics():
                self._try_update_heuristic(heuristic, analyzed)
        return analyzed

    def _try_update_heuristic(self, heuristic: Heuristic, outcome: TaskOutcome) -> None:
        if heuristic.domain and heuristic.domain in outcome.failure_pattern:
            self.heuristic_store.record_failure(heuristic.id)
            heuristic.weight = max(0.1, heuristic.weight * 0.9)
            self.heuristic_store.update(heuristic)

    def generate_report(self) -> ReflectionReport:
        """Produce a reflection report summarising recent outcomes and
        heuristic adjustments."""
        with self._lock:
            patterns = self.outcome_analyzer.get_common_failures()
            updated = self.heuristic_store.list_heuristics()

            recommendations: list[str] = []
            for p in patterns:
                if p.severity == "high":
                    recommendations.append(
                        f"Address high-severity pattern '{p.pattern}' "
                        f"(seen {p.count} times, cause: {p.cause})"
                    )

            report = ReflectionReport(
                total_outcomes=self.outcome_analyzer.get_outcome_count(),
                failure_rate=self.outcome_analyzer.get_failure_rate(),
                common_failures=[p.pattern for p in patterns],
                updated_heuristics=[h.name for h in updated if h.name],
                recommendations=recommendations,
            )
            self._reports.append(report)
            return report

    def feedback_for_planner(self) -> dict[str, Any]:
        """Return adjusted weights and recommendations for the Planner."""
        with self._lock:
            heuristics = self.heuristic_store.list_heuristics()
            patterns = self.outcome_analyzer.get_common_failures()
            return {
                "adjusted_weights": {h.name: h.weight for h in heuristics if h.name},
                "avoid_patterns": [p.pattern for p in patterns if p.severity == "high"],
                "failure_rate": self.outcome_analyzer.get_failure_rate(),
            }

    def feedback_for_reasoner(self) -> dict[str, Any]:
        """Return reliability data and process adjustments for the Reasoner."""
        with self._lock:
            heuristics = self.heuristic_store.list_heuristics()
            return {
                "heuristic_reliability": {
                    h.name: h.reliability for h in heuristics if h.name
                },
                "total_failures": sum(
                    1 for o in self.outcome_analyzer.list_outcomes(success=False)
                ),
            }

    def list_reports(self, limit: int = 10) -> list[ReflectionReport]:
        with self._lock:
            return self._reports[-limit:]

    def health(self) -> dict[str, Any]:
        return {
            "alive": True,
            "outcomes_analyzed": self.outcome_analyzer.get_outcome_count(),
            "failure_rate": self.outcome_analyzer.get_failure_rate(),
            "reports_generated": len(self._reports),
            "heuristics_tracked": self.heuristic_store.count(),
        }
