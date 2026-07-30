from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class MetaEvolutionResult:
    meta_id: str = ""
    selected_strategy: str = ""
    areas_analyzed: int = 0
    plans_generated: int = 0
    quality_scores: int = 0
    overall_improvement: float = 0.0
    details: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    timestamp: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "meta_id": self.meta_id,
            "selected_strategy": self.selected_strategy,
            "areas_analyzed": self.areas_analyzed,
            "plans_generated": self.plans_generated,
            "quality_scores": self.quality_scores,
            "overall_improvement": self.overall_improvement,
            "details": dict(self.details),
            "error": self.error,
            "timestamp": self.timestamp,
        }


class MetaEvolutionManager:
    """Coordinates the entire meta-evolution process.

    Combines analysis, improvement planning, strategy
    selection, and quality scoring into a single
    self-improvement loop for the evolution system.
    """

    def __init__(
        self,
        analyzer: Any = None,
        improver: Any = None,
        strategy_selector: Any = None,
        quality_scorer: Any = None,
        graph_store: Any = None,
        event_bus: Any = None,
    ) -> None:
        self._analyzer = analyzer
        self._improver = improver
        self._strategy_selector = strategy_selector
        self._scorer = quality_scorer
        self._graph = graph_store
        self._bus = event_bus
        self._lock = threading.RLock()
        self._results: dict[str, MetaEvolutionResult] = {}

    def run_meta_evolution(self, risk_tolerance: float = 0.5) -> MetaEvolutionResult:
        meta_id = uuid.uuid4().hex[:16]
        details: dict[str, Any] = {}

        strategy = None
        if self._strategy_selector:
            strategy = self._strategy_selector.select_strategy(risk_tolerance)
            details["strategy"] = strategy.to_dict() if strategy else None

        analyses = []
        if self._analyzer:
            analyses = self._analyzer.analyze_all()
            details["analyses"] = [a.to_dict() for a in analyses]

        plans = []
        if self._improver and analyses:
            for analysis in analyses:
                plan = self._improver.generate_plan(analysis)
                plans.append(plan)
            details["plans"] = [p.to_dict() for p in plans]

        scores = []
        if self._scorer:
            evolution_areas = [
                "system_evolution",
                "framework_evolution",
                "ads_evolution",
                "tool_evolution",
                "simulation_evolution",
                "meta_evolution_itself",
            ]
            for area in evolution_areas:
                score = self._scorer.score_area(area)
                scores.append(score)
            details["scores"] = [s.to_dict() for s in scores]

        overall = 0.0
        if strategy:
            overall += strategy.expected_impact * 0.3
        if analyses:
            potentials = [a.improvement_potential for a in analyses]
            overall += (sum(potentials) / len(potentials)) * 0.3
        if plans:
            gains = [p.expected_gain for p in plans]
            overall += (sum(gains) / len(gains)) * 0.2
        if scores:
            score_values = [s.overall_score for s in scores]
            overall += (sum(score_values) / len(score_values)) * 0.2

        result = MetaEvolutionResult(
            meta_id=meta_id,
            selected_strategy=strategy.name if strategy else "none",
            areas_analyzed=len(analyses),
            plans_generated=len(plans),
            quality_scores=len(scores),
            overall_improvement=round(overall, 4),
            details=details,
            timestamp=time.time(),
        )

        if self._graph:
            try:
                self._graph.create_entity(
                    type="evolution_attempt",
                    name=f"meta_evolve_{meta_id}",
                    properties=result.to_dict(),
                )
            except Exception:
                pass
        if self._bus:
            try:
                self._bus.publish("meta.evolution.completed", result.to_dict())
            except Exception:
                pass

        with self._lock:
            self._results[meta_id] = result
        return result

    def get_result(self, meta_id: str) -> MetaEvolutionResult | None:
        with self._lock:
            return self._results.get(meta_id)

    def get_statistics(self) -> dict[str, Any]:
        with self._lock:
            total = len(self._results)
            avg_improvement = (
                sum(r.overall_improvement for r in self._results.values()) / total
            ) if total else 0.0
        return {
            "total_meta_evolutions": total,
            "average_improvement": round(avg_improvement, 4),
        }

    def health(self) -> dict[str, Any]:
        return {"alive": True}
