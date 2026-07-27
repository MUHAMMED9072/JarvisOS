from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ConnectionStatus(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    DISCONNECTING = "disconnecting"


class AuthState(str, Enum):
    NONE = "none"
    PENDING = "pending"
    AUTHENTICATED = "authenticated"
    FAILED = "failed"
    EXPIRED = "expired"


@dataclass
class ServerInfo:
    app_name: str = ""
    version: str = ""
    python_version: str = ""
    platform: str = ""


@dataclass
class HealthCheck:
    status: str = "healthy"
    previous_status: str = ""
    checks: dict[str, Any] = field(default_factory=dict)
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    timestamp: float = 0.0


@dataclass
class MetricsSnapshot:
    active_connections: int = 0
    authenticated_connections: int = 0
    anonymous_connections: int = 0
    total_connections: int = 0
    total_disconnections: int = 0
    total_reconnects: int = 0
    total_auth_success: int = 0
    total_auth_failures: int = 0
    bytes_sent: int = 0
    bytes_received: int = 0
    messages_sent: int = 0
    messages_received: int = 0
    retries: int = 0
    acknowledgements: int = 0
    failed_deliveries: int = 0
    average_latency_ms: float = 0.0
    heartbeat_failures: int = 0
    queue_overflows: int = 0
    compression_ratio_percent: float = 0.0
    command_executions: int = 0
    ai_streams: int = 0
    file_transfers: int = 0
    timestamp: float = 0.0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MetricsSnapshot:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class DiagnosticsReport:
    manager: dict[str, Any] = field(default_factory=dict)
    sessions: dict[str, Any] = field(default_factory=dict)
    retry_queues: dict[str, Any] = field(default_factory=dict)
    offline_queues: dict[str, Any] = field(default_factory=dict)
    heartbeat: dict[str, Any] = field(default_factory=dict)
    rooms: dict[str, Any] = field(default_factory=dict)
    subscriptions: dict[str, Any] = field(default_factory=dict)
    active_streams: dict[str, Any] = field(default_factory=dict)
    commands: list[Any] = field(default_factory=list)
    transfers: list[Any] = field(default_factory=list)
    auth_stats: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)
    runtime_config: dict[str, Any] = field(default_factory=dict)
    timestamp: float = 0.0


@dataclass
class PluginInfo:
    name: str = ""
    version: str = ""
    description: str = ""
    author: str = ""
    enabled: bool = False


@dataclass
class SkillInfo:
    name: str = ""
    intent: str = ""
    version: str = ""
    description: str = ""
    author: str = ""


@dataclass
class MemoryEntry:
    role: str = ""
    content: str = ""
    timestamp: float = 0.0


@dataclass
class VoiceStatus:
    running: bool = False


@dataclass
class SystemStatus:
    connected_clients: int = 0
    plugins: int = 0
    skills: int = 0
    memory_entries: int = 0
    voice_running: bool = False
    active_conversations: int = 0
    monitor_running: bool = False


@dataclass
class WSMessage:
    type: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    sender: str | None = None
    room: str | None = None
    event: str | None = None
    timestamp: str = ""
    message_id: str | None = None


@dataclass
class SessionInfo:
    session_id: str = ""
    client_id: str = ""
    is_authenticated: bool = False
    auth_method: str = "anonymous"
    roles: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
