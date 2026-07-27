"""Tests for client models."""

from __future__ import annotations

import pytest

from app.client.models import (
    AuthState,
    ConnectionStatus,
    DiagnosticsReport,
    HealthCheck,
    MemoryEntry,
    MetricsSnapshot,
    PluginInfo,
    ServerInfo,
    SessionInfo,
    SkillInfo,
    SystemStatus,
    VoiceStatus,
    WSMessage,
)


class TestEnums:
    def test_connection_status_values(self):
        assert ConnectionStatus.DISCONNECTED.value == "disconnected"
        assert ConnectionStatus.CONNECTED.value == "connected"
        assert ConnectionStatus.RECONNECTING.value == "reconnecting"

    def test_auth_state_values(self):
        assert AuthState.NONE.value == "none"
        assert AuthState.AUTHENTICATED.value == "authenticated"
        assert AuthState.FAILED.value == "failed"
        assert AuthState.EXPIRED.value == "expired"


class TestServerInfo:
    def test_defaults(self):
        info = ServerInfo()
        assert info.app_name == ""
        assert info.version == ""

    def test_fields(self):
        info = ServerInfo(app_name="JARVIS", version="1.0", python_version="3.14", platform="win32")
        assert info.app_name == "JARVIS"
        assert info.python_version == "3.14"


class TestHealthCheck:
    def test_defaults(self):
        hc = HealthCheck()
        assert hc.status == "healthy"
        assert hc.failures == []

    def test_fields(self):
        hc = HealthCheck(status="degraded", failures=["high_latency"], timestamp=100.0)
        assert hc.status == "degraded"
        assert "high_latency" in hc.failures


class TestMetricsSnapshot:
    def test_defaults(self):
        m = MetricsSnapshot()
        assert m.active_connections == 0
        assert m.bytes_sent == 0
        assert m.average_latency_ms == 0.0

    def test_from_dict(self):
        data = {
            "active_connections": 5,
            "bytes_sent": 1000,
            "average_latency_ms": 42.5,
            "unknown_field": "ignored",
        }
        m = MetricsSnapshot.from_dict(data)
        assert m.active_connections == 5
        assert m.bytes_sent == 1000
        assert m.average_latency_ms == 42.5
        assert not hasattr(m, "unknown_field")


class TestDiagnosticsReport:
    def test_defaults(self):
        r = DiagnosticsReport()
        assert r.manager == {}
        assert r.timestamp == 0.0

    def test_fields(self):
        r = DiagnosticsReport(
            manager={"active_connections": 3},
            rooms={"total_rooms": 2},
            timestamp=999.0,
        )
        assert r.manager["active_connections"] == 3
        assert r.rooms["total_rooms"] == 2
        assert r.timestamp == 999.0


class TestPluginInfo:
    def test_defaults(self):
        p = PluginInfo()
        assert p.name == ""
        assert p.enabled is False

    def test_fields(self):
        p = PluginInfo(name="test", version="1.0", enabled=True)
        assert p.name == "test"
        assert p.enabled is True


class TestSkillInfo:
    def test_fields(self):
        s = SkillInfo(name="greet", intent="hello", version="1.0")
        assert s.name == "greet"
        assert s.intent == "hello"


class TestMemoryEntry:
    def test_fields(self):
        e = MemoryEntry(role="user", content="hello", timestamp=100.0)
        assert e.role == "user"
        assert e.content == "hello"


class TestVoiceStatus:
    def test_defaults(self):
        v = VoiceStatus()
        assert v.running is False

    def test_running(self):
        v = VoiceStatus(running=True)
        assert v.running is True


class TestSystemStatus:
    def test_defaults(self):
        s = SystemStatus()
        assert s.connected_clients == 0
        assert s.voice_running is False

    def test_fields(self):
        s = SystemStatus(connected_clients=5, plugins=10, monitor_running=True)
        assert s.connected_clients == 5
        assert s.monitor_running is True


class TestWSMessage:
    def test_defaults(self):
        m = WSMessage()
        assert m.type == ""
        assert m.payload == {}
        assert m.message_id is None

    def test_fields(self):
        m = WSMessage(type="ping", payload={"ts": 1}, message_id="msg-1")
        assert m.type == "ping"
        assert m.payload["ts"] == 1
        assert m.message_id == "msg-1"

    def test_sender_and_room(self):
        m = WSMessage(type="message", sender="client1", room="lobby")
        assert m.sender == "client1"
        assert m.room == "lobby"


class TestSessionInfo:
    def test_defaults(self):
        s = SessionInfo()
        assert s.session_id == ""
        assert s.is_authenticated is False
        assert s.auth_method == "anonymous"

    def test_fields(self):
        s = SessionInfo(
            session_id="sess-1", client_id="client1",
            is_authenticated=True, auth_method="api_key",
            roles=["admin"], permissions=["admin.*"],
        )
        assert s.session_id == "sess-1"
        assert s.is_authenticated is True
        assert "admin" in s.roles
