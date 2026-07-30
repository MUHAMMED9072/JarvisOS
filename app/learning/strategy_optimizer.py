from __future__ import annotations

import collections
import math
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from app.learning.pattern_recognition import PatternRecognizer


@dataclass
class ABTestResult:
    test_id: str = ""
    strategy_a_name: str = ""
    strategy_b_name: str = ""
    a_success_rate: float = 0.0
    b_success_rate: float = 0.0
    a_avg_latency: float = 0.0
    b_avg_latency: float = 0.0
    a_sample_count: int = 0
    b_sample_count: int = 0
    winner: str = ""
    confidence: float = 0.0
    duration_hours: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "test_id": self.test_id,
            "strategy_a": self.strategy_a_name,
            "strategy_b": self.strategy_b_name,
            "a_success_rate": round(self.a_success_rate, 4),
            "b_success_rate": round(self.b_success_rate, 4),
            "a_avg_latency": round(self.a_avg_latency, 4),
            "b_avg_latency": round(self.b_avg_latency, 4),
            "a_samples": self.a_sample_count,
            "b_samples": self.b_sample_count,
            "winner": self.winner,
            "confidence": round(self.confidence, 4),
            "duration_hours": round(self.duration_hours, 2),
        }


@dataclass
class OptimizationSuggestion:
    suggestion_id: str = ""
    target: str = ""
    metric: str = ""
    current_value: float = 0.0
    suggested_value: float = 0.0
    expected_improvement: float = 0.0
    rationale: str = ""
    priority: str = "medium"

    def to_dict(self) -> dict[str, Any]:
        return {
            "suggestion_id": self.suggestion_id,
            "target": self.target,
            "metric": self.metric,
            "current_value": round(self.current_value, 4),
            "suggested_value": round(self.suggested_value, 4),
            "expected_improvement": round(self.expected_improvement, 4),
            "rationale": self.rationale,
            "priority": self.priority,
        }


class StrategyOptimizer:
    """Optimizes Planner, Reasoner, and Decision Engine strategies.

    Analyzes past decisions and their outcomes to generate
    optimization suggestions and supports A/B testing.
    """

    def __init__(
        self,
        pattern_recognizer: PatternRecognizer | None = None,
    ) -> None:
        self._recognizer = pattern_recognizer
        self._lock = threading.RLock()
        self._decisions: list[dict[str, Any]] = []
        self._ab_tests: dict[str, ABTestResult] = {}
        self._max_decisions = 10000

    def record_decision(
        self,
        decision_type: str = "",
        strategy: str = "",
        outcome: bool = False,
        latency: float = 0.0,
        context: dict[str, Any] | None = None,
    ) -> None:
        record = {
            "decision_id": uuid.uuid4().hex[:16],
            "decision_type": decision_type,
            "strategy": strategy,
            "outcome": outcome,
            "latency": latency,
            "context": context or {},
            "timestamp": time.time(),
        }
        with self._lock:
            self._decisions.append(record)
            if len(self._decisions) > self._max_decisions:
                self._decisions = self._decisions[-self._max_decisions:]

    def analyze_planner_optimization(self) -> list[OptimizationSuggestion]:
        with self._lock:
            planner_decisions = [
                d for d in self._decisions
                if d["decision_type"] == "planner"
            ]

        if len(planner_decisions) < 5:
            return []

        strategy_groups: dict[str, list[dict[str, Any]]] = {}
        for d in planner_decisions:
            strat = d.get("strategy", "default")
            if strat not in strategy_groups:
                strategy_groups[strat] = []
            strategy_groups[strat].append(d)

        suggestions: list[OptimizationSuggestion] = []
        for strategy, group in strategy_groups.items():
            success_rate = sum(1 for d in group if d["outcome"]) / len(group)
            avg_lat = sum(d["latency"] for d in group) / len(group)

            if success_rate < 0.6:
                suggestions.append(OptimizationSuggestion(
                    suggestion_id=uuid.uuid4().hex[:16],
                    target="planner",
                    metric="success_rate",
                    current_value=success_rate,
                    suggested_value=min(success_rate + 0.15, 1.0),
                    expected_improvement=0.15,
                    rationale=f"Strategy '{strategy}' has low success rate ({success_rate:.0%}). Consider alternative task decomposition approach.",
                    priority="high" if success_rate < 0.4 else "medium",
                ))

            if avg_lat > 5.0:
                suggestions.append(OptimizationSuggestion(
                    suggestion_id=uuid.uuid4().hex[:16],
                    target="planner",
                    metric="latency",
                    current_value=avg_lat,
                    suggested_value=max(avg_lat * 0.7, 0.1),
                    expected_improvement=avg_lat * 0.3,
                    rationale=f"Strategy '{strategy}' high avg latency ({avg_lat:.2f}s). Consider parallelizing independent tasks.",
                    priority="medium",
                ))

        return suggestions

    def analyze_reasoner_optimization(self) -> list[OptimizationSuggestion]:
        with self._lock:
            reasoner_decisions = [
                d for d in self._decisions
                if d["decision_type"] == "reasoner"
            ]

        if len(reasoner_decisions) < 5:
            return []

        criteria_groups: dict[str, list[dict[str, Any]]] = {}
        for d in reasoner_decisions:
            ctx = d.get("context", {})
            criteria = ctx.get("criteria", ctx.get("method", "default"))
            if criteria not in criteria_groups:
                criteria_groups[criteria] = []
            criteria_groups[criteria].append(d)

        suggestions: list[OptimizationSuggestion] = []
        for criteria, group in criteria_groups.items():
            success_rate = sum(1 for d in group if d["outcome"]) / len(group)
            if success_rate < 0.6:
                suggestions.append(OptimizationSuggestion(
                    suggestion_id=uuid.uuid4().hex[:16],
                    target="reasoner",
                    metric="criteria_accuracy",
                    current_value=success_rate,
                    suggested_value=min(success_rate + 0.2, 1.0),
                    expected_improvement=0.2,
                    rationale=f"Reasoning criteria '{criteria}' accuracy is low ({success_rate:.0%}). Adjust comparison weights.",
                    priority="high" if success_rate < 0.4 else "medium",
                ))

        return suggestions

    def analyze_decision_optimization(self) -> list[OptimizationSuggestion]:
        with self._lock:
            decision_decisions = [
                d for d in self._decisions
                if d["decision_type"] == "decision_engine"
            ]

        if len(decision_decisions) < 5:
            return []

        agent_weights: dict[str, list[dict[str, Any]]] = {}
        for d in decision_decisions:
            agent = d.get("context", {}).get("selected_agent", d.get("strategy", "unknown"))
            if agent not in agent_weights:
                agent_weights[agent] = []
            agent_weights[agent].append(d)

        suggestions: list[OptimizationSuggestion] = []
        for agent, group in agent_weights.items():
            success_rate = sum(1 for d in group if d["outcome"]) / len(group)
            if success_rate < 0.5 and len(group) >= 3:
                suggestions.append(OptimizationSuggestion(
                    suggestion_id=uuid.uuid4().hex[:16],
                    target="decision_engine",
                    metric="agent_selection_weight",
                    current_value=success_rate,
                    suggested_value=max(success_rate - 0.1, 0.0),
                    expected_improvement=0.1,
                    rationale=f"Agent '{agent}' low success rate ({success_rate:.0%}). Reduce selection weight.",
                    priority="medium",
                ))

        return suggestions

    def run_ab_test(
        self,
        strategy_a: str,
        strategy_b: str,
        test_duration_hours: float = 24.0,
    ) -> ABTestResult:
        test_id = uuid.uuid4().hex[:16]
        result = ABTestResult(
            test_id=test_id,
            strategy_a_name=strategy_a,
            strategy_b_name=strategy_b,
        )

        with self._lock:
            relevant = [
                d for d in self._decisions
                if d.get("strategy") in (strategy_a, strategy_b)
            ]

        group_a = [d for d in relevant if d["strategy"] == strategy_a]
        group_b = [d for d in relevant if d["strategy"] == strategy_b]

        if group_a:
            result.a_success_rate = sum(1 for d in group_a if d["outcome"]) / len(group_a)
            result.a_avg_latency = sum(d["latency"] for d in group_a) / len(group_a)
            result.a_sample_count = len(group_a)

        if group_b:
            result.b_success_rate = sum(1 for d in group_b if d["outcome"]) / len(group_b)
            result.b_avg_latency = sum(d["latency"] for d in group_b) / len(group_b)
            result.b_sample_count = len(group_b)

        if result.a_success_rate > result.b_success_rate:
            result.winner = strategy_a
        elif result.b_success_rate > result.a_success_rate:
            result.winner = strategy_b
        else:
            result.winner = "tie"

        diff = abs(result.a_success_rate - result.b_success_rate)
        result.confidence = min(diff * 5, 1.0)
        result.duration_hours = test_duration_hours

        with self._lock:
            self._ab_tests[test_id] = result

        return result

    def get_optimization_suggestions(self) -> list[OptimizationSuggestion]:
        suggestions: list[OptimizationSuggestion] = []
        suggestions.extend(self.analyze_planner_optimization())
        suggestions.extend(self.analyze_reasoner_optimization())
        suggestions.extend(self.analyze_decision_optimization())
        return suggestions

    def get_ab_test_results(self) -> list[ABTestResult]:
        with self._lock:
            return list(self._ab_tests.values())

    def get_statistics(self) -> dict[str, Any]:
        with self._lock:
            total = len(self._decisions)
            by_type: dict[str, int] = {}
            for d in self._decisions:
                dt = d.get("decision_type", "unknown")
                by_type[dt] = by_type.get(dt, 0) + 1
        return {
            "total_decisions": total,
            "decisions_by_type": by_type,
            "ab_tests_performed": len(self._ab_tests),
            "optimization_suggestions": len(self.get_optimization_suggestions()),
        }

    def health(self) -> dict[str, Any]:
        stats = self.get_statistics()
        return {
            "alive": True,
            "decisions_recorded": stats["total_decisions"],
            "ab_tests_performed": stats["ab_tests_performed"],
            "active_suggestions": stats["optimization_suggestions"],
        }
