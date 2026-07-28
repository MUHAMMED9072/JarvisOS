from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from app.executive_controller.routing_strategies import (
    AffinityStrategy,
    LeastLoadedStrategy,
    RoundRobinStrategy,
    RoutingStrategy,
    WeightedStrategy,
)


@dataclass
class AgentLoad:
    agent_id: str
    active_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    total_task_time: float = 0.0
    capacity: float = 1.0
    overloaded: bool = False
    last_selected: float = 0.0
    created_at: float = field(default_factory=time.time)

    @property
    def load_factor(self) -> float:
        if self.capacity <= 0:
            return 1.0
        return self.active_tasks / self.capacity

    @property
    def avg_task_time(self) -> float:
        if self.completed_tasks == 0:
            return 0.0
        return self.total_task_time / self.completed_tasks

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "active_tasks": self.active_tasks,
            "completed_tasks": self.completed_tasks,
            "failed_tasks": self.failed_tasks,
            "total_task_time": self.total_task_time,
            "capacity": self.capacity,
            "load_factor": self.load_factor,
            "overloaded": self.overloaded,
            "avg_task_time": self.avg_task_time,
            "last_selected": self.last_selected,
        }


class LoadBalancer:
    """Distributes tasks across registered agents using configurable
    routing strategies.

    Features:
      - Multiple routing strategies (round-robin, least-loaded, weighted,
        affinity-based)
      - Agent overload detection and backpressure
      - Dynamic scaling support (if agent provides a scaling callback)
      - Per-agent load metrics tracking

    Thread-safe.
    """

    def __init__(
        self,
        strategy: RoutingStrategy | None = None,
        overload_threshold: float = 0.9,
        scale_up_callback: Callable[[str], None] | None = None,
        scale_down_callback: Callable[[str], None] | None = None,
    ) -> None:
        self._strategy = strategy or RoundRobinStrategy()
        self._overload_threshold = overload_threshold
        self._scale_up = scale_up_callback
        self._scale_down = scale_down_callback

        self._lock = threading.RLock()
        self._agents: dict[str, AgentLoad] = {}
        self._strategy_lock = threading.RLock()
        self._routing_count: int = 0
        self._overload_events: int = 0
        self._last_metrics_publish: float = 0.0

    # ------------------------------------------------------------------
    # Agent management
    # ------------------------------------------------------------------

    def register_agent(self, agent_id: str, capacity: float = 1.0) -> None:
        with self._lock:
            self._agents.setdefault(agent_id, AgentLoad(
                agent_id=agent_id, capacity=max(0.1, capacity),
            ))

    def unregister_agent(self, agent_id: str) -> bool:
        with self._lock:
            if agent_id in self._agents:
                del self._agents[agent_id]
                return True
            return False

    def set_capacity(self, agent_id: str, capacity: float) -> None:
        with self._lock:
            load = self._agents.get(agent_id)
            if load:
                load.capacity = max(0.1, capacity)

    def get_agent_load(self, agent_id: str) -> AgentLoad | None:
        with self._lock:
            return self._agents.get(agent_id)

    def get_all_loads(self) -> list[AgentLoad]:
        with self._lock:
            return list(self._agents.values())

    def _get_loads_dict(self) -> dict[str, float]:
        return {
            aid: al.load_factor
            for aid, al in self._agents.items()
        }

    # ------------------------------------------------------------------
    # Routing
    # ------------------------------------------------------------------

    def select(self, affinity_key: str | None = None, **kwargs: Any) -> str | None:
        with self._lock:
            candidates = self._get_available_agents()
            if not candidates:
                return None
            loads = self._get_loads_dict()
            kwargs["affinity_key"] = affinity_key
            chosen = self._strategy.select(candidates, loads, **kwargs)
            if chosen:
                self._agents[chosen].active_tasks += 1
                self._agents[chosen].last_selected = time.time()
                self._routing_count += 1
                self._check_overload(chosen)
            return chosen

    def task_started(self, agent_id: str) -> None:
        with self._lock:
            load = self._agents.get(agent_id)
            if load:
                load.active_tasks += 1
                self._check_overload(agent_id)

    def task_completed(self, agent_id: str, duration: float = 0.0, success: bool = True) -> None:
        with self._lock:
            load = self._agents.get(agent_id)
            if load:
                load.active_tasks = max(0, load.active_tasks - 1)
                load.completed_tasks += 1
                load.total_task_time += duration
                if not success:
                    load.failed_tasks += 1

    def get_available_agents(self, affinity_key: str | None = None) -> list[str]:
        with self._lock:
            return self._get_available_agents()

    def _get_available_agents(self) -> list[str]:
        return [
            aid for aid, al in self._agents.items()
            if not al.overloaded
        ]

    def _check_overload(self, agent_id: str) -> None:
        load = self._agents.get(agent_id)
        if load is None:
            return
        if load.load_factor >= self._overload_threshold and not load.overloaded:
            load.overloaded = True
            self._overload_events += 1
            if self._scale_up:
                try:
                    self._scale_up(agent_id)
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # Strategy
    # ------------------------------------------------------------------

    @property
    def strategy(self) -> RoutingStrategy:
        return self._strategy

    @strategy.setter
    def strategy(self, s: RoutingStrategy) -> None:
        self._strategy = s

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> dict[str, Any]:
        with self._lock:
            agents = list(self._agents.values())
            total_active = sum(a.active_tasks for a in agents)
            total_completed = sum(a.completed_tasks for a in agents)
            overloaded_count = sum(1 for a in agents if a.overloaded)
            return {
                "agents_registered": len(agents),
                "agents_available": len(self._get_available_agents()),
                "agents_overloaded": overloaded_count,
                "total_active_tasks": total_active,
                "total_completed_tasks": total_completed,
                "routing_count": self._routing_count,
                "overload_events": self._overload_events,
                "strategy": self._strategy.name(),
                "overload_threshold": self._overload_threshold,
            }

    def health(self) -> dict[str, Any]:
        return self.get_stats()
