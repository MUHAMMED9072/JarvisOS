"""Tests for client state management."""

from __future__ import annotations

import pytest

from app.client.models import (
    AuthState,
    ConnectionStatus,
    DiagnosticsReport,
    HealthCheck,
    MetricsSnapshot,
    PluginInfo,
    ServerInfo,
    SkillInfo,
    VoiceStatus,
)
from app.client.state import ClientState


class TestClientStateDefaults:
    def test_initial_state(self):
        s = ClientState()
        assert s.connection_status == ConnectionStatus.DISCONNECTED
        assert s.auth_state == AuthState.NONE
        assert s.session_id is None
        assert s.client_id is None
        assert isinstance(s.server_info, ServerInfo)
        assert isinstance(s.health, HealthCheck)
        assert isinstance(s.metrics, MetricsSnapshot)
        assert isinstance(s.diagnostics, DiagnosticsReport)
        assert s.plugins == []
        assert s.skills == []
        assert s.memory_count == 0
        assert isinstance(s.voice, VoiceStatus)
        assert s.reconnect_count == 0
        assert s.latency_ms == 0.0
        assert s.uptime_seconds == 0.0

    def test_events_dispatcher_exists(self):
        s = ClientState()
        assert hasattr(s, "events")
        assert s.events.listener_count == 0


class TestClientStateChanges:
    def test_connection_status_change(self):
        s = ClientState()
        events = []
        s.events.subscribe("state.connection_status", lambda e, **kw: events.append(kw))
        s.connection_status = ConnectionStatus.CONNECTED
        assert len(events) == 1
        assert events[0]["new"] == ConnectionStatus.CONNECTED

    def test_connection_status_no_duplicate(self):
        s = ClientState()
        events = []
        s.events.subscribe("state.connection_status", lambda e, **kw: events.append(kw))
        s.connection_status = ConnectionStatus.DISCONNECTED
        assert len(events) == 0  # Already disconnected

    def test_auth_state_change(self):
        s = ClientState()
        events = []
        s.events.subscribe("state.auth_state", lambda e, **kw: events.append(kw))
        s.auth_state = AuthState.AUTHENTICATED
        assert len(events) == 1

    def test_session_id_change(self):
        s = ClientState()
        events = []
        s.events.subscribe("state.session_id", lambda e, **kw: events.append(kw))
        s.session_id = "sess-1"
        assert s.session_id == "sess-1"

    def test_client_id_change(self):
        s = ClientState()
        s.client_id = "client-1"
        assert s.client_id == "client-1"

    def test_server_info_change(self):
        s = ClientState()
        info = ServerInfo(app_name="JARVIS", version="1.0")
        s.server_info = info
        assert s.server_info.app_name == "JARVIS"

    def test_health_change(self):
        s = ClientState()
        hc = HealthCheck(status="degraded")
        s.health = hc
        assert s.health.status == "degraded"

    def test_metrics_change(self):
        s = ClientState()
        m = MetricsSnapshot(active_connections=5)
        s.metrics = m
        assert s.metrics.active_connections == 5

    def test_diagnostics_change(self):
        s = ClientState()
        d = DiagnosticsReport()
        d.manager = {"active_connections": 3}
        s.diagnostics = d
        assert s.diagnostics.manager["active_connections"] == 3

    def test_plugins_change(self):
        s = ClientState()
        plugins = [PluginInfo(name="test", enabled=True)]
        s.plugins = plugins
        assert len(s.plugins) == 1
        assert s.plugins[0].name == "test"

    def test_skills_change(self):
        s = ClientState()
        skills = [SkillInfo(name="greet")]
        s.skills = skills
        assert len(s.skills) == 1

    def test_memory_count_change(self):
        s = ClientState()
        events = []
        s.events.subscribe("state.memory_count", lambda e, **kw: events.append(kw))
        s.memory_count = 42
        assert s.memory_count == 42
        assert len(events) == 1

    def test_voice_change(self):
        s = ClientState()
        v = VoiceStatus(running=True)
        s.voice = v
        assert s.voice.running is True

    def test_reconnect_count_change(self):
        s = ClientState()
        s.reconnect_count = 3
        assert s.reconnect_count == 3

    def test_latency_change(self):
        s = ClientState()
        s.latency_ms = 42.5
        assert s.latency_ms == 42.5

    def test_uptime_change(self):
        s = ClientState()
        s.uptime_seconds = 3600.0
        assert s.uptime_seconds == 3600.0


class TestClientStateReset:
    def test_reset_clears_all(self):
        s = ClientState()
        s.connection_status = ConnectionStatus.CONNECTED
        s.auth_state = AuthState.AUTHENTICATED
        s.session_id = "sess-1"
        s.client_id = "client-1"
        s.reconnect_count = 5
        s.latency_ms = 100.0
        s.reset()
        assert s.connection_status == ConnectionStatus.DISCONNECTED
        assert s.auth_state == AuthState.NONE
        assert s.session_id is None
        assert s.client_id is None
        assert s.reconnect_count == 0
        assert s.latency_ms == 0.0

    def test_reset_emits_event(self):
        s = ClientState()
        events = []
        s.events.subscribe("state.reset", lambda e, **kw: events.append(kw))
        s.reset()
        assert len(events) == 1


class TestClientStateSnapshot:
    def test_snapshot_returns_dict(self):
        s = ClientState()
        s.connection_status = ConnectionStatus.CONNECTED
        s.auth_state = AuthState.AUTHENTICATED
        s.client_id = "client-1"
        snap = s.snapshot()
        assert snap["connection_status"] == "connected"
        assert snap["auth_state"] == "authenticated"
        assert snap["client_id"] == "client-1"

    def test_snapshot_structure(self):
        s = ClientState()
        snap = s.snapshot()
        keys = {"connection_status", "auth_state", "session_id", "client_id",
                "reconnect_count", "latency_ms", "uptime_seconds"}
        assert set(snap.keys()) == keys


class TestClientStateUpdateConnection:
    def test_update_connection(self):
        s = ClientState()
        s.update_connection(ConnectionStatus.CONNECTED)
        assert s.connection_status == ConnectionStatus.CONNECTED


class TestClientStateThreadSafety:
    def test_concurrent_updates(self):
        import threading
        s = ClientState()
        errors = []

        def worker():
            try:
                for i in range(50):
                    s.connection_status = ConnectionStatus.CONNECTED if i % 2 == 0 else ConnectionStatus.DISCONNECTED
                    s.reconnect_count = i
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(errors) == 0
