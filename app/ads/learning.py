from __future__ import annotations

import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from app.knowledge_graph.store import GraphStore


@dataclass
class FeedbackEntry:
    artifact_name: str = ""
    execution_id: str = ""
    success: bool = False
    latency_ms: float = 0.0
    error_type: str = ""
    feedback: str = ""
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_name": self.artifact_name,
            "execution_id": self.execution_id,
            "success": self.success,
            "latency_ms": self.latency_ms,
            "error_type": self.error_type,
            "feedback": self.feedback,
            "timestamp": self.timestamp,
        }


@dataclass
class Heuristic:
    name: str = ""
    description: str = ""
    weight: float = 1.0
    hit_count: int = 0
    miss_count: int = 0
    last_updated: float = field(default_factory=time.time)

    @property
    def accuracy(self) -> float:
        total = self.hit_count + self.miss_count
        if total == 0:
            return 1.0
        return self.hit_count / total

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "weight": self.weight,
            "hit_count": self.hit_count,
            "miss_count": self.miss_count,
            "accuracy": self.accuracy,
            "last_updated": self.last_updated,
        }


@dataclass
class LearningResult:
    success: bool = True
    error: str = ""
    feedback: FeedbackEntry | None = None
    heuristics_updated: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "error": self.error,
            "feedback": self.feedback.to_dict() if self.feedback else None,
            "heuristics_updated": list(self.heuristics_updated),
        }


class LearningLoop:
    """Collect execution feedback and update heuristics."""

    def __init__(self, graph_store: GraphStore) -> None:
        self._store = graph_store
        self._lock = threading.RLock()
        self._feedback_log: list[FeedbackEntry] = []
        self._heuristics: dict[str, Heuristic] = {
            "latency_penalty": Heuristic(
                name="latency_penalty",
                description="Penalize high-latency executions",
                weight=0.3,
            ),
            "error_rate_boost": Heuristic(
                name="error_rate_boost",
                description="Boost monitoring for artifacts with high error rates",
                weight=0.5,
            ),
            "success_reinforcement": Heuristic(
                name="success_reinforcement",
                description="Reinforce patterns that lead to success",
                weight=0.8,
            ),
        }

    def record_feedback(self, feedback: FeedbackEntry) -> LearningResult:
        with self._lock:
            self._feedback_log.append(feedback)

        # Persist to KG
        self._store.create_entity(
            type="concept",
            name=f"feedback_{feedback.artifact_name}_{int(time.time())}",
            properties={
                "artifact_name": feedback.artifact_name,
                "execution_id": feedback.execution_id,
                "success": str(feedback.success),
                "latency_ms": str(feedback.latency_ms),
                "error_type": feedback.error_type,
                "feedback": feedback.feedback,
                "timestamp": str(feedback.timestamp),
            },
        )

        # Update heuristics based on feedback
        updated = self._update_heuristics(feedback)

        return LearningResult(
            success=True,
            feedback=feedback,
            heuristics_updated=updated,
        )

    def get_feedback(
        self, artifact_name: str, limit: int = 50,
    ) -> list[FeedbackEntry]:
        with self._lock:
            matching = [f for f in self._feedback_log if f.artifact_name == artifact_name]
            return matching[-limit:]

    def get_all_feedback(self, limit: int = 200) -> list[FeedbackEntry]:
        with self._lock:
            return self._feedback_log[-limit:]

    def get_heuristics(self) -> dict[str, Heuristic]:
        with self._lock:
            return dict(self._heuristics)

    def get_heuristic(self, name: str) -> Heuristic | None:
        with self._lock:
            return self._heuristics.get(name)

    def update_heuristic_weight(self, name: str, weight: float) -> bool:
        with self._lock:
            if name not in self._heuristics:
                return False
            self._heuristics[name].weight = weight
            self._heuristics[name].last_updated = time.time()
            return True

    def _update_heuristics(self, feedback: FeedbackEntry) -> list[str]:
        updated: list[str] = []
        with self._lock:
            for name, heur in self._heuristics.items():
                if name == "latency_penalty":
                    if feedback.latency_ms > 500:
                        heur.hit_count += 1
                        updated.append(name)
                    else:
                        heur.miss_count += 1
                elif name == "error_rate_boost":
                    if not feedback.success and feedback.error_type:
                        heur.hit_count += 1
                        updated.append(name)
                    else:
                        heur.miss_count += 1
                elif name == "success_reinforcement":
                    if feedback.success:
                        heur.hit_count += 1
                        updated.append(name)
                    else:
                        heur.miss_count += 1
                heur.last_updated = time.time()
        return updated

    def compute_quality_adjustment(self, artifact_name: str) -> float:
        with self._lock:
            recent = [f for f in self._feedback_log if f.artifact_name == artifact_name][-20:]
        if not recent:
            return 0.0

        success_rate = sum(1 for f in recent if f.success) / len(recent)
        avg_latency = sum(f.latency_ms for f in recent) / len(recent)

        adjustment = 0.0
        if success_rate < 0.5:
            adjustment -= 0.2
        elif success_rate < 0.8:
            adjustment -= 0.1
        elif success_rate > 0.95:
            adjustment += 0.05

        if avg_latency > 1000:
            adjustment -= 0.1
        elif avg_latency < 50:
            adjustment += 0.05

        return round(adjustment, 2)

    def health(self) -> dict[str, Any]:
        with self._lock:
            return {
                "alive": True,
                "feedback_count": len(self._feedback_log),
                "heuristic_count": len(self._heuristics),
            }
