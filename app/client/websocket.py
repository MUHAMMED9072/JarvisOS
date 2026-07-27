from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Any, Callable

import websockets

from app.client.events import EventDispatcher

logger = logging.getLogger("jarvis.client.ws")


class WebSocketClient:
    """Async WebSocket client for the JARVIS API.

    Features:
    - Automatic connect and reconnect
    - Heartbeat (ping/pong)
    - Authentication (api key, bearer token, reconnect token)
    - Event subscriptions with wildcards
    - Message callbacks
    """

    def __init__(
        self,
        url: str = "ws://localhost:8000/api/v1/ws",
        api_key: str | None = None,
        bearer_token: str | None = None,
        reconnect_token: str | None = None,
        heartbeat_interval: float = 30.0,
        auto_reconnect: bool = True,
        max_reconnect_delay: float = 30.0,
    ) -> None:
        self._url = url
        self._api_key = api_key
        self._bearer_token = bearer_token
        self._reconnect_token = reconnect_token
        self._heartbeat_interval = heartbeat_interval
        self._auto_reconnect = auto_reconnect
        self._max_reconnect_delay = max_reconnect_delay

        self._ws: websockets.WebSocketClientProtocol | None = None
        self._connected = False
        self._client_id: str | None = None
        self._session_id: str | None = None
        self._closing = False

        self.events = EventDispatcher()
        self._message_task: asyncio.Task[None] | None = None
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._reconnect_task: asyncio.Task[None] | None = None
        self._reconnect_count = 0
        self._last_pong: float = 0.0

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def client_id(self) -> str | None:
        return self._client_id

    @property
    def session_id(self) -> str | None:
        return self._session_id

    @property
    def reconnect_count(self) -> int:
        return self._reconnect_count

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> str | None:
        """Connect to the WebSocket server.

        Returns the assigned client_id, or ``None`` on failure.
        """
        self._closing = False
        params = []
        if self._api_key:
            params.append(f"token=apikey%20{self._api_key}")
        elif self._bearer_token:
            params.append(f"token=bearer%20{self._bearer_token}")
        if self._reconnect_token:
            params.append(f"reconnect_token={self._reconnect_token}")

        uri = self._url
        if params:
            sep = "&" if "?" in uri else "?"
            uri = f"{uri}{sep}{'&'.join(params)}"

        try:
            self._ws = await websockets.connect(uri, close_timeout=5)
            self._connected = True
            self._last_pong = time.monotonic()

            self.events.publish("connection.opened")

            self._message_task = asyncio.create_task(self._message_loop())
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

            return self._client_id
        except Exception as exc:
            logger.error("WebSocket connect failed: %s", exc)
            self.events.publish("connection.error", error=str(exc))
            return None

    async def disconnect(self) -> None:
        """Disconnect from the WebSocket server."""
        self._closing = True
        self._connected = False
        self.events.publish("connection.closed")

        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None

        if self._message_task is not None:
            self._message_task.cancel()
            try:
                await self._message_task
            except asyncio.CancelledError:
                pass
            self._message_task = None

        if self._reconnect_task is not None:
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass
            self._reconnect_task = None

        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None

    async def shutdown(self) -> None:
        """Full shutdown — disconnect and clear all event handlers."""
        await self.disconnect()
        self.events.clear()

    # ------------------------------------------------------------------
    # Reconnection
    # ------------------------------------------------------------------

    async def reconnect(self) -> bool:
        """Attempt to reconnect to the server."""
        self._reconnect_count += 1
        self.events.publish("connection.reconnecting", attempt=self._reconnect_count)

        cid = await self.connect()
        if cid is not None:
            self._client_id = cid
            self.events.publish("connection.reconnected", client_id=cid, count=self._reconnect_count)
            return True

        return False

    async def _auto_reconnect_loop(self) -> None:
        delay = 1.0
        while not self._closing:
            await asyncio.sleep(delay)
            if self._connected or self._closing:
                break
            try:
                ok = await self.reconnect()
                if ok:
                    break
            except Exception:
                pass
            delay = min(delay * 2, self._max_reconnect_delay)

    # ------------------------------------------------------------------
    # Message I/O
    # ------------------------------------------------------------------

    async def send(self, msg_type: str, payload: dict[str, Any] | None = None,
                   **kwargs: Any) -> None:
        """Send a typed message to the server."""
        if self._ws is None or not self._connected:
            raise RuntimeError("WebSocket not connected")

        message: dict[str, Any] = {
            "type": msg_type,
            "payload": payload or {},
        }
        message.update(kwargs)
        await self._ws.send(json.dumps(message))

    async def send_message(self, msg_type: str, **payload: Any) -> None:
        """Convenience: send a message with keyword payload."""
        await self.send(msg_type, payload)

    async def _message_loop(self) -> None:
        """Background task: drain incoming messages."""
        try:
            async for raw in self._ws:
                try:
                    data = json.loads(raw)
                    msg_type = data.get("type", "")
                    payload = data.get("payload", {})

                    # Store client_id from various response types
                    if msg_type in ("auth.success", "reconnect.success", "connect"):
                        self._client_id = payload.get("client_id") or self._client_id
                        self._session_id = payload.get("session_id") or self._session_id

                    # Handle heartbeat
                    if msg_type == "heartbeat":
                        hb_id = payload.get("heartbeat_id", "")
                        await self.send("heartbeat_ack", {"heartbeat_id": hb_id})
                        continue

                    # Handle pong
                    if msg_type == "pong":
                        self._last_pong = time.monotonic()
                        continue

                    # Publish to event dispatcher
                    self.events.publish(f"message.{msg_type}", data=data)
                    self.events.publish("message.received", data=data)

                except json.JSONDecodeError:
                    pass
        except websockets.ConnectionClosed:
            pass
        except asyncio.CancelledError:
            return
        finally:
            self._connected = False
            self.events.publish("connection.closed")
            if self._auto_reconnect and not self._closing:
                self._reconnect_task = asyncio.create_task(self._auto_reconnect_loop())

    # ------------------------------------------------------------------
    # Heartbeat
    # ------------------------------------------------------------------

    async def _heartbeat_loop(self) -> None:
        """Periodic heartbeat send."""
        while True:
            await asyncio.sleep(self._heartbeat_interval)
            if not self._connected or self._ws is None:
                break
            try:
                await self.send("ping")
            except Exception:
                break

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    async def authenticate(self, token: str) -> bool:
        """Send an authentication request and wait for response."""
        future: asyncio.Future[bool] = asyncio.get_running_loop().create_future()

        def _handler(event: str, **data: Any) -> None:
            msg = data.get("data", {})
            mtype = msg.get("type", "")
            if mtype == "auth.success":
                self._client_id = msg.get("payload", {}).get("client_id") or self._client_id
                self._session_id = msg.get("payload", {}).get("session_id")
                if not future.done():
                    future.set_result(True)
            elif mtype == "auth.failure":
                if not future.done():
                    future.set_result(False)

        self.events.subscribe("message.auth.*", _handler)

        try:
            await self.send("auth.request", {"token": token})
            return await asyncio.wait_for(future, timeout=30.0)
        except asyncio.TimeoutError:
            return False
        finally:
            self.events.unsubscribe("message.auth.*", _handler)

    async def refresh_session(self) -> bool:
        """Refresh the current authentication session."""
        if not self._session_id:
            return False
        future: asyncio.Future[bool] = asyncio.get_running_loop().create_future()

        def _handler(event: str, **data: Any) -> None:
            msg = data.get("data", {})
            if msg.get("type") == "auth.response":
                if not future.done():
                    future.set_result(True)

        self.events.subscribe("message.auth.response", _handler)
        try:
            await self.send("auth.refresh", {"session_id": self._session_id})
            return await asyncio.wait_for(future, timeout=30.0)
        except asyncio.TimeoutError:
            return False
        finally:
            self.events.unsubscribe("message.auth.response", _handler)

    async def logout(self) -> None:
        """Log out and invalidate the current session."""
        await self.send("auth.logout", {})
        self._session_id = None

    # ------------------------------------------------------------------
    # Subscriptions
    # ------------------------------------------------------------------

    async def subscribe(self, event: str) -> None:
        await self.send("subscribe", event=event)

    async def unsubscribe(self, event: str) -> None:
        await self.send("unsubscribe", event=event)

    async def join_room(self, room: str) -> None:
        await self.send("join", room=room)

    async def leave_room(self, room: str) -> None:
        await self.send("leave", room=room)

    # ------------------------------------------------------------------
    # Event listener shortcuts
    # ------------------------------------------------------------------

    def on(self, event: str, callback: Callable[..., None]) -> None:
        """Register a callback for a WebSocket message event."""
        prefixed = event if event.startswith("message.") else f"message.{event}"
        self.events.subscribe(prefixed, callback)

    def off(self, event: str, callback: Callable[..., None]) -> None:
        prefixed = event if event.startswith("message.") else f"message.{event}"
        self.events.unsubscribe(prefixed, callback)
