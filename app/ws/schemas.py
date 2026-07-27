from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class WSMessageType(str, Enum):
    """Message types exchanged over WebSocket connections."""

    # Client -> Server
    PING = "ping"
    SUBSCRIBE = "subscribe"
    UNSUBSCRIBE = "unsubscribe"
    JOIN = "join"
    LEAVE = "leave"
    MESSAGE = "message"
    AI_STREAM_START = "ai.stream.start"
    AI_STREAM_CANCEL = "ai.stream.cancel"

    # Server -> Client
    PONG = "pong"
    SUBSCRIBED = "subscribed"
    UNSUBSCRIBED = "unsubscribed"
    JOINED = "joined"
    LEFT = "left"
    EVENT = "event"
    ERROR = "error"
    AI_STREAM_CHUNK = "ai.stream.chunk"
    AI_STREAM_COMPLETE = "ai.stream.complete"
    AI_STREAM_CANCELLED = "ai.stream.cancelled"
    AI_STREAM_ERROR = "ai.stream.error"
    AI_STREAM_STARTED = "ai.stream.started"

    # Client -> Server: Remote Administration (P12-07)
    ADMIN_PING = "admin.ping"
    ADMIN_STATUS = "admin.status"
    ADMIN_INFO = "admin.info"
    ADMIN_SHUTDOWN = "admin.shutdown"
    ADMIN_RESTART = "admin.restart"
    ADMIN_CLIENTS = "admin.clients"
    ADMIN_PLUGINS = "admin.plugins"
    ADMIN_SKILLS = "admin.skills"
    ADMIN_MEMORY = "admin.memory"
    ADMIN_VOICE = "admin.voice"
    ADMIN_MONITOR = "admin.monitor"
    ADMIN_CONFIG = "admin.config"

    # Server -> Client: Remote Administration (P12-07)
    ADMIN_PONG = "admin.pong"
    ADMIN_STATUS_RESPONSE = "admin.status"
    ADMIN_INFO_RESPONSE = "admin.info"
    ADMIN_SHUTDOWN_RESPONSE = "admin.shutdown"
    ADMIN_RESTART_RESPONSE = "admin.restart"
    ADMIN_CLIENTS_RESPONSE = "admin.clients"
    ADMIN_PLUGINS_RESPONSE = "admin.plugins"
    ADMIN_SKILLS_RESPONSE = "admin.skills"
    ADMIN_MEMORY_RESPONSE = "admin.memory"
    ADMIN_VOICE_RESPONSE = "admin.voice"
    ADMIN_MONITOR_RESPONSE = "admin.monitor"
    ADMIN_CONFIG_RESPONSE = "admin.config"
    ADMIN_ERROR = "admin.error"

    # Client -> Server: Remote Command Execution (P12-05)
    COMMAND_EXECUTE = "command.execute"
    COMMAND_CANCEL = "command.cancel"

    # Server -> Client: Remote Command Execution (P12-05)
    COMMAND_RESULT = "command.result"
    COMMAND_ERROR = "command.error"
    COMMAND_PROGRESS = "command.progress"

    # Client -> Server: Remote File Transfer (P12-06)
    FILE_UPLOAD_START = "file.upload.start"
    FILE_UPLOAD_CHUNK = "file.upload.chunk"
    FILE_UPLOAD_COMPLETE = "file.upload.complete"
    FILE_UPLOAD_CANCEL = "file.upload.cancel"
    FILE_DOWNLOAD_START = "file.download.start"
    FILE_DOWNLOAD_CANCEL = "file.download.cancel"

    # Server -> Client: Remote File Transfer (P12-06)
    FILE_UPLOAD_STARTED = "file.upload.started"
    FILE_UPLOAD_DONE = "file.upload.done"
    FILE_DOWNLOAD_INIT = "file.download.init"
    FILE_DOWNLOAD_CHUNK = "file.download.chunk"
    FILE_DOWNLOAD_DONE = "file.download.done"
    FILE_PROGRESS = "file.progress"
    FILE_ERROR = "file.error"

    # Client <-> Server: Authentication (P12-08)
    AUTH_REQUEST = "auth.request"
    AUTH_RESPONSE = "auth.response"
    AUTH_SUCCESS = "auth.success"
    AUTH_FAILURE = "auth.failure"
    AUTH_REFRESH = "auth.refresh"
    AUTH_LOGOUT = "auth.logout"
    AUTH_EXPIRED = "auth.expired"
    AUTH_DENIED = "auth.denied"

    # System Monitor
    SYSTEM_METRICS = "system.metrics"
    SYSTEM_HEALTH = "system.health"
    SYSTEM_WARNING = "system.warning"


class ClientMessage(BaseModel):
    """Message sent from a WebSocket client to the server."""

    type: WSMessageType = Field(..., description="Message type")
    payload: dict[str, Any] = Field(default_factory=dict, description="Message payload")
    target: str | None = Field(None, description="Target client ID for directed messages")
    room: str | None = Field(None, description="Room name for join/leave/room messages")
    event: str | None = Field(None, description="Event type for subscribe/unsubscribe")


class ServerMessage(BaseModel):
    """Message sent from the server to a WebSocket client."""

    type: WSMessageType = Field(..., description="Message type")
    payload: dict[str, Any] = Field(default_factory=dict, description="Message payload")
    sender: str | None = Field(None, description="Sender client ID")
    room: str | None = Field(None, description="Room name")
    event: str | None = Field(None, description="Event type")
    timestamp: str = Field("", description="ISO-8601 timestamp")


class WSPongMessage(ServerMessage):
    type: WSMessageType = WSMessageType.PONG


class WSErrorMessage(ServerMessage):
    type: WSMessageType = WSMessageType.ERROR


class WSSubscribedMessage(ServerMessage):
    type: WSMessageType = WSMessageType.SUBSCRIBED


class WSUnsubscribedMessage(ServerMessage):
    type: WSMessageType = WSMessageType.UNSUBSCRIBED


class WSJoinedMessage(ServerMessage):
    type: WSMessageType = WSMessageType.JOINED


class WSLeftMessage(ServerMessage):
    type: WSMessageType = WSMessageType.LEFT


class WSMessage(ServerMessage):
    type: WSMessageType = WSMessageType.MESSAGE
