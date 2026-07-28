from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from app.intelligence.decision_matrix import DecisionMatrix, Candidate, CriterionDef


@dataclass
class DecisionRecord:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    decision_type: str = ""  # agent_selection, strategy_selection
    context: dict[str, Any] = field(default_factory=dict)
    winner_id: str = ""
    winner_label: str = ""
    scores: dict[str, float] = field(default_factory=dict)
    explanation: str = ""
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "decision_type": self.decision_type,
            "context": dict(self.context),
            "winner_id": self.winner_id,
            "winner_label": self.winner_label,
            "scores": dict(self.scores),
            "explanation": self.explanation,
            "timestamp": self.timestamp,
        }


@dataclass
class AgentInfo:
    agent_id: str = ""
    name: str = ""
    capability: float = 0.0
    cost: float = 0.0
    load: float = 0.0
    reliability: float = 0.5

    def to_candidate(self) -> Candidate:
        return Candidate(
            id=self.agent_id,
            label=self.name,
            attributes={
                "capability": self.capability,
                "cost": -self.cost,
                "load": -self.load,
                "reliability": self.reliability,
            },
        )


class DecisionEngine:
    """Makes optimal choices between competing agents, strategies, plans,
    and resources using the DecisionMatrix.

    Thread-safe.  Logs every decision for audit.
    """

    def __init__(
        self,
        matrix: DecisionMatrix | None = None,
    ) -> None:
        self._lock = threading.RLock()
        self._matrix = matrix or self._default_matrix()
        self._decision_log: list[DecisionRecord] = []

    @staticmethod
    def _default_matrix() -> DecisionMatrix:
        m = DecisionMatrix()
        m.add_criterion("capability", weight=3.0, maximize=True, description="Agent capability score")
        m.add_criterion("cost", weight=2.0, maximize=True, description="Negative cost (higher = cheaper)")
        m.add_criterion("load", weight=1.5, maximize=True, description="Negative load (higher = less loaded)")
        m.add_criterion("reliability", weight=2.5, maximize=True, description="Historical reliability")
        return m

    def select_agent(
        self,
        agents: list[AgentInfo],
        context: dict[str, Any] | None = None,
    ) -> DecisionRecord:
        with self._lock:
            candidates = [a.to_candidate() for a in agents]
            result = self._matrix.evaluate(candidates)
            winner_label = result.winner.label if result.winner else ""
            winner_id = result.winner.id if result.winner else ""
            explanation = result.explanations.get(winner_id, "No winner") if winner_id else "No candidates"

            record = DecisionRecord(
                decision_type="agent_selection",
                context=context or {},
                winner_id=winner_id,
                winner_label=winner_label,
                scores=result.scores,
                explanation=explanation,
            )
            self._decision_log.append(record)
            return record

    def select_strategy(
        self,
        strategies: list[Candidate],
        context: dict[str, Any] | None = None,
    ) -> DecisionRecord:
        with self._lock:
            result = self._matrix.evaluate(strategies)
            winner_label = result.winner.label if result.winner else ""
            winner_id = result.winner.id if result.winner else ""
            explanation = result.explanations.get(winner_id, "No winner") if winner_id else "No candidates"

            record = DecisionRecord(
                decision_type="strategy_selection",
                context=context or {},
                winner_id=winner_id,
                winner_label=winner_label,
                scores=result.scores,
                explanation=explanation,
            )
            self._decision_log.append(record)
            return record

    def get_recent_decisions(self, limit: int = 20) -> list[DecisionRecord]:
        with self._lock:
            return self._decision_log[-limit:]

    def get_decision_count(self) -> int:
        with self._lock:
            return len(self._decision_log)

    def get_decision_log(self) -> list[DecisionRecord]:
        with self._lock:
            return list(self._decision_log)

    def matrix(self) -> DecisionMatrix:
        return self._matrix

    def health(self) -> dict[str, Any]:
        return {
            "alive": True,
            "decisions_made": self.get_decision_count(),
            "criteria_configured": self._matrix.count(),
        }
