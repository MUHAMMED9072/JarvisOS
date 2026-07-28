from __future__ import annotations

import threading
import time

from app.executive_controller.load_balancer import AgentLoad, LoadBalancer
from app.executive_controller.routing_strategies import (
    AffinityStrategy,
    LeastLoadedStrategy,
    RoundRobinStrategy,
    WeightedStrategy,
)


class TestAgentLoad:
    def test_defaults(self) -> None:
        al = AgentLoad(agent_id="test")
        assert al.agent_id == "test"
        assert al.active_tasks == 0
        assert al.overloaded is False

    def test_load_factor(self) -> None:
        al = AgentLoad(agent_id="test", active_tasks=5, capacity=10.0)
        assert al.load_factor == 0.5

    def test_load_factor_zero_capacity(self) -> None:
        al = AgentLoad(agent_id="test", active_tasks=5, capacity=0.0)
        assert al.load_factor == 1.0

    def test_avg_task_time(self) -> None:
        al = AgentLoad(agent_id="test", completed_tasks=4, total_task_time=10.0)
        assert al.avg_task_time == 2.5

    def test_avg_task_time_zero(self) -> None:
        al = AgentLoad(agent_id="test")
        assert al.avg_task_time == 0.0

    def test_to_dict(self) -> None:
        al = AgentLoad(agent_id="a", active_tasks=3)
        d = al.to_dict()
        assert d["agent_id"] == "a"
        assert d["active_tasks"] == 3
        assert "load_factor" in d


class TestLoadBalancer:
    def test_register_and_unregister(self) -> None:
        lb = LoadBalancer()
        lb.register_agent("agent-a")
        assert lb.get_agent_load("agent-a") is not None
        assert lb.unregister_agent("agent-a") is True
        assert lb.get_agent_load("agent-a") is None

    def test_unregister_missing(self) -> None:
        lb = LoadBalancer()
        assert lb.unregister_agent("nonexistent") is False

    def test_select_returns_agent(self) -> None:
        lb = LoadBalancer()
        lb.register_agent("agent-a")
        result = lb.select()
        assert result == "agent-a"

    def test_select_no_agents(self) -> None:
        lb = LoadBalancer()
        assert lb.select() is None

    def test_select_round_robin(self) -> None:
        lb = LoadBalancer(strategy=RoundRobinStrategy())
        lb.register_agent("a", capacity=100.0)
        lb.register_agent("b", capacity=100.0)
        results = [lb.select() for _ in range(4)]
        assert results == ["a", "b", "a", "b"]

    def test_select_least_loaded(self) -> None:
        lb = LoadBalancer(strategy=LeastLoadedStrategy(), overload_threshold=1.0)
        lb.register_agent("a", capacity=100.0)
        lb.register_agent("b", capacity=100.0)
        # Both have 0 load, first routes to min load (first)
        first = lb.select()
        # Now the chosen one has active_tasks=1 while the other has 0
        second = lb.select()
        assert second is not None
        assert second != first

    def test_overload_detection(self) -> None:
        lb = LoadBalancer(overload_threshold=0.5)
        lb.register_agent("agent-a", capacity=2.0)
        lb.task_started("agent-a")
        # load_factor = 1.0 > 0.5 after second task_started
        lb.task_started("agent-a")
        load = lb.get_agent_load("agent-a")
        assert load is not None
        assert load.overloaded is True

    def test_overloaded_agent_not_selected(self) -> None:
        lb = LoadBalancer(overload_threshold=0.5)
        lb.register_agent("a", capacity=2.0)
        lb.register_agent("b", capacity=100.0)  # high capacity so it won't overload
        lb.task_started("a")
        lb.task_started("a")  # load_factor = 1.0 > 0.5, overloaded
        assert lb.get_agent_load("a") is not None
        assert lb.get_agent_load("a").overloaded is True
        results = [lb.select() for _ in range(5)]
        assert all(r == "b" for r in results)

    def test_task_completed_reduces_active_tasks(self) -> None:
        lb = LoadBalancer()
        lb.register_agent("a")
        lb.task_started("a")
        assert lb.get_agent_load("a").active_tasks == 1  # type: ignore[union-attr]
        lb.task_completed("a", duration=1.0, success=True)
        load = lb.get_agent_load("a")
        assert load is not None
        assert load.active_tasks == 0
        assert load.completed_tasks == 1
        assert load.total_task_time == 1.0

    def test_task_completed_tracks_failures(self) -> None:
        lb = LoadBalancer()
        lb.register_agent("a")
        lb.task_completed("a", success=False)
        load = lb.get_agent_load("a")
        assert load is not None
        assert load.failed_tasks == 1

    def test_set_capacity(self) -> None:
        lb = LoadBalancer()
        lb.register_agent("a", capacity=5.0)
        lb.set_capacity("a", 10.0)
        load = lb.get_agent_load("a")
        assert load is not None
        assert load.capacity == 10.0

    def test_get_all_loads(self) -> None:
        lb = LoadBalancer()
        lb.register_agent("a")
        lb.register_agent("b")
        assert len(lb.get_all_loads()) == 2

    def test_get_stats(self) -> None:
        lb = LoadBalancer()
        lb.register_agent("a")
        lb.register_agent("b")
        lb.select()
        stats = lb.get_stats()
        assert stats["agents_registered"] == 2
        assert stats["routing_count"] == 1
        assert stats["strategy"] == "round-robin"

    def test_health(self) -> None:
        lb = LoadBalancer()
        h = lb.health()
        assert "agents_registered" in h

    def test_strategy_property(self) -> None:
        lb = LoadBalancer(strategy=LeastLoadedStrategy())
        assert lb.strategy.name() == "least-loaded"
        lb.strategy = RoundRobinStrategy()
        assert lb.strategy.name() == "round-robin"

    def test_select_with_affinity(self) -> None:
        lb = LoadBalancer(strategy=AffinityStrategy())
        lb.register_agent("a", capacity=100.0)
        lb.register_agent("b", capacity=100.0)
        first = lb.select(affinity_key="task-x")
        second = lb.select(affinity_key="task-x")
        assert first == second

    def test_scale_up_callback(self) -> None:
        scaled: list[str] = []

        def scale_up(agent_id: str) -> None:
            scaled.append(agent_id)

        lb = LoadBalancer(overload_threshold=0.5, scale_up_callback=scale_up)
        lb.register_agent("a", capacity=1.0)
        lb.task_started("a")
        lb.task_started("a")  # load_factor = 2.0 > 0.5, triggers scale_up
        assert "a" in scaled

    def test_register_agent_idempotent(self) -> None:
        lb = LoadBalancer()
        lb.register_agent("a")
        lb.register_agent("a")  # should not raise
        assert len(lb.get_all_loads()) == 1

    def test_get_available_agents(self) -> None:
        lb = LoadBalancer(overload_threshold=0.5)
        lb.register_agent("a", capacity=2.0)
        lb.register_agent("b", capacity=2.0)
        lb.task_started("a")  # load_factor = 0.5, not overloaded
        lb.task_started("a")  # load_factor = 1.0 > 0.5, overloaded
        available = lb.get_available_agents()
        assert "a" not in available
        assert "b" in available

    def test_thread_safety(self) -> None:
        lb = LoadBalancer()
        lb.register_agent("a")
        lb.register_agent("b")
        errors: list[Exception] = []

        def worker() -> None:
            for _ in range(100):
                try:
                    chosen = lb.select()
                    if chosen:
                        lb.task_completed(chosen, duration=0.1, success=True)
                    lb.get_stats()
                    lb.get_all_loads()
                except Exception as e:
                    errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(errors) == 0
