from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ChatMessage:
    role: str = "user"
    content: str = ""
    timestamp: float = 0.0
    streaming: bool = False
    message_id: str = ""
    error: str = ""


@dataclass
class MetricSample:
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    memory_used_gb: float = 0.0
    memory_total_gb: float = 0.0
    disk_percent: float = 0.0
    network_sent_mbps: float = 0.0
    network_recv_mbps: float = 0.0
    timestamp: float = 0.0


@dataclass
class ServerStatus:
    connected: bool = False
    app_name: str = ""
    version: str = ""
    uptime: float = 0.0
    python_version: str = ""
    platform: str = ""
    connected_clients: int = 0
    skills_count: int = 0
    plugins_count: int = 0
    memory_entries: int = 0
    active_conversations: int = 0
    voice_running: bool = False
    monitor_running: bool = False


@dataclass
class SkillDescriptor:
    name: str = ""
    intent: str = ""
    description: str = ""
    version: str = ""
    author: str = ""


@dataclass
class PluginDescriptor:
    name: str = ""
    version: str = ""
    description: str = ""
    author: str = ""
    enabled: bool = False


@dataclass
class ConversationEntry:
    conversation_id: str = ""
    title: str = ""
    message_count: int = 0
    created: float = 0.0
    updated: float = 0.0


@dataclass
class SettingsGroup:
    name: str = ""
    settings: dict[str, Any] = field(default_factory=dict)


@dataclass
class HealthEvent:
    status: str = "healthy"
    message: str = ""
    timestamp: float = 0.0
