from __future__ import annotations

import threading
from typing import Any

from app.client.events import EventDispatcher
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


class ClientState:
    """Centralized client state with change event publishing.

    Every state mutation publishes a corresponding change event
    via the internal ``EventDispatcher`` so that UI or other
    consumers can react to changes.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.events = EventDispatcher()

        self._connection_status: ConnectionStatus = ConnectionStatus.DISCONNECTED
        self._auth_state: AuthState = AuthState.NONE
        self._session_id: str | None = None
        self._client_id: str | None = None
        self._server_info: ServerInfo = ServerInfo()
        self._health: HealthCheck = HealthCheck()
        self._metrics: MetricsSnapshot = MetricsSnapshot()
        self._diagnostics: DiagnosticsReport = DiagnosticsReport()
        self._plugins: list[PluginInfo] = []
        self._skills: list[SkillInfo] = []
        self._memory_count: int = 0
        self._voice: VoiceStatus = VoiceStatus()
        self._reconnect_count: int = 0
        self._latency_ms: float = 0.0
        self._uptime_seconds: float = 0.0

    # ------------------------------------------------------------------
    # Properties with change events
    # ------------------------------------------------------------------

    @property
    def connection_status(self) -> ConnectionStatus:
        return self._connection_status

    @connection_status.setter
    def connection_status(self, value: ConnectionStatus) -> None:
        with self._lock:
            old = self._connection_status
            self._connection_status = value
        if old != value:
            self.events.publish("state.connection_status", old=old, new=value)

    @property
    def auth_state(self) -> AuthState:
        return self._auth_state

    @auth_state.setter
    def auth_state(self, value: AuthState) -> None:
        with self._lock:
            old = self._auth_state
            self._auth_state = value
        if old != value:
            self.events.publish("state.auth_state", old=old, new=value)

    @property
    def session_id(self) -> str | None:
        return self._session_id

    @session_id.setter
    def session_id(self, value: str | None) -> None:
        with self._lock:
            self._session_id = value
        self.events.publish("state.session_id", value=value)

    @property
    def client_id(self) -> str | None:
        return self._client_id

    @client_id.setter
    def client_id(self, value: str | None) -> None:
        with self._lock:
            self._client_id = value
        self.events.publish("state.client_id", value=value)

    @property
    def server_info(self) -> ServerInfo:
        return self._server_info

    @server_info.setter
    def server_info(self, value: ServerInfo) -> None:
        with self._lock:
            self._server_info = value
        self.events.publish("state.server_info", value=value)

    @property
    def health(self) -> HealthCheck:
        return self._health

    @health.setter
    def health(self, value: HealthCheck) -> None:
        with self._lock:
            self._health = value
        self.events.publish("state.health", value=value)

    @property
    def metrics(self) -> MetricsSnapshot:
        return self._metrics

    @metrics.setter
    def metrics(self, value: MetricsSnapshot) -> None:
        with self._lock:
            self._metrics = value
        self.events.publish("state.metrics", value=value)

    @property
    def diagnostics(self) -> DiagnosticsReport:
        return self._diagnostics

    @diagnostics.setter
    def diagnostics(self, value: DiagnosticsReport) -> None:
        with self._lock:
            self._diagnostics = value
        self.events.publish("state.diagnostics", value=value)

    @property
    def plugins(self) -> list[PluginInfo]:
        return self._plugins

    @plugins.setter
    def plugins(self, value: list[PluginInfo]) -> None:
        with self._lock:
            self._plugins = value
        self.events.publish("state.plugins", value=value)

    @property
    def skills(self) -> list[SkillInfo]:
        return self._skills

    @skills.setter
    def skills(self, value: list[SkillInfo]) -> None:
        with self._lock:
            self._skills = value
        self.events.publish("state.skills", value=value)

    @property
    def memory_count(self) -> int:
        return self._memory_count

    @memory_count.setter
    def memory_count(self, value: int) -> None:
        with self._lock:
            self._memory_count = value
        self.events.publish("state.memory_count", value=value)

    @property
    def voice(self) -> VoiceStatus:
        return self._voice

    @voice.setter
    def voice(self, value: VoiceStatus) -> None:
        with self._lock:
            self._voice = value
        self.events.publish("state.voice", value=value)

    @property
    def reconnect_count(self) -> int:
        return self._reconnect_count

    @reconnect_count.setter
    def reconnect_count(self, value: int) -> None:
        with self._lock:
            self._reconnect_count = value
        self.events.publish("state.reconnect_count", value=value)

    @property
    def latency_ms(self) -> float:
        return self._latency_ms

    @latency_ms.setter
    def latency_ms(self, value: float) -> None:
        with self._lock:
            self._latency_ms = value
        self.events.publish("state.latency_ms", value=value)

    @property
    def uptime_seconds(self) -> float:
        return self._uptime_seconds

    @uptime_seconds.setter
    def uptime_seconds(self, value: float) -> None:
        with self._lock:
            self._uptime_seconds = value
        self.events.publish("state.uptime_seconds", value=value)

    # ------------------------------------------------------------------
    # Bulk update helpers
    # ------------------------------------------------------------------

    def update_connection(self, status: ConnectionStatus, **extra: Any) -> None:
        self.connection_status = status
        for key, val in extra.items():
            if hasattr(self, key):
                setattr(self, f"_{key}", val)

    def reset(self) -> None:
        """Reset all state to defaults."""
        self._connection_status = ConnectionStatus.DISCONNECTED
        self._auth_state = AuthState.NONE
        self._session_id = None
        self._client_id = None
        self._server_info = ServerInfo()
        self._health = HealthCheck()
        self._metrics = MetricsSnapshot()
        self._diagnostics = DiagnosticsReport()
        self._plugins = []
        self._skills = []
        self._memory_count = 0
        self._voice = VoiceStatus()
        self._reconnect_count = 0
        self._latency_ms = 0.0
        self._uptime_seconds = 0.0
        self.events.publish("state.reset")

    # ------------------------------------------------------------------
    # Snapshot
    # ------------------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        """Return a plain-dict snapshot of all state."""
        return {
            "connection_status": self._connection_status.value,
            "auth_state": self._auth_state.value,
            "session_id": self._session_id,
            "client_id": self._client_id,
            "reconnect_count": self._reconnect_count,
            "latency_ms": self._latency_ms,
            "uptime_seconds": self._uptime_seconds,
        }
