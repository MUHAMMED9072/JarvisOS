from __future__ import annotations

import time

import pytest

from app.agents.health import AgentHealthMonitor, HealthRecord, HealthStatus


class TestHealthRecord:
    def test_to_dict(self):
        r = HealthRecord(agent_id="a1", status=HealthStatus.HEALTHY)
        d = r.to_dict()
        assert d["agent_id"] == "a1"
        assert d["status"] == "healthy"


class TestAgentHealthMonitor:
    @pytest.fixture
    def monitor(self):
        return AgentHealthMonitor()

    def test_register(self, monitor):
        record = monitor.register("agent-1")
        assert record.agent_id == "agent-1"
        assert record.status == HealthStatus.UNKNOWN

    def test_unregister(self, monitor):
        monitor.register("agent-1")
        assert monitor.unregister("agent-1") is True
        assert monitor.unregister("agent-1") is False

    def test_heartbeat(self, monitor):
        monitor.register("agent-1")
        record = monitor.heartbeat("agent-1")
        assert record is not None
        assert record.last_heartbeat > 0
        assert record.status == HealthStatus.HEALTHY

    def test_heartbeat_nonexistent(self, monitor):
        assert monitor.heartbeat("nobody") is None

    def test_liveness_probe_alive(self, monitor):
        monitor.register("agent-1", liveness_timeout=60)
        monitor.heartbeat("agent-1")
        assert monitor.liveness_probe("agent-1") is True

    def test_liveness_probe_dead(self, monitor):
        monitor.register("agent-1", liveness_timeout=0.01)
        time.sleep(0.02)
        assert monitor.liveness_probe("agent-1") is False
        record = monitor.get_health("agent-1")
        assert record is not None
        assert record.status == HealthStatus.UNHEALTHY

    def test_readiness_probe(self, monitor):
        monitor.register("agent-1")
        monitor.heartbeat("agent-1")
        assert monitor.readiness_probe("agent-1") is True

    def test_readiness_probe_not_ready(self, monitor):
        monitor.register("agent-1")
        monitor.set_ready("agent-1", False)
        assert monitor.readiness_probe("agent-1") is False

    def test_readiness_probe_nonexistent(self, monitor):
        assert monitor.readiness_probe("nobody") is False

    def test_set_ready(self, monitor):
        monitor.register("agent-1")
        monitor.set_ready("agent-1", False)
        record = monitor.get_health("agent-1")
        assert record is not None
        assert record.ready is False

    def test_attempt_recovery(self, monitor):
        monitor.register("agent-1", max_recovery_attempts=3)
        monitor.liveness_probe("agent-1")  # marks unhealthy if no heartbeat
        assert monitor.attempt_recovery("agent-1") is True
        record = monitor.get_health("agent-1")
        assert record is not None
        assert record.recovery_attempts == 1
        assert record.status == HealthStatus.DEGRADED

    def test_attempt_recovery_max_exceeded(self, monitor):
        monitor.register("agent-1", max_recovery_attempts=2)
        monitor.liveness_probe("agent-1")
        monitor.attempt_recovery("agent-1")
        monitor.attempt_recovery("agent-1")
        result = monitor.attempt_recovery("agent-1")
        assert result is False
        record = monitor.get_health("agent-1")
        assert record is not None
        assert record.status == HealthStatus.UNHEALTHY

    def test_attempt_recovery_nonexistent(self, monitor):
        assert monitor.attempt_recovery("nobody") is False

    def test_get_health(self, monitor):
        monitor.register("agent-1")
        record = monitor.get_health("agent-1")
        assert record is not None
        assert record.agent_id == "agent-1"

    def test_get_health_nonexistent(self, monitor):
        assert monitor.get_health("nobody") is None

    def test_list_unhealthy(self, monitor):
        monitor.register("agent-1")
        monitor.register("agent-2", liveness_timeout=0.01)
        time.sleep(0.02)
        monitor.liveness_probe("agent-2")
        unhealthy = monitor.list_unhealthy()
        assert len(unhealthy) >= 1
        assert unhealthy[0].agent_id == "agent-2"

    def test_health_diagnostic(self, monitor):
        monitor.register("agent-1")
        h = monitor.health()
        assert h["alive"] is True
        assert h["monitored_agents"] == 1

    def test_escalation_callback(self, monitor):
        escalated = []
        def on_esc(agent_id: str, reason: str):
            escalated.append((agent_id, reason))
        m = AgentHealthMonitor(on_escalate=on_esc)
        m.register("agent-1", max_recovery_attempts=1)
        m.liveness_probe("agent-1")
        m.attempt_recovery("agent-1")
        m.attempt_recovery("agent-1")  # should trigger escalation
        assert len(escalated) >= 1
        assert escalated[0][0] == "agent-1"

    def test_heartbeat_transitions(self, monitor):
        monitor.register("agent-1")
        # starts UNKNOWN
        record = monitor.get_health("agent-1")
        assert record.status == HealthStatus.UNKNOWN
        # heartbeat -> HEALTHY
        monitor.heartbeat("agent-1")
        assert monitor.get_health("agent-1").status == HealthStatus.HEALTHY
        # liveness failure -> UNHEALTHY
        m2 = AgentHealthMonitor()
        m2.register("agent-2", liveness_timeout=0.01)
        time.sleep(0.02)
        m2.liveness_probe("agent-2")
        assert m2.get_health("agent-2").status == HealthStatus.UNHEALTHY
        # heartbeat after unhealthy -> DEGRADED
        m2.heartbeat("agent-2")
        assert m2.get_health("agent-2").status == HealthStatus.DEGRADED
