from __future__ import annotations

import threading
import time

import pytest

from app.executive_controller.core import ExecutiveController, SubsystemInfo, SubsystemStatus
from app.executive_controller.priority_manager import PriorityLevel
from app.core.event_bus import EventBus


class TestSubsystemInfo:
    def test_to_dict_contains_keys(self) -> None:
        info = SubsystemInfo(id="test", name="Test Subsystem")
        d = info.to_dict()
        assert d["id"] == "test"
        assert d["name"] == "Test Subsystem"
        assert d["status"] == "pending"
        assert d["priority"] == "MEDIUM"

    def test_to_dict_with_error(self) -> None:
        info = SubsystemInfo(id="test", name="Test", status=SubsystemStatus.FAILED, error="boom")
        d = info.to_dict()
        assert d["status"] == "failed"
        assert d["error"] == "boom"


class TestExecutiveControllerRegistration:
    def test_register_adds_subsystem(self) -> None:
        ec = ExecutiveController()
        ec.register("test", "Test Subsystem")
        info = ec.get_subsystem("test")
        assert info is not None
        assert info.id == "test"
        assert info.name == "Test Subsystem"

    def test_register_duplicate_raises(self) -> None:
        ec = ExecutiveController()
        ec.register("test", "Test")
        with pytest.raises(ValueError, match="already registered"):
            ec.register("test", "Test")

    def test_register_with_dependencies(self) -> None:
        ec = ExecutiveController()
        ec.register("child", dependencies=["parent"])
        info = ec.get_subsystem("child")
        assert info is not None
        assert info.dependencies == ["parent"]

    def test_unregister_removes_subsystem(self) -> None:
        ec = ExecutiveController()
        ec.register("test", "Test")
        assert ec.unregister("test") is True
        assert ec.get_subsystem("test") is None

    def test_unregister_nonexistent_returns_true(self) -> None:
        ec = ExecutiveController()
        assert ec.unregister("nothing") is True

    def test_get_all_subsystems(self) -> None:
        ec = ExecutiveController()
        ec.register("a", "A")
        ec.register("b", "B")
        assert len(ec.get_all_subsystems()) == 2

    def test_properties(self) -> None:
        ec = ExecutiveController()
        assert ec.subsystem_count == 0
        assert ec.running is False
        assert ec.uptime == 0.0
        assert ec.startup_order == []


class TestExecutiveControllerStartup:
    def test_start_runs_startup_hooks_in_order(self) -> None:
        ec = ExecutiveController()
        order: list[str] = []

        def start_a() -> None:
            order.append("a")

        def start_b() -> None:
            order.append("b")

        ec.register("a", startup=start_a)
        ec.register("b", dependencies=["a"], startup=start_b)
        ec.start()
        assert order == ["a", "b"]

    def test_start_respects_dependency_order(self) -> None:
        ec = ExecutiveController()
        order: list[str] = []

        def make_start(name: str):
            def fn() -> None:
                order.append(name)
            return fn

        ec.register("db", startup=make_start("db"))
        ec.register("cache", dependencies=["db"], startup=make_start("cache"))
        ec.register("app", dependencies=["cache", "db"], startup=make_start("app"))
        ec.start()
        assert order.index("db") < order.index("cache")
        assert order.index("cache") < order.index("app")

    def test_start_sets_running_true(self) -> None:
        ec = ExecutiveController()
        ec.register("a", startup=lambda: None)
        ec.start()
        assert ec.running is True

    def test_start_idempotent(self) -> None:
        ec = ExecutiveController()
        count = 0

        def start() -> None:
            nonlocal count
            count += 1

        ec.register("a", startup=start)
        ec.start()
        ec.start()
        assert count == 1

    def test_start_reports_failed_subsystems(self) -> None:
        ec = ExecutiveController()

        def fail() -> None:
            raise RuntimeError("startup error")

        ec.register("good", startup=lambda: None)
        ec.register("bad", startup=fail)
        failed = ec.start()
        assert "bad" in failed
        assert "good" not in failed

    def test_failed_subsystem_has_failed_status(self) -> None:
        ec = ExecutiveController()

        def fail() -> None:
            raise RuntimeError("boom")

        ec.register("bad", startup=fail)
        ec.start()
        info = ec.get_subsystem("bad")
        assert info is not None
        assert info.status == SubsystemStatus.FAILED
        assert info.error is not None

    def test_circular_dependency_raises(self) -> None:
        ec = ExecutiveController()
        ec.register("a", dependencies=["b"])
        ec.register("b", dependencies=["a"])
        with pytest.raises(ValueError, match="Circular dependency"):
            ec.start()

    def test_start_publishes_events(self) -> None:
        bus = EventBus()
        ec = ExecutiveController(event_bus=bus)
        events: list[str] = []
        bus.subscribe_wildcard("ec.*", lambda ev, **kw: events.append(ev))
        ec.register("a", startup=lambda: None)
        ec.start()
        assert "ec.starting" in events
        assert "ec.started" in events

    def test_start_publishes_subsystem_events(self) -> None:
        bus = EventBus()
        ec = ExecutiveController(event_bus=bus)
        events: list[str] = []
        bus.subscribe_wildcard("ec.subsystem.*", lambda ev, **kw: events.append(ev))
        ec.register("a", startup=lambda: None)
        ec.start()
        assert "ec.subsystem.starting" in events
        assert "ec.subsystem.started" in events


class TestExecutiveControllerShutdown:
    def test_stop_shuts_down_in_reverse_order(self) -> None:
        ec = ExecutiveController()
        order: list[str] = []

        def make(name: str):
            def start() -> None:
                order.append(f"start-{name}")
            def stop() -> None:
                order.append(f"stop-{name}")
            return start, stop

        s1, h1 = make("a")
        s2, h2 = make("b")
        ec.register("a", startup=s1, shutdown=h1)
        ec.register("b", dependencies=["a"], startup=s2, shutdown=h2)
        ec.start()
        order.clear()
        ec.stop()
        assert order == ["stop-b", "stop-a"]

    def test_stop_respects_timeout(self) -> None:
        ec = ExecutiveController(shutdown_timeout=0.1)

        def slow() -> None:
            time.sleep(1.0)

        ec.register("a", shutdown=slow)
        ec.start()
        failed = ec.stop()
        assert "a" not in failed

    def test_stop_sets_running_false(self) -> None:
        ec = ExecutiveController()
        ec.register("a", startup=lambda: None)
        ec.start()
        ec.stop()
        assert ec.running is False

    def test_stop_when_not_started(self) -> None:
        ec = ExecutiveController()
        result = ec.stop()
        assert result == []

    def test_stop_publishes_events(self) -> None:
        bus = EventBus()
        ec = ExecutiveController(event_bus=bus)
        events: list[str] = []
        bus.subscribe_wildcard("ec.*", lambda ev, **kw: events.append(ev))
        ec.register("a", startup=lambda: None, shutdown=lambda: None)
        ec.start()
        ec.stop()
        assert "ec.shutdown_starting" in events
        assert "ec.shutdown_complete" in events

    def test_shutdown_failure_does_not_block_others(self) -> None:
        ec = ExecutiveController()
        order: list[str] = []

        def ok_stop() -> None:
            order.append("ok")

        def bad_stop() -> None:
            order.append("bad")
            raise RuntimeError("shutdown error")

        ec.register("ok", startup=lambda: None, shutdown=ok_stop)
        ec.register("bad", startup=lambda: None, shutdown=bad_stop)
        ec.start()
        ec.stop()
        assert "ok" in order
        assert "bad" in order

    def test_shutdown_failure_recorded(self) -> None:
        ec = ExecutiveController()

        def bad_stop() -> None:
            raise RuntimeError("shutdown error")

        ec.register("bad", startup=lambda: None, shutdown=bad_stop)
        ec.start()
        failed = ec.stop()
        assert "bad" in failed


class TestExecutiveControllerHealth:
    def test_health_returns_dict(self) -> None:
        ec = ExecutiveController()
        h = ec.health()
        assert isinstance(h, dict)
        assert "alive" in h
        assert "uptime_seconds" in h

    def test_health_alive_when_running(self) -> None:
        ec = ExecutiveController()
        ec.register("a", startup=lambda: None)
        ec.start()
        h = ec.health()
        assert h["alive"] is True

    def test_health_reports_subsystem_counts(self) -> None:
        ec = ExecutiveController()
        ec.register("a", startup=lambda: None)
        ec.register("b", startup=lambda: None)
        ec.start()
        h = ec.health()
        assert h["subsystems"]["total"] == 2
        assert h["subsystems"]["running"] == 2

    def test_health_reports_failed_subsystem(self) -> None:
        ec = ExecutiveController()

        def fail() -> None:
            raise RuntimeError("boom")

        ec.register("bad", startup=fail)
        ec.start()
        h = ec.health()
        assert h["subsystems"]["failed"] == 1


class TestExecutiveControllerIntegration:
    def test_resource_manager_and_priority_manager_available(self) -> None:
        ec = ExecutiveController()
        assert ec.resource_manager is not None
        assert ec.priority_manager is not None

    def test_register_sets_priority_in_priority_manager(self) -> None:
        ec = ExecutiveController()
        ec.register("critical-svc", priority=PriorityLevel.CRITICAL)
        assert ec.priority_manager.get_priority("critical-svc") == PriorityLevel.CRITICAL

    def test_register_tracks_in_resource_manager(self) -> None:
        ec = ExecutiveController()
        ec.register("tracked-svc")
        assert ec.resource_manager.is_tracked("tracked-svc") is True

    def test_unregister_cleans_up_managers(self) -> None:
        ec = ExecutiveController()
        ec.register("svc")
        ec.unregister("svc")
        assert ec.priority_manager.get_priority("svc") == PriorityLevel.MEDIUM
        assert ec.resource_manager.is_tracked("svc") is False

    def test_full_lifecycle(self) -> None:
        bus = EventBus()
        ec = ExecutiveController(event_bus=bus)
        events: list[str] = []
        bus.subscribe_wildcard("ec.*", lambda ev, **kw: events.append(ev))

        started: list[str] = []
        stopped: list[str] = []

        ec.register("db", "Database",
            startup=lambda: started.append("db"),
            shutdown=lambda: stopped.append("db"))
        ec.register("app", "Application",
            dependencies=["db"],
            startup=lambda: started.append("app"),
            shutdown=lambda: stopped.append("app"))

        assert ec.subsystem_count == 2
        assert ec.get_subsystem("db") is not None

        ec.start()
        assert ec.running is True
        assert ec.uptime > 0
        assert started == ["db", "app"]
        assert len(ec.startup_order) > 0

        ec.stop()
        assert ec.running is False
        assert stopped == ["app", "db"]

    def test_thread_safety(self) -> None:
        ec = ExecutiveController()
        errors: list[Exception] = []

        def register_worker() -> None:
            for i in range(50):
                try:
                    ec.register(f"svc-{i}", startup=lambda: None)
                except ValueError:
                    pass

        def start_worker() -> None:
            try:
                ec.start()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=register_worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        ec.start()
        assert ec.running is True
