from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

ScoreFunc = Callable[[dict[str, Any]], float]


@dataclass
class CriterionDef:
    name: str
    weight: float = 1.0
    maximize: bool = True  # True = higher is better; False = lower is better
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "weight": self.weight,
            "maximize": self.maximize,
            "description": self.description,
        }


@dataclass
class Candidate:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    label: str = ""
    attributes: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "attributes": dict(self.attributes),
        }


@dataclass
class DecisionResult:
    winner: Candidate | None = None
    runner_up: Candidate | None = None
    scores: dict[str, float] = field(default_factory=dict)  # candidate_id -> score
    explanations: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "winner_id": self.winner.id if self.winner else None,
            "winner_label": self.winner.label if self.winner else None,
            "runner_up_id": self.runner_up.id if self.runner_up else None,
            "runner_up_label": self.runner_up.label if self.runner_up else None,
            "scores": dict(self.scores),
            "explanations": dict(self.explanations),
        }


class DecisionMatrix:
    """Weighted multi-criteria decision matrix.

    Thread-safe.  Supports scoring candidates against configurable
    criteria with per-criterion weight and direction (maximize/minimize).
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._criteria: dict[str, CriterionDef] = {}
        self._custom_scorers: dict[str, ScoreFunc] = {}

    def add_criterion(
        self,
        name: str,
        weight: float = 1.0,
        maximize: bool = True,
        description: str = "",
    ) -> str:
        with self._lock:
            self._criteria[name] = CriterionDef(
                name=name, weight=weight, maximize=maximize,
                description=description or name,
            )
            return name

    def remove_criterion(self, name: str) -> bool:
        with self._lock:
            if name in self._criteria:
                del self._criteria[name]
                self._custom_scorers.pop(name, None)
                return True
            return False

    def set_custom_scorer(self, criterion: str, scorer: ScoreFunc) -> None:
        with self._lock:
            if criterion not in self._criteria:
                raise ValueError(f"Unknown criterion: {criterion}")
            self._custom_scorers[criterion] = scorer

    def _get_raw_scores(self, candidate: Candidate) -> dict[str, float]:
        result: dict[str, float] = {}
        attr = candidate.attributes
        for cname, cdef in self._criteria.items():
            if cname in self._custom_scorers:
                try:
                    val = self._custom_scorers[cname](attr)
                except Exception:
                    val = 0.0
            else:
                val = attr.get(cname, 0.0)
            result[cname] = val
        return result

    @staticmethod
    def _compute_bounds(all_raw: list[dict[str, float]]) -> dict[str, tuple[float, float]]:
        bounds: dict[str, tuple[float, float]] = {}
        for raw in all_raw:
            for cname, val in raw.items():
                if cname not in bounds:
                    bounds[cname] = (val, val)
                else:
                    lo, hi = bounds[cname]
                    bounds[cname] = (min(lo, val), max(hi, val))
        return bounds

    def _normalize(self, raw_scores: dict[str, float], bounds: dict[str, tuple[float, float]]) -> dict[str, float]:
        normalized: dict[str, float] = {}
        for cname, val in raw_scores.items():
            cdef = self._criteria.get(cname)
            if cdef is None:
                continue
            lo, hi = bounds.get(cname, (0.0, 0.0))
            rng = hi - lo
            if rng == 0.0:
                normalized[cname] = 0.5
            else:
                raw = (val - lo) / rng
                normalized[cname] = raw if cdef.maximize else (1.0 - raw)
        return normalized

    def evaluate(self, candidates: list[Candidate]) -> DecisionResult:
        with self._lock:
            if not candidates:
                return DecisionResult(winner=None)

            if not self._criteria:
                return DecisionResult(winner=candidates[0])

            total_weight = sum(c.weight for c in self._criteria.values())
            if total_weight == 0.0:
                total_weight = 1.0

            all_raw: list[dict[str, float]] = [self._get_raw_scores(c) for c in candidates]
            bounds = self._compute_bounds(all_raw)
            all_norm: list[dict[str, float]] = [self._normalize(r, bounds) for r in all_raw]

            composite: dict[str, float] = {}
            explanations: dict[str, str] = {}

            for cand, raw, norm in zip(candidates, all_raw, all_norm):
                total = 0.0
                parts: list[str] = []
                for cname, cdef in self._criteria.items():
                    n = norm.get(cname, 0.0)
                    weighted = n * cdef.weight
                    total += weighted
                    direction = "+" if cdef.maximize else "-"
                    parts.append(f"{cname}={cdef.weight}*{n:.2f} ({direction})")
                composite[cand.id] = total / total_weight
                explanations[cand.id] = f"Score: {composite[cand.id]:.3f} | " + ", ".join(parts)

            sorted_ids = sorted(composite, key=lambda cid: composite[cid], reverse=True)
            winner_id = sorted_ids[0] if sorted_ids else None
            runner_up_id = sorted_ids[1] if len(sorted_ids) > 1 else None

            winner = next((c for c in candidates if c.id == winner_id), None)
            runner_up = next((c for c in candidates if c.id == runner_up_id), None)

            return DecisionResult(
                winner=winner,
                runner_up=runner_up,
                scores=composite,
                explanations=explanations,
            )

    def list_criteria(self) -> list[CriterionDef]:
        with self._lock:
            return list(self._criteria.values())

    def get_criterion(self, name: str) -> CriterionDef | None:
        with self._lock:
            return self._criteria.get(name)

    def count(self) -> int:
        with self._lock:
            return len(self._criteria)

    def clear(self) -> None:
        with self._lock:
            self._criteria.clear()
            self._custom_scorers.clear()

    def health(self) -> dict[str, Any]:
        return {"alive": True, "criterion_count": self.count()}
