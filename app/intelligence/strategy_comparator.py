from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any


CRITERIA_DESCRIPTIONS: dict[str, str] = {
    "speed": "How fast the approach completes",
    "accuracy": "How accurate the results are expected to be",
    "resource_efficiency": "How efficiently resources are used",
    "risk": "How risky the approach is",
    "complexity": "How complex the implementation is",
    "scalability": "How well the approach scales",
    "maintainability": "How maintainable the results are",
    "reusability": "How reusable the approach is",
}


@dataclass
class Criterion:
    name: str = ""
    weight: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "weight": self.weight}


@dataclass
class Strategy:
    id: str = ""
    name: str = ""
    description: str = ""
    scores: dict[str, float] = field(default_factory=dict)

    @property
    def weighted_score(self) -> float:
        return sum(self.scores.values())

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "scores": dict(self.scores),
            "weighted_score": self.weighted_score,
        }


@dataclass
class ComparisonResult:
    strategies: list[Strategy] = field(default_factory=list)
    criteria: list[Criterion] = field(default_factory=list)
    winner: str = ""
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategies": [s.to_dict() for s in self.strategies],
            "criteria": [c.to_dict() for c in self.criteria],
            "winner": self.winner,
            "summary": self.summary,
        }


class StrategyComparator:
    """Compares multiple approaches against weighted criteria to rank
    alternatives and identify the best approach.

    Thread-safe.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()

    def compare(
        self,
        strategies: list[Strategy],
        criteria: list[Criterion] | None = None,
    ) -> ComparisonResult:
        """Compare strategies and produce a ranked result.

        Args:
            strategies: List of Strategy objects to compare.
            criteria: List of Criterion with weights. Uses default criteria
                      if None.

        Returns:
            ComparisonResult with ranked strategies and the winner.
        """
        with self._lock:
            if criteria is None:
                criteria = [
                    Criterion(name="speed", weight=1.0),
                    Criterion(name="accuracy", weight=1.0),
                    Criterion(name="resource_efficiency", weight=0.8),
                    Criterion(name="risk", weight=1.0),
                ]

            scored: list[tuple[float, Strategy]] = []
            for strategy in strategies:
                total = sum(
                    strategy.scores.get(c.name, 0.0) * c.weight
                    for c in criteria
                )
                scored.append((total, strategy))

            scored.sort(key=lambda x: x[0], reverse=True)
            ranked = [s for _, s in scored]

            winner = ranked[0].name if ranked else ""

            details = []
            for s in ranked:
                criteria_breakdown = ", ".join(
                    f"{c.name}={s.scores.get(c.name, 0.0):.1f}"
                    for c in criteria
                )
                details.append(f"{s.name}: {s.weighted_score:.1f} ({criteria_breakdown})")

            summary = " | ".join(details)

            return ComparisonResult(
                strategies=ranked,
                criteria=criteria,
                winner=winner,
                summary=summary,
            )

    def health(self) -> dict[str, Any]:
        return {"alive": True}
