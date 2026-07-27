from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Callable

from fastapi import WebSocket

from app.core.logger import JarvisLogger
from app.ws.auth import WSAuthenticator
from app.ws.events import EventEnvelope, get_matching_subscriptions
from app.ws.reliability import ConnectionStats, OfflineQueue, RetryQueue, compress_payload
from app.ws.schemas import (
    ClientMessage,
    ServerMessage,
    WSMessageType,
)


class ConnectionInfo:
    """Metadata about a single WebSocket connection."""

    def __init__(
        self,
        client_id: str,
        websocket: WebSocket,
        metadata: dict[str, Any] | None = None,
        queue_maxsize: int = 100,
        config: Any = None,
    ) -> None:
        self.client_id: str = client_id
        self.websocket: WebSocket = websocket
        self.metadata: dict[str, Any] = metadata or {}
        self.rooms: set[str] = set()
        self.subscriptions: set[str] = set()
        self.connected_at: float = time.monotonic()
        self.last_heartbeat: float = time.monotonic()
        self.event_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(
            maxsize=queue_maxsize
        )
        self.dispatch_task: asyncio.Task[None] | None = None

        # --- Reliability (P12-09) ---
        from app.core.config import Config as _Cfg
        cfg = config or _Cfg

        self.stats: ConnectionStats = ConnectionStats(connected_at=self.connected_at)

        self.last_active_heartbeat: float = time.monotonic()
        self.pending_heartbeats: dict[str, float] = {}

        retry_send_fn: Callable[[dict[str, Any]], bool] | None = None
        if getattr(cfg, "WS_RELIABLE_SEND_ENABLED", True):
            self.retry_queue: RetryQueue | None = RetryQueue(
                client_id=client_id,
                max_retries=getattr(cfg, "WS_MAX_RETRIES", 3),
                retry_interval=getattr(cfg, "WS_RETRY_INTERVAL", 5.0),
                ack_timeout=getattr(cfg, "WS_ACK_TIMEOUT", 30.0),
            )
        else:
            self.retry_queue = None

        self.reconnect_token: str | None = None
        self.reconnect_token_expires: float = 0.0
        self.reconnect_count: int = 0

        if getattr(cfg, "WS_OFFLINE_QUEUE_ENABLED", True):
            self.offline_queue: OfflineQueue | None = OfflineQueue(
                maxsize=getattr(cfg, "WS_OFFLINE_QUEUE_MAXSIZE", 100),
                overflow_strategy=getattr(cfg, "WS_OFFLINE_QUEUE_OVERFLOW", "drop_oldest"),
            )
        else:
            self.offline_queue = None


class WebSocketConnectionManager:
    """Thread-safe, async-first manager for WebSocket connections.

    Supports:
    - Client registration / disconnection
    - Room / channel membership
    - Event subscriptions
    - Broadcast, targeted, and room-scoped messaging
    - Heartbeat / ping-pong (passive + active P12-09)
    - Authentication hook
    - JSON serialization
    - Message ACKs & reliable send (P12-09)
    - Reconnection with state restore (P12-09)
    - Offline message queue (P12-09)
    - Connection statistics (P12-09)
    """

    def __init__(
        self,
        authenticator: WSAuthenticator | None = None,
        heartbeat_interval: float = 30.0,
        heartbeat_timeout: float = 10.0,
        config: Any = None,
    ) -> None:
        self._authenticator = authenticator or WSAuthenticator()
        self._heartbeat_interval = heartbeat_interval
        self._heartbeat_timeout = heartbeat_timeout

        from app.core.config import Config as _Cfg
        self._config = config or _Cfg

        self._lock = asyncio.Lock()
        self._connections: dict[str, ConnectionInfo] = {}
        self._rooms: dict[str, set[str]] = defaultdict(set)
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._active_heartbeat_task: asyncio.Task[None] | None = None

        # EventBus for reliability events
        self._event_bus: Any = None
        if self._authenticator is not None:
            self._event_bus = getattr(self._authenticator, "_event_bus", None)

    # ------------------------------------------------------------------
    # EventBus integration
    # ------------------------------------------------------------------

    def _publish(self, event: str, **data: Any) -> None:
        if self._event_bus is not None:
            try:
                self._event_bus.publish(event, **data)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    async def connect(
        self,
        websocket: WebSocket,
        client_id: str | None = None,
        token: str | None = None,
        reconnect_token: str | None = None,
    ) -> ConnectionInfo | None:
        """Accept and register a new WebSocket connection.

        Handles both fresh connections and reconnections (when
        *reconnect_token* is provided).

        Returns the connection info on success, or ``None`` if
        authentication / reconnection failed.
        """
        await websocket.accept()

        cid = client_id or str(uuid.uuid4())

        # -----------------------------------------------------------
        # Try reconnection path first
        # -----------------------------------------------------------
        if reconnect_token and getattr(self._config, "WS_RECONNECT_ENABLED", True):
            result = await self._handle_reconnect(
                cid, reconnect_token, websocket,
            )
            if result is not None:
                return result

        # -----------------------------------------------------------
        # Fresh connection
        # -----------------------------------------------------------
        headers = dict(websocket.headers) if websocket.headers else {}

        metadata = await self._authenticator.authenticate(
            client_id=cid,
            token=token,
            headers=headers,
        )
        if metadata is None:
            await websocket.close(code=4001, reason="Authentication failed")
            return None

        info = ConnectionInfo(
            client_id=cid,
            websocket=websocket,
            metadata=metadata,
            config=self._config,
        )

        async with self._lock:
            self._connections[cid] = info

        await self._authenticator.on_connect(cid, metadata)
        self._start_heartbeat()

        # Generate a reconnect token for this connection
        await self._generate_reconnect_token(cid)

        return info

    async def _handle_reconnect(
        self,
        client_id: str,
        reconnect_token: str,
        websocket: WebSocket,
    ) -> ConnectionInfo | None:
        """Restore a previous connection using a reconnect token."""
        old_cid = None
        old_info: ConnectionInfo | None = None

        async with self._lock:
            for cid, info in list(self._connections.items()):
                if info.reconnect_token == reconnect_token:
                    if time.monotonic() < info.reconnect_token_expires:
                        old_cid = cid
                        old_info = info
                        break

        if old_info is None:
            return None

        # Cancel old dispatch/retry tasks
        if old_info.dispatch_task is not None and not old_info.dispatch_task.done():
            old_info.dispatch_task.cancel()
            try:
                await old_info.dispatch_task
            except asyncio.CancelledError:
                pass

        # Update connection
        old_info.websocket = websocket
        old_info.last_heartbeat = time.monotonic()
        old_info.last_active_heartbeat = time.monotonic()
        old_info.reconnect_count += 1
        old_info.stats.reconnect_count += 1

        # Update connection registry if cid changed
        if old_cid != client_id:
            async with self._lock:
                self._connections.pop(old_cid, None)
                self._connections[client_id] = old_info
            old_info.client_id = client_id
            old_info.metadata["client_id"] = client_id
        else:
            # Still need lock to ensure consistency
            async with self._lock:
                self._connections[client_id] = old_info

        # Drain offline queue
        if old_info.offline_queue is not None:
            queued = await old_info.offline_queue.drain()
            if queued:
                self._publish("ws.offline_queue.drained",
                              client_id=client_id, count=len(queued))

        # Start dispatch task
        old_info.dispatch_task = asyncio.create_task(
            self._dispatch_loop(client_id, old_info)
        )

        await self._authenticator.on_connect(client_id, old_info.metadata)
        self._start_heartbeat()

        # Invalidate the reused token and generate a fresh one
        old_info.reconnect_token = None
        old_info.reconnect_token_expires = 0.0
        await self._generate_reconnect_token(client_id)

        JarvisLogger.info(
            "Client reconnected: %s (reconnect #%d)",
            client_id, old_info.reconnect_count,
        )

        return old_info

    async def generate_reconnect_token(self, client_id: str) -> str | None:
        """Externally generate a reconnect token (used by authenticator)."""
        return await self._generate_reconnect_token(client_id)

    async def _generate_reconnect_token(self, client_id: str) -> str | None:
        """Generate a reconnect token for the given client."""
        async with self._lock:
            info = self._connections.get(client_id)
            if info is None:
                return None
            raw = f"{client_id}:{uuid.uuid4().hex}:{time.monotonic()}"
            secret = getattr(self._config, "WS_AUTH_BEARER_SECRET", "change-me-in-production")
            sig = hmac.new(secret.encode(), raw.encode(), hashlib.sha256).hexdigest()[:12]
            token = f"rtok:{uuid.uuid4().hex}:{sig}"
            expiry = getattr(self._config, "WS_RECONNECT_TOKEN_EXPIRY", 300.0)
            info.reconnect_token = token
            info.reconnect_token_expires = time.monotonic() + expiry
            self._publish("ws.reconnect.token_generated",
                          client_id=client_id, token=token)
            return token

    async def disconnect(self, client_id: str) -> None:
        """Disconnect and remove a client."""
        info: ConnectionInfo | None = None
        async with self._lock:
            info = self._connections.pop(client_id, None)
            if info:
                await self._cancel_tasks(info)
                for room in list(info.rooms):
                    if room in self._rooms:
                        self._rooms[room].discard(client_id)
                        if not self._rooms[room]:
                            del self._rooms[room]

        if info:
            # Move unacked messages to offline queue before disconnect
            if info.retry_queue is not None and info.offline_queue is not None:
                pending = await info.retry_queue.clear()
                for msg in pending:
                    await info.offline_queue.put(msg)

            if info.retry_queue is not None:
                await info.retry_queue.stop_retry_loop()

            await self._authenticator.on_disconnect(client_id)
            try:
                await info.websocket.close(code=1000, reason="Client disconnected")
            except Exception:
                pass

    async def _cancel_tasks(self, info: ConnectionInfo) -> None:
        """Cancel a connection's background tasks."""
        if info.dispatch_task is not None and not info.dispatch_task.done():
            info.dispatch_task.cancel()
            try:
                await info.dispatch_task
            except asyncio.CancelledError:
                pass
            info.dispatch_task = None

    # ------------------------------------------------------------------
    # Connection queries
    # ------------------------------------------------------------------

    async def is_connected(self, client_id: str) -> bool:
        async with self._lock:
            return client_id in self._connections

    def get_connection(self, client_id: str) -> ConnectionInfo | None:
        return self._connections.get(client_id)

    async def update_metadata(
        self,
        client_id: str,
        metadata: dict[str, Any],
    ) -> bool:
        async with self._lock:
            info = self._connections.get(client_id)
            if info is None:
                return False
            info.metadata.update(metadata)
            return True

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

    async def get_subscribed_clients_for_event(self, event_name: str) -> list[str]:
        """Return all client IDs whose subscription patterns match *event_name*.

        Supports wildcard (fnmatch) patterns in client subscriptions.
        """
        async with self._lock:
            return [
                cid
                for cid, info in self._connections.items()
                if get_matching_subscriptions(info.subscriptions, event_name)
            ]

    # ------------------------------------------------------------------
    # Event streaming (per-client queue + dispatch)
    # ------------------------------------------------------------------

    async def enqueue_event(
        self,
        client_id: str,
        envelope: EventEnvelope,
    ) -> bool:
        """Push an event envelope onto a client's event queue.

        If the queue is full, the oldest event is dropped (backpressure).
        Returns ``True`` if the enqueue succeeded, ``False`` if the
        client was not found.
        """
        async with self._lock:
            info = self._connections.get(client_id)
            if info is None:
                return False
            try:
                info.event_queue.put_nowait(envelope.model_dump())
            except asyncio.QueueFull:
                info.stats.dropped_messages += 1
                try:
                    info.event_queue.get_nowait()
                    info.event_queue.put_nowait(envelope.model_dump())
                except asyncio.QueueEmpty:
                    pass
            if info.dispatch_task is None or info.dispatch_task.done():
                info.dispatch_task = asyncio.create_task(
                    self._dispatch_loop(client_id, info)
                )
        return True

    async def _dispatch_loop(
        self,
        client_id: str,
        info: ConnectionInfo,
    ) -> None:
        """Background task: drain the client's event queue and send via WS."""
        while True:
            try:
                payload = await info.event_queue.get()
                try:
                    await info.websocket.send_json(payload)
                except Exception:
                    JarvisLogger.warning(
                        "Dispatch send failed for %s; removing", client_id
                    )
                    await self.disconnect(client_id)
                    return
            except asyncio.CancelledError:
                return

    async def stop_dispatch(self, client_id: str) -> None:
        """Cancel a client's dispatch task."""
        async with self._lock:
            info = self._connections.get(client_id)
            if info is None:
                return
            if info.dispatch_task is not None and not info.dispatch_task.done():
                info.dispatch_task.cancel()
                try:
                    await info.dispatch_task
                except asyncio.CancelledError:
                    pass
                info.dispatch_task = None

    # ------------------------------------------------------------------
    # Messaging (standard + reliable + ack-aware)
    # ------------------------------------------------------------------

    async def send(self, client_id: str, message: ServerMessage,
                   require_ack: bool = False) -> bool:
        """Send a message to a specific client.

        If *require_ack* is True and reliability is enabled, the message
        is tracked for retry until the client acknowledges it.
        """
        info: ConnectionInfo | None
        async with self._lock:
            info = self._connections.get(client_id)
        if info is None:
            return False
        return await self._send_json(info, message, require_ack=require_ack)

    async def send_reliable(self, client_id: str, message: ServerMessage) -> bool:
        """Send a message with automatic retry until acknowledged."""
        return await self.send(client_id, message, require_ack=True)

    async def broadcast(self, message: ServerMessage,
                        require_ack: bool = False) -> int:
        """Send a message to all connected clients.

        Returns the number of successful sends.
        """
        targets: list[ConnectionInfo] = []
        async with self._lock:
            targets = list(self._connections.values())
        count = 0
        for info in targets:
            if await self._send_json(info, message, require_ack=require_ack):
                count += 1
        return count

    async def send_to_room(self, room: str, message: ServerMessage,
                           require_ack: bool = False) -> int:
        """Send a message to all clients in a room.

        Returns the number of successful sends.
        """
        members: list[str] = []
        async with self._lock:
            members = list(self._rooms.get(room, set()))
        count = 0
        for cid in members:
            if await self.send(cid, message, require_ack=require_ack):
                count += 1
        return count

    async def send_to_subscribers(self, event: str, message: ServerMessage,
                                  require_ack: bool = False) -> int:
        """Send a message to all clients subscribed to an event (supports wildcards).

        Returns the number of successful sends.
        """
        subscribers = await self.get_subscribed_clients_for_event(event)
        count = 0
        for cid in subscribers:
            if await self.send(cid, message, require_ack=require_ack):
                count += 1
        return count

    async def _send_json(self, info: ConnectionInfo, message: ServerMessage,
                         require_ack: bool = False) -> bool:
        """Serialize and send a JSON message to a single client.

        If *require_ack* is True, assigns a message_id and tracks it
        in the retry queue for automatic retry.

        Returns ``True`` on success. On failure, the client is
        disconnected and removed.
        """
        # Assign message_id if ACK requested
        ack_enabled = getattr(self._config, "WS_ACK_ENABLED", True)
        if require_ack and ack_enabled and info.retry_queue is not None:
            mid = f"msg-{uuid.uuid4().hex[:16]}"
            message.message_id = mid

        payload = message.model_dump(exclude_none=True)
        payload.setdefault("timestamp", datetime.now(timezone.utc).isoformat())

        try:
            compressed = getattr(self._config, "WS_COMPRESSION_ENABLED", False)
            min_size = getattr(self._config, "WS_COMPRESSION_MIN_SIZE", 4096)
            if compressed and len(json.dumps(payload)) > min_size:
                comp, _ = compress_payload(payload, min_size=min_size)
                if comp is not None:
                    payload["_compressed"] = True
                    raw = json.dumps(payload)
                    await info.websocket.send_text(raw)
                    info.stats.bytes_sent += len(raw.encode("utf-8"))
                else:
                    await info.websocket.send_json(payload)
                info.stats.messages_sent += 1
            else:
                await info.websocket.send_json(payload)
                info.stats.messages_sent += 1
                try:
                    raw = json.dumps(payload)
                    info.stats.bytes_sent += len(raw.encode("utf-8"))
                except Exception:
                    pass

            # Track in retry queue
            if require_ack and ack_enabled and info.retry_queue is not None and message.message_id:
                await info.retry_queue.add(message.message_id, payload)
                _info_ref = info
                async def _retry_send(p: dict[str, Any]) -> bool:
                    return await self._send_json(_info_ref, message.__class__(**p), require_ack=False)
                info.retry_queue.set_send_fn(_retry_send)

            return True
        except Exception:
            JarvisLogger.warning("Failed to send to %s; removing", info.client_id)
            await self.disconnect(info.client_id)
            return False

    async def _handle_ack(self, client_id: str, message_id: str) -> None:
        """Process an incoming ACK from a client."""
        info = self.get_connection(client_id)
        if info is None or info.retry_queue is None:
            return
        entry = await info.retry_queue.ack(message_id)
        if entry is not None:
            rtt = time.monotonic() - entry.sent_at
            info.stats.record_latency(rtt)
            self._publish("ws.ack.received",
                          client_id=client_id,
                          message_id=message_id,
                          rtt=round(rtt, 3))
            self._publish("ws.latency.update",
                          client_id=client_id,
                          rtt=round(rtt, 3),
                          avg=round(info.stats.latency_avg, 3))

    async def get_pending_ack_count(self, client_id: str) -> int:
        """Return the number of pending (unacknowledged) messages."""
        info = self.get_connection(client_id)
        if info is None or info.retry_queue is None:
            return 0
        return await info.retry_queue.pending_count()

    async def get_connection_stats(self, client_id: str) -> dict[str, Any] | None:
        """Return connection statistics for a client."""
        info = self.get_connection(client_id)
        if info is None:
            return None
        return info.stats.to_dict()

    # ------------------------------------------------------------------
    # Reconnect token validation
    # ------------------------------------------------------------------

    async def validate_reconnect_token(self, reconnect_token: str) -> str | None:
        """Validate a reconnect token and return the client_id.

        Returns ``None`` if the token is invalid or expired.
        """
        async with self._lock:
            for cid, info in self._connections.items():
                if info.reconnect_token == reconnect_token:
                    if time.monotonic() < info.reconnect_token_expires:
                        return cid
            return None

    async def revoke_reconnect_token(self, client_id: str) -> bool:
        """Revoke a client's reconnect token."""
        async with self._lock:
            info = self._connections.get(client_id)
            if info is None:
                return False
            info.reconnect_token = None
            info.reconnect_token_expires = 0.0
            self._publish("ws.reconnect.token_revoked", client_id=client_id)
            return True

    # ------------------------------------------------------------------
    # Incoming message handling
    # ------------------------------------------------------------------

    async def handle_message(self, client_id: str, raw: str,
                             info: ConnectionInfo | None = None) -> ServerMessage | None:
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

        # --- Reliability: ACK handling ---
        if msg.type == WSMessageType.ACK:
            mid = msg.payload.get("message_id", "")
            if mid:
                await self._handle_ack(client_id, mid)
            return None

        # --- Reliability: Heartbeat ACK ---
        if msg.type == WSMessageType.HEARTBEAT_ACK:
            _info = self.get_connection(client_id)
            if _info:
                hb_id = msg.payload.get("heartbeat_id", "")
                sent_at = _info.pending_heartbeats.pop(hb_id, None)
                if sent_at is not None:
                    rtt = time.monotonic() - sent_at
                    _info.stats.record_latency(rtt)
                    self._publish("ws.latency.update",
                                  client_id=client_id, rtt=round(rtt, 3))
                _info.last_active_heartbeat = time.monotonic()
            return None

        # Look up connection for stats tracking
        if info is None:
            info = self.get_connection(client_id)
        if info:
            info.stats.messages_received += 1
            info.stats.bytes_received += len(raw.encode("utf-8"))

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
    # Heartbeat (passive + active)
    # ------------------------------------------------------------------

    def _start_heartbeat(self) -> None:
        if self._heartbeat_task is not None and not self._heartbeat_task.done():
            return
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

        # Start active heartbeat if enabled
        if getattr(self._config, "WS_ACTIVE_HEARTBEAT_ENABLED", True):
            if self._active_heartbeat_task is None or self._active_heartbeat_task.done():
                self._active_heartbeat_task = asyncio.create_task(
                    self._active_heartbeat_loop()
                )

    async def _heartbeat_loop(self) -> None:
        """Passive heartbeat: check client PING timestamps."""
        while True:
            await asyncio.sleep(self._heartbeat_interval)
            stale: list[str] = []
            async with self._lock:
                now = time.monotonic()
                for cid, info in list(self._connections.items()):
                    if now - info.last_heartbeat > self._heartbeat_timeout:
                        stale.append(cid)
            for cid in stale:
                JarvisLogger.warning(
                    "Heartbeat timeout for %s; disconnecting", cid
                )
                await self.disconnect(cid)
            if not stale and not self._connections:
                break

    async def _active_heartbeat_loop(self) -> None:
        """Active heartbeat: send PING messages and measure latency."""
        while True:
            await asyncio.sleep(self._heartbeat_interval / 2)
            async with self._lock:
                now = time.monotonic()
                for cid, info in list(self._connections.items()):
                    # Check if stale (no heartbeat_ack within timeout)
                    if now - info.last_active_heartbeat > self._heartbeat_timeout:
                        continue  # Will be caught by passive heartbeat
                    # Send active heartbeat probe
                    hb_id = f"hb-{uuid.uuid4().hex[:12]}"
                    info.pending_heartbeats[hb_id] = now
                    msg = ServerMessage(
                        type=WSMessageType.HEARTBEAT,
                        payload={"heartbeat_id": hb_id},
                    )
                    payload_d = msg.model_dump(exclude_none=True)
                    payload_d.setdefault(
                        "timestamp", datetime.now(timezone.utc).isoformat()
                    )
                    try:
                        raw = json.dumps(payload_d)
                        await info.websocket.send_text(raw)
                        info.stats.messages_sent += 1
                        info.stats.bytes_sent += len(raw.encode("utf-8"))
                    except Exception:
                        pass
            if not self._connections:
                break

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    async def shutdown(self) -> None:
        """Disconnect all clients and stop all background tasks."""

        # Stop active heartbeat
        if self._active_heartbeat_task is not None and not self._active_heartbeat_task.done():
            self._active_heartbeat_task.cancel()
            try:
                await self._active_heartbeat_task
            except asyncio.CancelledError:
                pass
            self._active_heartbeat_task = None

        # Stop passive heartbeat
        if self._heartbeat_task is not None and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None

        # Stop all retry queues
        async with self._lock:
            for info in self._connections.values():
                if info.retry_queue is not None:
                    await info.retry_queue.stop_retry_loop()
                if info.dispatch_task is not None and not info.dispatch_task.done():
                    info.dispatch_task.cancel()
            cids = list(self._connections.keys())
        for cid in cids:
            await self.disconnect(cid)
