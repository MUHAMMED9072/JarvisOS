from __future__ import annotations

import threading
import time

import pytest

from app.executive_controller.evolution_coordinator import (
    EvolutionCoordinator,
    EvolutionPlan,
    EvolutionStatus,
    EvolutionWindow,
)
from app.core.event_bus import EventBus


class TestEvolutionStatus:
    def test_ordering(self) -> None:
        assert EvolutionStatus.IDLE.value == "idle"
        assert EvolutionStatus.PLANNING.value == "planning"
        assert EvolutionStatus.EVOLVING.value == "evolving"
        assert EvolutionStatus.COMMITTED.value == "committed"
        assert EvolutionStatus.FAILED.value == "failed"


class TestEvolutionPlan:
    def test_to_dict(self) -> None:
        plan = EvolutionPlan(component_id="comp-a", version="2.0.0")
        d = plan.to_dict()
        assert d["component_id"] == "comp-a"
        assert d["version"] == "2.0.0"
        assert d["status"] == "planning"


class TestEvolutionWindow:
    def test_to_dict(self) -> None:
        w = EvolutionWindow(component_id="comp-a")
        d = w.to_dict()
        assert d["component_id"] == "comp-a"

    def test_is_expired(self) -> None:
        w = EvolutionWindow(component_id="a", closes_at=time.time() - 10)
        assert w.is_expired is True

    def test_remaining(self) -> None:
        w = EvolutionWindow(component_id="a", closes_at=time.time() + 60)
        assert 55 < w.remaining <= 60


class TestEvolutionCoordinator:
    def test_initial_status(self) -> None:
        ec = EvolutionCoordinator()
        assert ec.status == EvolutionStatus.IDLE
        assert ec.active_plan is None
        assert ec.active_window is None

    def test_register_and_get_dependents(self) -> None:
        ec = EvolutionCoordinator()
        ec.register_dependency("agent-a", "tool-x")
        ec.register_dependency("agent-b", "tool-x")
        assert sorted(ec.get_dependents("tool-x")) == ["agent-a", "agent-b"]

    def test_unregister_dependency(self) -> None:
        ec = EvolutionCoordinator()
        ec.register_dependency("a", "x")
        assert ec.unregister_dependency("a", "x") is True
        assert ec.get_dependents("x") == []
        assert ec.unregister_dependency("nonexistent", "x") is False

    def test_block_and_unblock(self) -> None:
        ec = EvolutionCoordinator()
        ec.block_component("comp-a")
        assert ec.is_blocked("comp-a") is True
        assert ec.unblock_component("comp-a") is True
        assert ec.is_blocked("comp-a") is False

    def test_unblock_missing(self) -> None:
        ec = EvolutionCoordinator()
        assert ec.unblock_component("nonexistent") is False

    def test_window_available(self) -> None:
        ec = EvolutionCoordinator()
        assert ec.window_available("comp-a") is True
        ec.block_component("comp-a")
        assert ec.window_available("comp-a") is False

    def test_open_and_close_window(self) -> None:
        ec = EvolutionCoordinator()
        window = ec.open_window("comp-a", duration=30.0)
        assert window.component_id == "comp-a"
        assert window.active is True
        assert ec.status == EvolutionStatus.WINDOW_OPEN
        ec.close_window()
        assert ec.status == EvolutionStatus.IDLE

    def test_open_window_when_busy_raises(self) -> None:
        ec = EvolutionCoordinator()
        ec.open_window("comp-a")
        with pytest.raises(RuntimeError, match="Cannot open"):
            ec.open_window("comp-b")

    def test_plan_and_evolve(self) -> None:
        ec = EvolutionCoordinator()
        ec.register_hot_swap_hook("comp-a", lambda: None)
        plan = ec.plan("comp-a", "Update component", "2.0.0")
        assert plan.component_id == "comp-a"
        assert ec.active_plan is not None
        ec.open_window("comp-a", duration=30.0)
        result = ec.evolve()
        assert result is not None
        assert ec.status == EvolutionStatus.VERIFYING

    def test_evolve_without_window_raises(self) -> None:
        ec = EvolutionCoordinator()
        ec.register_hot_swap_hook("comp-a", lambda: None)
        ec.plan("comp-a", "test")
        with pytest.raises(RuntimeError, match="evolution window not open"):
            ec.evolve()

    def test_evolve_without_plan(self) -> None:
        ec = EvolutionCoordinator()
        assert ec.evolve() is None

    def test_evolve_calls_hot_swap_hook(self) -> None:
        ec = EvolutionCoordinator()
        hook_called: list[bool] = [False]

        def hook() -> None:
            hook_called[0] = True

        ec.register_hot_swap_hook("comp-a", hook)
        ec.plan("comp-a", "test")
        ec.open_window("comp-a", duration=30.0)
        ec.evolve()
        assert hook_called[0] is True

    def test_evolve_hook_failure(self) -> None:
        ec = EvolutionCoordinator()

        def failing_hook() -> None:
            raise RuntimeError("swap failed")

        ec.register_hot_swap_hook("comp-a", failing_hook)
        ec.plan("comp-a", "test")
        ec.open_window("comp-a", duration=30.0)
        result = ec.evolve()
        assert result is not None
        assert result.status == EvolutionStatus.FAILED
        assert ec.status == EvolutionStatus.FAILED

    def test_commit(self) -> None:
        ec = EvolutionCoordinator()
        ec.register_hot_swap_hook("comp-a", lambda: None)
        ec.plan("comp-a", "test", "2.0.0")
        ec.open_window("comp-a", duration=30.0)
        ec.evolve()
        committed = ec.commit()
        assert committed is not None
        assert committed.status == EvolutionStatus.COMMITTED
        assert ec.status == EvolutionStatus.IDLE

    def test_commit_without_evolve_raises(self) -> None:
        ec = EvolutionCoordinator()
        ec.plan("comp-a", "test")
        ec.open_window("comp-a", duration=30.0)
        with pytest.raises(RuntimeError, match="Cannot commit"):
            ec.commit()

    def test_commit_without_plan(self) -> None:
        ec = EvolutionCoordinator()
        assert ec.commit() is None

    def test_rollback(self) -> None:
        ec = EvolutionCoordinator()
        rollback_called: list[bool] = [False]

        def rollback() -> None:
            rollback_called[0] = True

        ec.register_hot_swap_hook("comp-a", lambda: None)
        ec.register_rollback_hook("comp-a", rollback)
        ec.plan("comp-a", "test")
        ec.open_window("comp-a", duration=30.0)
        ec.evolve()
        result = ec.rollback(reason="verification failed")
        assert result is not None
        assert rollback_called[0] is True
        assert ec.status == EvolutionStatus.IDLE

    def test_rollback_without_plan(self) -> None:
        ec = EvolutionCoordinator()
        assert ec.rollback() is None

    def test_window_expired_fails_evolution(self) -> None:
        ec = EvolutionCoordinator()
        ec.register_hot_swap_hook("comp-a", lambda: None)
        ec.plan("comp-a", "test")
        ec.open_window("comp-a", duration=-1.0)  # already expired
        time.sleep(0.01)
        result = ec.evolve()
        assert result is not None
        assert result.status == EvolutionStatus.FAILED
        assert result.error == "Evolution window expired"

    def test_get_completed_evolutions(self) -> None:
        ec = EvolutionCoordinator()
        ec.register_hot_swap_hook("comp-a", lambda: None)
        ec.plan("comp-a", "test")
        ec.open_window("comp-a", duration=30.0)
        ec.evolve()
        ec.commit()
        assert len(ec.get_completed_evolutions()) == 1

    def test_event_publishing(self) -> None:
        bus = EventBus()
        ec = EvolutionCoordinator(event_bus=bus)
        events: list[str] = []
        bus.subscribe_wildcard("ec.evolution.*", lambda ev, **kw: events.append(ev))
        ec.register_hot_swap_hook("comp-a", lambda: None)
        ec.plan("comp-a", "test")
        ec.open_window("comp-a", duration=30.0)
        ec.evolve()
        ec.commit()
        assert "ec.evolution.planned" in events
        assert "ec.evolution.window_open" in events
        assert "ec.evolution.started" in events
        assert "ec.evolution.hot_swapped" in events
        assert "ec.evolution.committed" in events

    def test_register_hot_swap_and_rollback_hooks(self) -> None:
        ec = EvolutionCoordinator()
        ec.register_hot_swap_hook("a", lambda: None)
        ec.register_rollback_hook("a", lambda: None)
        h = ec.health()
        assert h["registered_hooks"] == 1
        assert h["registered_rollback_hooks"] == 1

    def test_health(self) -> None:
        ec = EvolutionCoordinator()
        h = ec.health()
        assert h["status"] == "idle"
        assert h["has_active_plan"] is False

    def test_health_with_active_plan(self) -> None:
        ec = EvolutionCoordinator()
        ec.plan("comp-a", "test")
        h = ec.health()
        assert h["has_active_plan"] is True
        assert h["status"] == "planning"

    def test_thread_safety(self) -> None:
        ec = EvolutionCoordinator()
        errors: list[Exception] = []

        def worker() -> None:
            for i in range(50):
                try:
                    cid = f"comp-{i % 5}"
                    ec.register_dependency(cid, "base")
                    ec.get_dependents("base")
                    ec.is_blocked(cid)
                    ec.health()
                except Exception as e:
                    errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(errors) == 0
