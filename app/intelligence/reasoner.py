from __future__ import annotations

import threading
import time
from typing import Any

from app.core.event_bus import EventBus
from app.intelligence.justification import (
    CounterArgument,
    Evidence,
    Justification,
    JustificationGenerator,
)
from app.intelligence.strategy_comparator import (
    ComparisonResult,
    Criterion,
    Strategy,
    StrategyComparator,
)
from app.knowledge_graph.store import GraphStore


class Reasoner:
    """Evaluates alternative strategies, compares approaches, and produces
    coherent justifications with confidence scoring and counter-arguments.

    Integrates with:
      - StrategyComparator for ranking alternatives
      - JustificationGenerator for human-readable explanations
      - Knowledge Graph for evidence gathering

    Thread-safe.
    """

    def __init__(
        self,
        graph_store: GraphStore | None = None,
        event_bus: EventBus | None = None,
    ) -> None:
        self._graph = graph_store
        self._event_bus = event_bus
        self._comparator = StrategyComparator()
        self._justifier = JustificationGenerator(graph_store)
        self._lock = threading.RLock()
        self._recommendations: list[dict[str, Any]] = []
        self._started_at: float = time.time()

    @property
    def comparator(self) -> StrategyComparator:
        return self._comparator

    @property
    def justifier(self) -> JustificationGenerator:
        return self._justifier

    # ------------------------------------------------------------------
    # Recommendation
    # ------------------------------------------------------------------

    def recommend(
        self,
        context: dict[str, Any],
        strategies: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Produce a recommendation given a decision context and strategies.

        Args:
            context: Decision context with fields like 'goal', 'constraints', etc.
            strategies: List of strategy dicts with 'name', 'description', 'scores'.

        Returns:
            Dict with 'comparison', 'justification', 'winner', and 'confidence'.
        """
        with self._lock:
            strategy_objects = self._build_strategies(strategies)
            criteria = self._build_criteria(context)
            comparison = self._comparator.compare(strategy_objects, criteria)
            best_strategy = comparison.strategies[0] if comparison.strategies else None

            justification = self._build_justification(
                best_strategy, comparison, context
            )

            result = {
                "comparison": comparison.to_dict(),
                "justification": justification.to_dict(),
                "winner": justification.decision,
                "confidence": justification.confidence,
                "timestamp": time.time(),
            }

            self._recommendations.append(result)
            self._publish("recommendation", result)
            return result

    def _build_strategies(self, strategies: list[dict[str, Any]]) -> list[Strategy]:
        return [
            Strategy(
                id=s.get("id", str(i)),
                name=s.get("name", f"strategy_{i}"),
                description=s.get("description", ""),
                scores=dict(s.get("scores", {})),
            )
            for i, s in enumerate(strategies)
        ]

    def _build_criteria(self, context: dict[str, Any]) -> list[Criterion]:
        constraints = context.get("constraints", {})
        criteria = [
            Criterion(name="speed", weight=constraints.get("speed_weight", 1.0)),
            Criterion(name="accuracy", weight=constraints.get("accuracy_weight", 1.0)),
            Criterion(name="risk", weight=constraints.get("risk_weight", 1.0)),
            Criterion(name="resource_efficiency", weight=constraints.get("efficiency_weight", 0.8)),
        ]
        return criteria

    def _build_justification(
        self,
        best_strategy: Strategy | None,
        comparison: ComparisonResult,
        context: dict[str, Any],
    ) -> Justification:
        decision = best_strategy.name if best_strategy else "no_viable_strategy"
        goal = context.get("goal", "")
        reasoning = (
            f"Strategy '{decision}' ranked highest among "
            f"{len(comparison.strategies)} alternatives "
            f"based on weighted criteria evaluation."
        )

        alternatives = [s.name for s in comparison.strategies[1:]]
        evidence_sources = context.get("evidence_sources")

        return self._justifier.generate(
            decision=decision,
            reasoning=reasoning,
            alternatives=alternatives,
            evidence_sources=evidence_sources,
        )

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def list_recommendations(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._recommendations)

    def get_recommendation_count(self) -> int:
        with self._lock:
            return len(self._recommendations)

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    def health(self) -> dict[str, Any]:
        with self._lock:
            return {
                "alive": True,
                "uptime_seconds": time.time() - self._started_at,
                "recommendations": len(self._recommendations),
                "comparator_available": True,
                "justifier_available": True,
            }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _publish(self, event: str, data: dict[str, Any]) -> None:
        if self._event_bus:
            try:
                self._event_bus.publish(f"reasoner.{event}", data)
            except Exception:
                pass
