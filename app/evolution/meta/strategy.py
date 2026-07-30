from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from app.evolution.meta.analyzer import EVOLUTION_AREAS


@dataclass
class EvolutionStrategy:
    strategy_id: str = ""
    name: str = ""
    description: str = ""
    target_areas: list[str] = field(default_factory=list)
    expected_impact: float = 0.0
    execution_order: list[str] = field(default_factory=list)
    timestamp: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy_id": self.strategy_id,
            "name": self.name,
            "description": self.description,
            "target_areas": list(self.target_areas),
            "expected_impact": self.expected_impact,
            "execution_order": list(self.execution_order),
            "timestamp": self.timestamp,
        }


PREDEFINED_STRATEGIES: list[dict[str, Any]] = [
    {
        "name": "conservative",
        "description": "Focus on low-risk improvements with high success probability",
        "expected_impact": 0.3,
    },
    {
        "name": "balanced",
        "description": "Mix of medium-risk improvements across all areas",
        "expected_impact": 0.5,
    },
    {
        "name": "aggressive",
        "description": "Pursue high-impact improvements even with elevated risk",
        "expected_impact": 0.8,
    },
    {
        "name": "area_focus",
        "description": "Deep improvement in the most critical evolution area",
        "expected_impact": 0.6,
    },
    {
        "name": "cross_area",
        "description": "Improve integration and consistency across all evolution areas",
        "expected_impact": 0.7,
    },
]


class MetaStrategySelector:
    """Selects and manages evolution strategies.

    Chooses the best strategy based on current state,
    past performance, and risk tolerance.
    """

    def __init__(self, event_bus: Any = None, graph_store: Any = None) -> None:
        self._bus = event_bus
        self._graph = graph_store
        self._lock = threading.RLock()
        self._strategies: dict[str, EvolutionStrategy] = {}
        self._strategy_performance: dict[str, list[float]] = {}

    def get_strategy(self, name: str) -> EvolutionStrategy | None:
        with self._lock:
            return self._strategies.get(name)

    def select_strategy(self, risk_tolerance: float = 0.5) -> EvolutionStrategy:
        if risk_tolerance < 0.3:
            chosen = "conservative"
        elif risk_tolerance < 0.6:
            chosen = "balanced"
        elif risk_tolerance < 0.8:
            chosen = "area_focus"
        else:
            chosen = "aggressive"

        with self._lock:
            self._strategy_performance.setdefault(chosen, [])
            if chosen in self._strategies:
                return self._strategies[chosen]

        areas = ["system_evolution", "framework_evolution", "ads_evolution"]
        if chosen in ("area_focus", "cross_area"):
            areas = list(EVOLUTION_AREAS)

        strategy = EvolutionStrategy(
            strategy_id=uuid.uuid4().hex[:16],
            name=chosen,
            description=[s["description"] for s in PREDEFINED_STRATEGIES if s["name"] == chosen][0],
            target_areas=areas,
            expected_impact=[s["expected_impact"] for s in PREDEFINED_STRATEGIES if s["name"] == chosen][0],
            execution_order=areas if chosen != "conservative" else areas[:1],
            timestamp=time.time(),
        )

        if self._bus:
            try:
                self._bus.publish("meta.strategy.selected", strategy.to_dict())
            except Exception:
                pass

        with self._lock:
            self._strategies[chosen] = strategy
        return strategy

    def record_performance(self, strategy_name: str, gain: float) -> None:
        with self._lock:
            self._strategy_performance.setdefault(strategy_name, []).append(gain)

    def get_best_strategy(self) -> str:
        with self._lock:
            best_name = "balanced"
            best_avg = 0.0
            for name, gains in self._strategy_performance.items():
                if gains:
                    avg = sum(gains) / len(gains)
                    if avg > best_avg:
                        best_avg = avg
                        best_name = name
            return best_name

    def get_statistics(self) -> dict[str, Any]:
        with self._lock:
            return {
                "total_strategies": len(self._strategies),
                "strategy_performance": {
                    name: round(sum(gains) / len(gains), 4) if gains else 0.0
                    for name, gains in self._strategy_performance.items()
                },
            }

    def health(self) -> dict[str, Any]:
        return {"alive": True}
