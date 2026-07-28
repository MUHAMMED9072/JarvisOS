from __future__ import annotations

import time
from threading import Event

import pytest

from app.kernel.health.heartbeat import Heartbeat, HeartbeatRegistry, HeartbeatStatus
from app.kernel.health.monitor import (
    ComponentHealth,
    HealthEvent,
    HealthMonitor,
    HealthState,
    ResourceUsage,
)
from app.kernel.health.probe import (
    LivenessProbe,
    ProbeRegistry,
    ProbeResult,
    ReadinessProbe,
)


# =========================================================================
# Heartbeat Tests
# =========================================================================


class TestHeartbeat:
    def test_default_status_is_alive(self):
        hb = Heartbeat(component_id="test")
        assert hb.status == HeartbeatStatus.ALIVE

    def test_is_stale_returns_false_for_recent(self):
        hb = Heartbeat(component_id="test")
        assert not hb.is_stale(timeout=30.0)

    def test_is_stale_returns_true_for_old(self):
        hb = Heartbeat(component_id="test", timestamp=time.time() - 100)
        assert hb.is_stale(timeout=30.0)

    def test_is_stale_boundary(self):
        hb = Heartbeat(component_id="test", timestamp=time.time() - 29.9)
        assert not hb.is_stale(timeout=30.0)

    def test_custom_status_and_message(self):
        hb = Heartbeat(component_id="test", status=HeartbeatStatus.DEGRADED, message="high load")
        assert hb.status == HeartbeatStatus.DEGRADED
        assert hb.message == "high load"


class TestHeartbeatRegistry:
    def test_register_adds_component(self):
        reg = HeartbeatRegistry()
        reg.register("comp-1")
        assert reg.count() == 1

    def test_register_idempotent(self):
        reg = HeartbeatRegistry()
        reg.register("comp-1")
        reg.register("comp-1")
        assert reg.count() == 1

    def test_unregister_removes_component(self):
        reg = HeartbeatRegistry()
        reg.register("comp-1")
        assert reg.unregister("comp-1") is True
        assert reg.count() == 0

    def test_unregister_missing(self):
        reg = HeartbeatRegistry()
        assert reg.unregister("nonexistent") is False

    def test_beat_updates_heartbeat(self):
        reg = HeartbeatRegistry()
        reg.register("comp-1")
        hb = reg.beat("comp-1", status=HeartbeatStatus.ALIVE, message="ok")
        assert hb.component_id == "comp-1"
        assert hb.status == HeartbeatStatus.ALIVE
        assert hb.message == "ok"

    def test_beat_auto_registers(self):
        reg = HeartbeatRegistry()
        hb = reg.beat("comp-1")
        assert reg.get("comp-1") is not None

    def test_get_returns_heartbeat(self):
        reg = HeartbeatRegistry()
        reg.beat("comp-1", message="hello")
        hb = reg.get("comp-1")
        assert hb is not None
        assert hb.message == "hello"

    def test_get_missing_returns_none(self):
        reg = HeartbeatRegistry()
        assert reg.get("nonexistent") is None

    def test_is_alive_returns_true(self):
        reg = HeartbeatRegistry(default_timeout=30.0)
        reg.register("comp-1")
        reg.beat("comp-1")
        assert reg.is_alive("comp-1") is True

    def test_is_alive_stale(self):
        reg = HeartbeatRegistry(default_timeout=0.1)
        reg.register("comp-1")
        hb = Heartbeat(component_id="comp-1", timestamp=time.time() - 10)
        reg._heartbeats["comp-1"] = hb
        assert reg.is_alive("comp-1") is False

    def test_is_alive_missing(self):
        reg = HeartbeatRegistry()
        assert reg.is_alive("nonexistent") is False

    def test_get_stale_returns_stale_heartbeats(self):
        reg = HeartbeatRegistry(default_timeout=0.1)
        reg.register("fresh")
        reg.register("stale-comp")
        reg._heartbeats["stale-comp"] = Heartbeat(
            component_id="stale-comp", timestamp=time.time() - 10
        )
        stale = reg.get_stale()
        assert len(stale) == 1
        assert stale[0].component_id == "stale-comp"

    def test_get_all(self):
        reg = HeartbeatRegistry()
        reg.register("a")
        reg.register("b")
        assert len(reg.get_all()) == 2

    def test_clear(self):
        reg = HeartbeatRegistry()
        reg.register("a")
        reg.register("b")
        reg.clear()
        assert reg.count() == 0

    def test_default_timeout_property(self):
        reg = HeartbeatRegistry(default_timeout=60.0)
        assert reg.default_timeout == 60.0


# =========================================================================
# Probe Tests
# =========================================================================


class TestProbeResult:
    def test_default_alive_is_true(self):
        r = ProbeResult()
        assert r.alive is True

    def test_default_ready_is_true(self):
        r = ProbeResult()
        assert r.ready is True

    def test_default_error_is_none(self):
        r = ProbeResult()
        assert r.error is None

    def test_default_metrics_is_empty(self):
        r = ProbeResult()
        assert r.metrics == {}


class _CheckableComponent:
    def __init__(self, alive=True, ready=True):
        self._alive = alive
        self._ready = ready

    def check_liveness(self) -> ProbeResult:
        return ProbeResult(alive=self._alive)

    def check_readiness(self) -> ProbeResult:
        return ProbeResult(alive=self._alive, ready=self._ready)


class TestLivenessProbe:
    def test_probe_no_target_returns_alive(self):
        probe = LivenessProbe()
        result = probe.probe()
        assert result.alive is True

    def test_probe_with_checkable(self):
        component = _CheckableComponent(alive=True)
        probe = LivenessProbe()
        result = probe.probe(component)
        assert result.alive is True

    def test_probe_dead_component(self):
        component = _CheckableComponent(alive=False)
        probe = LivenessProbe()
        result = probe.probe(component)
        assert result.alive is False

    def test_probe_with_callable(self):
        probe = LivenessProbe(check_callable=lambda: ProbeResult(alive=True))
        result = probe.probe()
        assert result.alive is True

    def test_probe_callable_returns_false(self):
        probe = LivenessProbe(check_callable=lambda: ProbeResult(alive=False))
        result = probe.probe()
        assert result.alive is False

    def test_probe_handles_exception(self):
        def _fail():
            raise RuntimeError("boom")
        probe = LivenessProbe(check_callable=_fail)
        result = probe.probe()
        assert result.alive is False
        assert "boom" in (result.error or "")

    def test_probe_records_latency(self):
        def _slow():
            time.sleep(0.01)
            return ProbeResult(alive=True)
        probe = LivenessProbe(check_callable=_slow)
        result = probe.probe()
        assert result.latency_ms >= 5.0


class TestReadinessProbe:
    def test_probe_no_target_returns_ready(self):
        probe = ReadinessProbe()
        result = probe.probe()
        assert result.ready is True

    def test_probe_with_checkable(self):
        component = _CheckableComponent(ready=True)
        probe = ReadinessProbe()
        result = probe.probe(component)
        assert result.ready is True

    def test_probe_not_ready(self):
        component = _CheckableComponent(ready=False)
        probe = ReadinessProbe()
        result = probe.probe(component)
        assert result.ready is False

    def test_probe_with_callable(self):
        probe = ReadinessProbe(check_callable=lambda: ProbeResult(alive=True, ready=True))
        result = probe.probe()
        assert result.ready is True

    def test_probe_handles_exception(self):
        def _fail():
            raise RuntimeError("not ready")
        probe = ReadinessProbe(check_callable=_fail)
        result = probe.probe()
        assert result.ready is False
        assert "not ready" in (result.error or "")


class TestProbeRegistry:
    def test_register_liveness_probe(self):
        reg = ProbeRegistry()
        probe = LivenessProbe()
        reg.register("comp-1", liveness_probe=probe)
        result = reg.probe_liveness("comp-1")
        assert result.alive is True

    def test_register_readiness_probe(self):
        reg = ProbeRegistry()
        probe = ReadinessProbe()
        reg.register("comp-1", readiness_probe=probe)
        result = reg.probe_readiness("comp-1")
        assert result.ready is True

    def test_probe_liveness_no_probe_returns_alive(self):
        reg = ProbeRegistry()
        result = reg.probe_liveness("nonexistent")
        assert result.alive is True

    def test_probe_readiness_no_probe_returns_ready(self):
        reg = ProbeRegistry()
        result = reg.probe_readiness("nonexistent")
        assert result.ready is True

    def test_unregister(self):
        reg = ProbeRegistry()
        reg.register("comp-1", liveness_probe=LivenessProbe())
        assert reg.unregister("comp-1") is True
        assert reg.probe_liveness("comp-1").alive is True  # defaults to alive

    def test_unregister_missing(self):
        reg = ProbeRegistry()
        assert reg.unregister("nonexistent") is False

    def test_get_component_ids(self):
        reg = ProbeRegistry()
        reg.register("a", liveness_probe=LivenessProbe())
        reg.register("b", readiness_probe=ReadinessProbe())
        ids = reg.get_component_ids()
        assert "a" in ids
        assert "b" in ids

    def test_clear(self):
        reg = ProbeRegistry()
        reg.register("a", liveness_probe=LivenessProbe())
        reg.register("b", readiness_probe=ReadinessProbe())
        reg.clear()
        assert reg.get_component_ids() == []


# =========================================================================
# HealthMonitor Tests
# =========================================================================


class TestResourceUsage:
    def test_default_values(self):
        ru = ResourceUsage()
        assert ru.cpu_percent == 0.0
        assert ru.memory_percent == 0.0
        assert ru.memory_rss == 0

    def test_to_dict(self):
        ru = ResourceUsage(cpu_percent=10.5, memory_percent=50.0, memory_rss=1024)
        d = ru.to_dict()
        assert d["cpu_percent"] == 10.5
        assert d["memory_percent"] == 50.0
        assert d["memory_rss_bytes"] == 1024
        assert "timestamp" in d


class TestComponentHealth:
    def test_default_state_is_healthy(self):
        ch = ComponentHealth(component_id="test")
        assert ch.state == HealthState.HEALTHY

    def test_default_alive_is_true(self):
        ch = ComponentHealth(component_id="test")
        assert ch.alive is True

    def test_consecutive_failures_defaults_to_zero(self):
        ch = ComponentHealth(component_id="test")
        assert ch.consecutive_failures == 0

    def test_to_dict_contains_expected_keys(self):
        ch = ComponentHealth(component_id="test")
        d = ch.to_dict()
        assert d["component_id"] == "test"
        assert d["state"] == "healthy"
        assert "last_state_change" in d


class TestHealthEvent:
    def test_to_dict(self):
        event = HealthEvent(
            component_id="test",
            previous_state=HealthState.HEALTHY,
            new_state=HealthState.DOWN,
            message="crashed",
        )
        d = event.to_dict()
        assert d["component_id"] == "test"
        assert d["previous_state"] == "healthy"
        assert d["new_state"] == "down"
        assert d["message"] == "crashed"


class TestHealthMonitor:
    def test_default_properties(self):
        hm = HealthMonitor()
        assert hm.check_interval == 30.0
        assert hm.failure_threshold == 2
        assert hm.running is False
        assert hm.uptime == 0.0

    def test_start_and_stop(self):
        hm = HealthMonitor()
        hm.start()
        assert hm.running is True
        assert hm.uptime > 0.0
        hm.stop()
        assert hm.running is False

    def test_register_component(self):
        hm = HealthMonitor()
        hm.register_component("comp-1")
        health = hm.get_component_health("comp-1")
        assert health is not None
        assert health.component_id == "comp-1"

    def test_register_component_duplicate(self):
        hm = HealthMonitor()
        hm.register_component("comp-1")
        hm.register_component("comp-1")
        assert len(hm.get_all_component_health()) == 1

    def test_unregister_component(self):
        hm = HealthMonitor()
        hm.register_component("comp-1")
        assert hm.unregister_component("comp-1") is True
        assert hm.get_component_health("comp-1") is None

    def test_unregister_missing(self):
        hm = HealthMonitor()
        assert hm.unregister_component("nonexistent") is False

    def test_record_heartbeat(self):
        hm = HealthMonitor()
        hm.register_component("comp-1")
        hm.record_heartbeat("comp-1", message="alive")
        hb = hm.heartbeat_registry.get("comp-1")
        assert hb is not None
        assert hb.message == "alive"

    def test_check_once_returns_health_for_all(self):
        hm = HealthMonitor()
        hm.register_component("comp-1")
        hm.register_component("comp-2")
        results = hm.check_once()
        assert len(results) == 2

    def test_check_once_updates_state(self):
        hm = HealthMonitor()
        hm.register_component("comp-1")
        hm.check_once()
        health = hm.get_component_health("comp-1")
        assert health is not None
        assert health.state == HealthState.HEALTHY

    def test_failure_threshold_triggers_degraded(self):
        hm = HealthMonitor(failure_threshold=2)
        hm.register_component("comp-1")
        fail_count = [0]

        def failing_probe():
            fail_count[0] += 1
            return ProbeResult(alive=False, ready=False, error="fail")
        hm.register_custom_check("comp-1", failing_probe)
        hm.check_once()
        health = hm.get_component_health("comp-1")
        assert health.consecutive_failures == 1
        assert health.state == HealthState.DEGRADED

    def test_failure_threshold_triggers_down(self):
        hm = HealthMonitor(failure_threshold=2)
        hm.register_component("comp-1")

        def failing_probe():
            return ProbeResult(alive=False, ready=False, error="fail")
        hm.register_custom_check("comp-1", failing_probe)
        hm.check_once()
        hm.check_once()
        health = hm.get_component_health("comp-1")
        assert health.consecutive_failures == 2
        assert health.state == HealthState.DOWN

    def test_recovery_resets_consecutive_failures(self):
        hm = HealthMonitor(failure_threshold=2)
        hm.register_component("comp-1")

        def failing_probe():
            return ProbeResult(alive=False, ready=False, error="fail")
        hm.register_custom_check("comp-1", failing_probe)
        hm.check_once()
        hm.check_once()
        health = hm.get_component_health("comp-1")
        assert health.state == HealthState.DOWN

        # Now recover - replace with passing check
        def passing_probe():
            return ProbeResult(alive=True, ready=True)
        hm.register_custom_check("comp-1", passing_probe)
        hm.check_once()
        health = hm.get_component_health("comp-1")
        assert health.consecutive_failures == 0
        assert health.state == HealthState.HEALTHY

    def test_health_self_probe(self):
        hm = HealthMonitor()
        hm.register_component("comp-1")
        hm.register_component("comp-2")
        hm.check_once()
        health = hm.health()
        assert health["alive"] is False
        assert health["components"]["total"] == 2
        assert "resource_usage" in health

    def test_event_publishing_on_state_change(self):
        events: list[str] = []
        from app.core.event_bus import EventBus

        bus = EventBus()

        def collector(event, **kw):
            events.append(event)
        bus.subscribe_wildcard("health.*", collector)
        hm = HealthMonitor(event_bus=bus, failure_threshold=1)
        hm.register_component("comp-1")

        def failing_probe():
            return ProbeResult(alive=False, ready=False, error="fail")
        hm.register_custom_check("comp-1", failing_probe)
        hm.check_once()
        assert any("health.component.state_changed" in e for e in events)

    def test_register_custom_check(self):
        hm = HealthMonitor()
        hm.register_custom_check("custom", lambda: ProbeResult(alive=True, ready=True))

    def test_get_all_component_health_empty(self):
        hm = HealthMonitor()
        assert hm.get_all_component_health() == []

    def test_get_all_component_health(self):
        hm = HealthMonitor()
        hm.register_component("a")
        hm.register_component("b")
        assert len(hm.get_all_component_health()) == 2

    def test_get_component_health_missing(self):
        hm = HealthMonitor()
        assert hm.get_component_health("nonexistent") is None

    def test_health_self_probe_when_not_running(self):
        hm = HealthMonitor()
        health = hm.health()
        assert health["alive"] is False

    def test_monitor_loop_runs_checks(self):
        hm = HealthMonitor(check_interval=0.05)
        hm.register_component("comp-1")
        hm.start()
        time.sleep(0.12)
        hm.stop()
        assert hm.check_count >= 1

    def test_double_start_is_idempotent(self):
        hm = HealthMonitor()
        hm.start()
        hm.start()
        assert hm.running is True
        hm.stop()

    def test_double_stop_is_safe(self):
        hm = HealthMonitor()
        hm.start()
        hm.stop()
        hm.stop()

    def test_probe_registry_exposed(self):
        hm = HealthMonitor()
        assert hm.probe_registry is not None

    def test_heartbeat_registry_exposed(self):
        hm = HealthMonitor()
        assert hm.heartbeat_registry is not None

    def test_event_bus_property(self):
        from app.core.event_bus import EventBus
        bus = EventBus()
        hm = HealthMonitor(event_bus=bus)
        assert hm.event_bus is bus

    def test_event_bus_none_by_default(self):
        hm = HealthMonitor()
        assert hm.event_bus is None

    def test_start_publishes_monitor_started(self):
        events = []
        from app.core.event_bus import EventBus
        bus = EventBus()
        bus.subscribe("health.monitor.started", lambda: events.append("started"))
        hm = HealthMonitor(event_bus=bus)
        hm.start()
        assert "started" in events
        hm.stop()

    def test_stop_publishes_monitor_stopped(self):
        events = []
        from app.core.event_bus import EventBus
        bus = EventBus()
        bus.subscribe("health.monitor.stopped", lambda: events.append("stopped"))
        hm = HealthMonitor(event_bus=bus)
        hm.start()
        hm.stop()
        assert "stopped" in events
