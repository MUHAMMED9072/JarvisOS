from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from fastapi import WebSocket

from app.core.logger import JarvisLogger
from app.ws.auth import WSAuthenticator
from app.ws.schemas import (
    ClientMessage,
    ServerMessage,
    WSMessageType,
)


class ConnectionInfo:
    """Metadata about a single WebSocket connection."""

    __slots__ = ("client_id", "websocket", "metadata", "rooms", "subscriptions", "connected_at", "last_heartbeat")

    def __init__(
        self,
        client_id: str,
        websocket: WebSocket,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.client_id: str = client_id
        self.websocket: WebSocket = websocket
        self.metadata: dict[str, Any] = metadata or {}
        self.rooms: set[str] = set()
        self.subscriptions: set[str] = set()
        self.connected_at: float = time.monotonic()
        self.last_heartbeat: float = time.monotonic()


class WebSocketConnectionManager:
    """Thread-safe, async-first manager for WebSocket connections.

    Supports:
    - Client registration / disconnection
    - Room / channel membership
    - Event subscriptions
    - Broadcast, targeted, and room-scoped messaging
    - Heartbeat / ping-pong
    - Authentication hook
    - JSON serialization
    """

    def __init__(
        self,
        authenticator: WSAuthenticator | None = None,
        heartbeat_interval: float = 30.0,
        heartbeat_timeout: float = 10.0,
    ) -> None:
        self._authenticator = authenticator or WSAuthenticator()
        self._heartbeat_interval = heartbeat_interval
        self._heartbeat_timeout = heartbeat_timeout

        self._lock = asyncio.Lock()
        self._connections: dict[str, ConnectionInfo] = {}
        self._rooms: dict[str, set[str]] = defaultdict(set)
        self._heartbeat_task: asyncio.Task[None] | None = None

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    async def connect(
        self,
        websocket: WebSocket,
        client_id: str | None = None,
        token: str | None = None,
    ) -> ConnectionInfo | None:
        """Accept and register a new WebSocket connection.

        Returns the connection info on success, or ``None`` if
        authentication failed.
        """
        await websocket.accept()

        cid = client_id or str(uuid.uuid4())

        headers = dict(websocket.headers) if websocket.headers else {}

        metadata = await self._authenticator.authenticate(
            client_id=cid,
            token=token,
            headers=headers,
        )
        if metadata is None:
            await websocket.close(code=4001, reason="Authentication failed")
            return None

        info = ConnectionInfo(client_id=cid, websocket=websocket, metadata=metadata)

        async with self._lock:
            self._connections[cid] = info

        await self._authenticator.on_connect(cid, metadata)
        self._start_heartbeat()
        return info

    async def disconnect(self, client_id: str) -> None:
        """Disconnect and remove a client."""
        info: ConnectionInfo | None = None
        async with self._lock:
            info = self._connections.pop(client_id, None)
            if info:
                for room in list(info.rooms):
                    if room in self._rooms:
                        self._rooms[room].discard(client_id)
                        if not self._rooms[room]:
                            del self._rooms[room]

        if info:
            await self._authenticator.on_disconnect(client_id)
            try:
                await info.websocket.close(code=1000, reason="Client disconnected")
            except Exception:
                pass

    async def is_connected(self, client_id: str) -> bool:
        async with self._lock:
            return client_id in self._connections

    def get_connection(self, client_id: str) -> ConnectionInfo | None:
        return self._connections.get(client_id)

    async def get_active_count(self) -> int:
        async with self._lock:
            return len(self._connections)

    async def get_connected_ids(self) -> list[str]:
        async with self._lock:
            return list(self._connections.keys())

    # ------------------------------------------------------------------
    # Room management
    # ------------------------------------------------------------------

    async def join_room(self, client_id: str, room: str) -> bool:
        async with self._lock:
            info = self._connections.get(client_id)
            if info is None:
                return False
            info.rooms.add(room)
            self._rooms[room].add(client_id)
            return True

    async def leave_room(self, client_id: str, room: str) -> bool:
        async with self._lock:
            info = self._connections.get(client_id)
            if info is None:
                return False
            info.rooms.discard(room)
            self._rooms[room].discard(client_id)
            if not self._rooms[room]:
                del self._rooms[room]
            return True

    async def get_room_members(self, room: str) -> list[str]:
        async with self._lock:
            return list(self._rooms.get(room, set()))

    async def get_client_rooms(self, client_id: str) -> list[str]:
        async with self._lock:
            info = self._connections.get(client_id)
            if info is None:
                return []
            return list(info.rooms)

    # ------------------------------------------------------------------
    # Event subscriptions
    # ------------------------------------------------------------------

    async def subscribe(self, client_id: str, event: str) -> bool:
        async with self._lock:
            info = self._connections.get(client_id)
            if info is None:
                return False
            info.subscriptions.add(event)
            return True

    async def unsubscribe(self, client_id: str, event: str) -> bool:
        async with self._lock:
            info = self._connections.get(client_id)
            if info is None:
                return False
            info.subscriptions.discard(event)
            return True

    async def get_subscribed_clients(self, event: str) -> list[str]:
        async with self._lock:
            return [
                cid
                for cid, info in self._connections.items()
                if event in info.subscriptions
            ]

    # ------------------------------------------------------------------
    # Messaging
    # ------------------------------------------------------------------

    async def send(self, client_id: str, message: ServerMessage) -> bool:
        """Send a message to a specific client."""
        info: ConnectionInfo | None
        async with self._lock:
            info = self._connections.get(client_id)
        if info is None:
            return False
        return await self._send_json(info, message)

    async def broadcast(self, message: ServerMessage) -> int:
        """Send a message to all connected clients.

        Returns the number of successful sends.
        """
        targets: list[ConnectionInfo] = []
        async with self._lock:
            targets = list(self._connections.values())
        count = 0
        for info in targets:
            if await self._send_json(info, message):
                count += 1
        return count

    async def send_to_room(self, room: str, message: ServerMessage) -> int:
        """Send a message to all clients in a room.

        Returns the number of successful sends.
        """
        members: list[str] = []
        async with self._lock:
            members = list(self._rooms.get(room, set()))
        count = 0
        for cid in members:
            if await self.send(cid, message):
                count += 1
        return count

    async def send_to_subscribers(self, event: str, message: ServerMessage) -> int:
        """Send a message to all clients subscribed to an event.

        Returns the number of successful sends.
        """
        subscribers = await self.get_subscribed_clients(event)
        count = 0
        for cid in subscribers:
            if await self.send(cid, message):
                count += 1
        return count

    async def _send_json(self, info: ConnectionInfo, message: ServerMessage) -> bool:
        """Serialize and send a JSON message to a single client.

        Returns ``True`` on success. On failure, the client is
        disconnected and removed.
        """
        payload = message.model_dump(exclude_none=True)
        payload.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
        try:
            await info.websocket.send_json(payload)
            return True
        except Exception:
            JarvisLogger.warning("Failed to send to %s; removing", info.client_id)
            await self.disconnect(info.client_id)
            return False

    # ------------------------------------------------------------------
    # Incoming message handling
    # ------------------------------------------------------------------

    async def handle_message(self, client_id: str, raw: str) -> ServerMessage | None:
        """Parse and handle an incoming WebSocket message.

        Returns a response message when one is needed, or ``None``.
        """
        try:
            data = json.loads(raw)
            msg = ClientMessage(**data)
        except (json.JSONDecodeError, ValueError) as exc:
            return ServerMessage(
                type=WSMessageType.ERROR,
                payload={"error": f"Invalid message: {exc}"},
            )

        if msg.type == WSMessageType.PING:
            info = self.get_connection(client_id)
            if info:
                info.last_heartbeat = time.monotonic()
            return ServerMessage(type=WSMessageType.PONG)

        if msg.type == WSMessageType.SUBSCRIBE:
            if msg.event:
                await self.subscribe(client_id, msg.event)
                return ServerMessage(
                    type=WSMessageType.SUBSCRIBED,
                    event=msg.event,
                )

        if msg.type == WSMessageType.UNSUBSCRIBE:
            if msg.event:
                await self.unsubscribe(client_id, msg.event)
                return ServerMessage(
                    type=WSMessageType.UNSUBSCRIBED,
                    event=msg.event,
                )

        if msg.type == WSMessageType.JOIN:
            if msg.room:
                await self.join_room(client_id, msg.room)
                return ServerMessage(
                    type=WSMessageType.JOINED,
                    room=msg.room,
                )

        if msg.type == WSMessageType.LEAVE:
            if msg.room:
                await self.leave_room(client_id, msg.room)
                return ServerMessage(
                    type=WSMessageType.LEFT,
                    room=msg.room,
                )

        if msg.type == WSMessageType.MESSAGE:
            if msg.target:
                await self.send(
                    msg.target,
                    ServerMessage(
                        type=WSMessageType.MESSAGE,
                        payload=msg.payload,
                        sender=client_id,
                    ),
                )
                return None

        return None

    # ------------------------------------------------------------------
    # Heartbeat
    # ------------------------------------------------------------------

    def _start_heartbeat(self) -> None:
        if self._heartbeat_task is not None and not self._heartbeat_task.done():
            return
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def _heartbeat_loop(self) -> None:
        while True:
            await asyncio.sleep(self._heartbeat_interval)
            stale: list[str] = []
            async with self._lock:
                now = time.monotonic()
                for cid, info in list(self._connections.items()):
                    if now - info.last_heartbeat > self._heartbeat_timeout:
                        stale.append(cid)
            for cid in stale:
                JarvisLogger.warning("Heartbeat timeout for %s; disconnecting", cid)
                await self.disconnect(cid)
            if not stale and not self._connections:
                break

    async def shutdown(self) -> None:
        """Disconnect all clients and stop the heartbeat."""
        if self._heartbeat_task is not None and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None

        async with self._lock:
            cids = list(self._connections.keys())
        for cid in cids:
            await self.disconnect(cid)
