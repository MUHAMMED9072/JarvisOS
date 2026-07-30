from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class QualityScore:
    score_id: str = ""
    target_area: str = ""
    overall_score: float = 0.0
    dimensions: dict[str, float] = field(default_factory=dict)
    recommendations: list[str] = field(default_factory=list)
    timestamp: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "score_id": self.score_id,
            "target_area": self.target_area,
            "overall_score": self.overall_score,
            "dimensions": dict(self.dimensions),
            "recommendations": list(self.recommendations),
            "timestamp": self.timestamp,
        }


SCORING_DIMENSIONS = [
    "correctness",
    "completeness",
    "efficiency",
    "maintainability",
    "test_coverage",
]


class MetaQualityScorer:
    """Scores the quality of evolution in each area.

    Evaluates correctness, completeness, efficiency,
    maintainability, and test coverage of evolution
    attempts.
    """

    def __init__(self, graph_store: Any = None, event_bus: Any = None) -> None:
        self._graph = graph_store
        self._bus = event_bus
        self._lock = threading.RLock()
        self._scores: dict[str, QualityScore] = {}
        self._dimension_records: dict[str, dict[str, list[float]]] = {}

    def record_dimension_score(
        self,
        area: str,
        dimension: str,
        score: float,
    ) -> None:
        with self._lock:
            if area not in self._dimension_records:
                self._dimension_records[area] = {}
            if dimension not in self._dimension_records[area]:
                self._dimension_records[area][dimension] = []
            self._dimension_records[area][dimension].append(max(0.0, min(1.0, score)))

    def score_area(self, area: str) -> QualityScore:
        score_id = uuid.uuid4().hex[:16]
        dims: dict[str, float] = {}
        recommendations: list[str] = []
        overall = 0.0

        with self._lock:
            records = self._dimension_records.get(area, {})

        for dim in SCORING_DIMENSIONS:
            values = records.get(dim, [])
            avg = sum(values) / len(values) if values else 0.5
            dims[dim] = round(avg, 4)

            if avg < 0.5:
                recommendations.append(f"Improve {dim} in {area} (current: {avg:.0%})")

        overall = round(sum(dims.values()) / len(dims), 4) if dims else 0.5

        if not recommendations:
            recommendations.append("Quality levels acceptable across all dimensions")

        score = QualityScore(
            score_id=score_id,
            target_area=area,
            overall_score=overall,
            dimensions=dims,
            recommendations=recommendations,
            timestamp=time.time(),
        )

        if self._graph:
            try:
                self._graph.create_entity(
                    type="quality_score",
                    name=f"quality_{score_id}",
                    properties=score.to_dict(),
                )
            except Exception:
                pass
        if self._bus:
            try:
                self._bus.publish("meta.quality.scored", score.to_dict())
            except Exception:
                pass

        with self._lock:
            self._scores[score_id] = score
        return score

    def get_score(self, score_id: str) -> QualityScore | None:
        with self._lock:
            return self._scores.get(score_id)

    def get_statistics(self) -> dict[str, Any]:
        with self._lock:
            total = len(self._scores)
            avg_scores: dict[str, float] = {}
            for area_records in self._dimension_records.values():
                for dim, values in area_records.items():
                    if dim not in avg_scores:
                        avg_scores[dim] = 0.0
                    avg_scores[dim] = sum(values) / len(values)
            return {
                "total_scores": total,
                "dimension_averages": {k: round(v, 4) for k, v in avg_scores.items()},
            }

    def health(self) -> dict[str, Any]:
        return {"alive": True}
