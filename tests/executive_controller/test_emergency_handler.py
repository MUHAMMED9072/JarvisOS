from __future__ import annotations

import threading

import pytest

from app.executive_controller.emergency_handler import (
    ComponentCriticality,
    EmergencyEvent,
    EmergencyHandler,
    EmergencyMode,
    PreservedAgentState,
)
from app.core.event_bus import EventBus


class TestEmergencyMode:
    def test_ordering(self) -> None:
        assert EmergencyMode.NORMAL.value == "normal"
        assert EmergencyMode.SAFE_MODE.value == "safe_mode"
        assert EmergencyMode.LOCKDOWN.value == "lockdown"
        assert EmergencyMode.EMERGENCY_SHUTDOWN.value == "emergency_shutdown"


class TestComponentCriticality:
    def test_ordering(self) -> None:
        assert ComponentCriticality.SYSTEM.value == "system"
        assert ComponentCriticality.HIGH.value == "high"
        assert ComponentCriticality.MEDIUM.value == "medium"
        assert ComponentCriticality.LOW.value == "low"


class TestPreservedAgentState:
    def test_to_dict(self) -> None:
        state = PreservedAgentState(
            agent_id="test-agent",
            state_data={"key": "value"},
            criticality=ComponentCriticality.HIGH,
        )
        d = state.to_dict()
        assert d["agent_id"] == "test-agent"
        assert d["criticality"] == "high"
        assert d["restored"] is False


class TestEmergencyEvent:
    def test_to_dict(self) -> None:
        ev = EmergencyEvent(
            mode=EmergencyMode.SAFE_MODE,
            reason="test",
            triggered_by="admin",
            affected_components=["a", "b"],
        )
        d = ev.to_dict()
        assert d["mode"] == "safe_mode"
        assert d["reason"] == "test"
        assert d["triggered_by"] == "admin"


class TestEmergencyHandler:
    def test_initial_mode_is_normal(self) -> None:
        eh = EmergencyHandler()
        assert eh.mode == EmergencyMode.NORMAL
        assert eh.in_emergency is False

    def test_register_component(self) -> None:
        eh = EmergencyHandler()
        eh.register_component("comp-a", ComponentCriticality.HIGH)
        assert eh.get_criticality("comp-a") == ComponentCriticality.HIGH

    def test_register_component_default_criticality(self) -> None:
        eh = EmergencyHandler()
        eh.register_component("comp-a")
        assert eh.get_criticality("comp-a") == ComponentCriticality.MEDIUM

    def test_unregister_component(self) -> None:
        eh = EmergencyHandler()
        eh.register_component("comp-a")
        assert eh.unregister_component("comp-a") is True

    def test_authorize(self) -> None:
        eh = EmergencyHandler(authorized_triggers={"admin", "system"})
        assert eh.authorize("admin") is True
        assert eh.authorize("unknown") is False

    def test_add_authorized_trigger(self) -> None:
        eh = EmergencyHandler()
        eh.add_authorized_trigger("new-user")
        assert eh.authorize("new-user") is True

    def test_remove_authorized_trigger(self) -> None:
        eh = EmergencyHandler(authorized_triggers={"admin", "user1"})
        assert eh.remove_authorized_trigger("user1") is True
        assert eh.authorize("user1") is False
        assert eh.remove_authorized_trigger("nonexistent") is False

    def test_trigger_emergency_shutdown(self) -> None:
        eh = EmergencyHandler()
        shutdown_called: list[str] = []

        def shutdown() -> None:
            shutdown_called.append("comp-a")

        eh.register_component("comp-a", ComponentCriticality.MEDIUM, shutdown_hook=shutdown)
        eh.register_component("kernel", ComponentCriticality.SYSTEM)
        ev = eh.trigger_emergency_shutdown("test shutdown", "admin")
        assert eh.mode == EmergencyMode.EMERGENCY_SHUTDOWN
        assert eh.in_emergency is True
        assert "comp-a" in ev.affected_components
        assert "kernel" not in ev.affected_components
        assert shutdown_called == ["comp-a"]

    def test_trigger_safe_mode(self) -> None:
        eh = EmergencyHandler()
        shutdown_called: list[str] = []

        def shutdown() -> None:
            shutdown_called.append("comp-a")

        eh.register_component("kernel", ComponentCriticality.SYSTEM)
        eh.register_component("core-svc", ComponentCriticality.HIGH)
        eh.register_component("comp-a", ComponentCriticality.MEDIUM, shutdown_hook=shutdown)
        eh.register_component("comp-b", ComponentCriticality.LOW)

        ev = eh.trigger_safe_mode("maintenance", "admin")
        assert eh.mode == EmergencyMode.SAFE_MODE
        assert "comp-a" in ev.affected_components
        assert "comp-b" in ev.affected_components
        assert "kernel" not in ev.affected_components
        assert "core-svc" not in ev.affected_components

    def test_trigger_resource_lockdown(self) -> None:
        eh = EmergencyHandler()
        ev = eh.trigger_resource_lockdown("resource crisis", "admin")
        assert eh.mode == EmergencyMode.LOCKDOWN
        assert eh.lockdown is True
        assert eh.can_accept_new_tasks() is False

    def test_can_accept_new_tasks_normal(self) -> None:
        eh = EmergencyHandler()
        assert eh.can_accept_new_tasks() is True

    def test_recover_from_shutdown(self) -> None:
        eh = EmergencyHandler()
        started: list[str] = []

        def start() -> None:
            started.append("comp-a")

        eh.register_component("comp-a", ComponentCriticality.MEDIUM, startup_hook=start)
        eh.trigger_emergency_shutdown("test")
        ev = eh.recover("admin")
        assert eh.mode == EmergencyMode.NORMAL
        assert eh.in_emergency is False
        assert eh.can_accept_new_tasks() is True
        assert "comp-a" in ev.affected_components

    def test_unauthorized_trigger_raises(self) -> None:
        eh = EmergencyHandler(authorized_triggers={"admin"})
        with pytest.raises(PermissionError, match="not authorized"):
            eh.trigger_emergency_shutdown("test", "hacker")

    def test_unauthorized_safe_mode_raises(self) -> None:
        eh = EmergencyHandler(authorized_triggers={"admin"})
        with pytest.raises(PermissionError):
            eh.trigger_safe_mode("test", "hacker")

    def test_unauthorized_lockdown_raises(self) -> None:
        eh = EmergencyHandler(authorized_triggers={"admin"})
        with pytest.raises(PermissionError):
            eh.trigger_resource_lockdown("test", "hacker")

    def test_unauthorized_recover_raises(self) -> None:
        eh = EmergencyHandler(authorized_triggers={"admin"})
        with pytest.raises(PermissionError):
            eh.recover("hacker")

    def test_preserved_state_after_shutdown(self) -> None:
        eh = EmergencyHandler()
        eh.register_component("comp-a", ComponentCriticality.MEDIUM)
        eh.trigger_emergency_shutdown("test")
        state = eh.get_preserved_state("comp-a")
        assert state is not None
        assert state.restored is False

    def test_get_all_preserved_states(self) -> None:
        eh = EmergencyHandler()
        eh.register_component("a", ComponentCriticality.LOW)
        eh.register_component("b", ComponentCriticality.MEDIUM)
        eh.trigger_safe_mode("test")
        assert len(eh.get_all_preserved_states()) == 2

    def test_event_history(self) -> None:
        eh = EmergencyHandler()
        eh.trigger_safe_mode("first", "admin")
        eh.trigger_resource_lockdown("second", "admin")
        eh.recover("admin")
        assert len(eh.get_event_history()) == 3

    def test_health(self) -> None:
        eh = EmergencyHandler()
        h = eh.health()
        assert h["mode"] == "normal"
        assert h["in_emergency"] is False

    def test_health_after_shutdown(self) -> None:
        eh = EmergencyHandler()
        eh.register_component("a", ComponentCriticality.MEDIUM)
        eh.trigger_emergency_shutdown("test")
        h = eh.health()
        assert h["mode"] == "emergency_shutdown"
        assert h["states_preserved"] == 1

    def test_event_publishing(self) -> None:
        bus = EventBus()
        eh = EmergencyHandler(event_bus=bus)
        events: list[str] = []
        bus.subscribe_wildcard("ec.*", lambda ev, **kw: events.append(ev))
        eh.register_component("a", ComponentCriticality.MEDIUM)
        eh.trigger_safe_mode("test", "admin")
        assert "ec.safe_mode" in events
        eh.recover("admin")
        assert "ec.recovered" in events

    def test_thread_safety(self) -> None:
        eh = EmergencyHandler()
        errors: list[Exception] = []

        def worker() -> None:
            for i in range(50):
                try:
                    cid = f"comp-{i % 5}"
                    eh.register_component(cid, ComponentCriticality.MEDIUM)
                    eh.get_criticality(cid)
                    eh.health()
                except Exception as e:
                    errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(errors) == 0
