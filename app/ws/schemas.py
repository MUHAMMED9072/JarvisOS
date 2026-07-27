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

    # Server -> Client
    PONG = "pong"
    SUBSCRIBED = "subscribed"
    UNSUBSCRIBED = "unsubscribed"
    JOINED = "joined"
    LEFT = "left"
    EVENT = "event"
    ERROR = "error"


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
