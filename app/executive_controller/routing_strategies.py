from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from collections import defaultdict
from typing import Any


class RoutingStrategy(ABC):
    @abstractmethod
    def select(self, candidates: list[str], loads: dict[str, float], **kwargs: Any) -> str | None:
        ...

    @abstractmethod
    def name(self) -> str:
        ...


class RoundRobinStrategy(RoutingStrategy):
    """Distributes tasks evenly across available agents in rotation."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._index: dict[str, int] = defaultdict(int)

    def select(self, candidates: list[str], loads: dict[str, float], **kwargs: Any) -> str | None:
        if not candidates:
            return None
        with self._lock:
            key = "|".join(sorted(candidates))
            idx = self._index[key] % len(candidates)
            self._index[key] = idx + 1
            return candidates[idx]

    def name(self) -> str:
        return "round-robin"


class LeastLoadedStrategy(RoutingStrategy):
    """Routes to the agent with the lowest current load."""

    def select(self, candidates: list[str], loads: dict[str, float], **kwargs: Any) -> str | None:
        if not candidates:
            return None
        return min(candidates, key=lambda c: loads.get(c, 0.0))

    def name(self) -> str:
        return "least-loaded"


class WeightedStrategy(RoutingStrategy):
    """Routes based on agent weights (capacity). Higher weight = more tasks."""

    def __init__(self, weights: dict[str, float] | None = None) -> None:
        self._lock = threading.RLock()
        self._weights: dict[str, float] = dict(weights or {})

    def set_weight(self, agent_id: str, weight: float) -> None:
        with self._lock:
            self._weights[agent_id] = max(0.0, weight)

    def get_weight(self, agent_id: str) -> float:
        with self._lock:
            return self._weights.get(agent_id, 1.0)

    def remove_weight(self, agent_id: str) -> bool:
        with self._lock:
            if agent_id in self._weights:
                del self._weights[agent_id]
                return True
            return False

    def select(self, candidates: list[str], loads: dict[str, float], **kwargs: Any) -> str | None:
        if not candidates:
            return None
        with self._lock:
            total_weight = sum(self._weights.get(c, 1.0) for c in candidates)
            if total_weight <= 0:
                return candidates[0]
            scores = {
                c: self._weights.get(c, 1.0) / (loads.get(c, 0.0) + 1.0)
                for c in candidates
            }
            return max(scores, key=scores.__getitem__)

    def name(self) -> str:
        return "weighted"


class AffinityStrategy(RoutingStrategy):
    """Routes to the same agent for the same task type or source.

    Implements 'sticky sessions' — tasks with the same affinity key
    are consistently routed to the same agent.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._affinity_map: dict[str, str] = {}

    def select(self, candidates: list[str], loads: dict[str, float], **kwargs: Any) -> str | None:
        affinity_key: str | None = kwargs.get("affinity_key")
        if not candidates:
            return None
        if affinity_key:
            with self._lock:
                preferred = self._affinity_map.get(affinity_key)
                if preferred and preferred in candidates:
                    return preferred
                chosen = candidates[0]
                self._affinity_map[affinity_key] = chosen
                return chosen
        return candidates[0] if candidates else None

    def name(self) -> str:
        return "affinity"

    def clear_affinity(self, affinity_key: str) -> None:
        with self._lock:
            self._affinity_map.pop(affinity_key, None)

    def get_affinity(self, affinity_key: str) -> str | None:
        with self._lock:
            return self._affinity_map.get(affinity_key)
