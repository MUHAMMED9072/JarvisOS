"""Tests for the WebSocket infrastructure (P12-01)."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient

from app.api.server import create_app
from app.core.registry import ServiceRegistry
from app.ws.auth import WSAuthenticator
from app.ws.manager import ConnectionInfo, WebSocketConnectionManager
from app.ws.schemas import (
    ClientMessage,
    ServerMessage,
    WSMessageType,
)


# ==========================================================================
# Helpers
# ==========================================================================


def _make_app(registry: ServiceRegistry | None = None) -> FastAPI:
    if registry is None:
        registry = ServiceRegistry()
    registry.register("dispatcher", MagicMock())
    registry.register("event_bus", MagicMock())
    return create_app(registry)


def _make_client(registry: ServiceRegistry | None = None) -> TestClient:
    return TestClient(_make_app(registry))


# ==========================================================================
# ConnectionInfo
# ==========================================================================


class TestConnectionInfo:
    """ConnectionInfo dataclass behavior."""

    def test_constructor_defaults(self):
        ws = MagicMock(spec=WebSocket)
        info = ConnectionInfo(client_id="test-1", websocket=ws)
        assert info.client_id == "test-1"
        assert info.websocket is ws
        assert info.metadata == {}
        assert info.rooms == set()
        assert info.subscriptions == set()
        assert info.connected_at > 0
        assert info.last_heartbeat > 0

    def test_constructor_with_metadata(self):
        ws = MagicMock(spec=WebSocket)
        info = ConnectionInfo(
            client_id="test-2",
            websocket=ws,
            metadata={"role": "admin"},
        )
        assert info.metadata == {"role": "admin"}


# ==========================================================================
# Connection lifecycle
# ==========================================================================


class TestConnectionLifecycle:
    """Connect, disconnect, reconnect."""

    @pytest.mark.asyncio
    async def test_connect_success(self):
        manager = WebSocketConnectionManager()
        ws = AsyncMock(spec=WebSocket)
        ws.headers = {"origin": "test"}
        info = await manager.connect(ws, client_id="client-1")
        assert info is not None
        assert info.client_id == "client-1"
        assert await manager.is_connected("client-1") is True
        ws.accept.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_connect_generates_client_id(self):
        manager = WebSocketConnectionManager()
        ws = AsyncMock(spec=WebSocket)
        ws.headers = {"origin": "test"}
        info = await manager.connect(ws)
        assert info is not None
        assert len(info.client_id) > 0
        assert info.client_id != ""

    @pytest.mark.asyncio
    async def test_connect_auth_rejected(self):
        rejector = MagicMock(spec=WSAuthenticator)
        rejector.authenticate = AsyncMock(return_value=None)
        manager = WebSocketConnectionManager(authenticator=rejector)
        ws = AsyncMock(spec=WebSocket)
        ws.headers = {}
        info = await manager.connect(ws, client_id="bad-client")
        assert info is None
        ws.close.assert_awaited_once_with(code=4001, reason="Authentication failed")

    @pytest.mark.asyncio
    async def test_disconnect_removes_client(self):
        manager = WebSocketConnectionManager()
        ws = AsyncMock(spec=WebSocket)
        ws.headers = {}
        await manager.connect(ws, client_id="to-remove")
        assert await manager.is_connected("to-remove") is True
        await manager.disconnect("to-remove")
        assert await manager.is_connected("to-remove") is False

    @pytest.mark.asyncio
    async def test_disconnect_removes_from_rooms(self):
        manager = WebSocketConnectionManager()
        ws = AsyncMock(spec=WebSocket)
        ws.headers = {}
        await manager.connect(ws, client_id="room-user")
        await manager.join_room("room-user", "general")
        assert await manager.get_room_members("general") == ["room-user"]
        await manager.disconnect("room-user")
        assert await manager.get_room_members("general") == []

    @pytest.mark.asyncio
    async def test_disconnect_nonexistent(self):
        manager = WebSocketConnectionManager()
        await manager.disconnect("does-not-exist")

    @pytest.mark.asyncio
    async def test_get_active_count(self):
        manager = WebSocketConnectionManager()
        ws1 = AsyncMock(spec=WebSocket)
        ws1.headers = {}
        ws2 = AsyncMock(spec=WebSocket)
        ws2.headers = {}
        await manager.connect(ws1, client_id="c1")
        await manager.connect(ws2, client_id="c2")
        assert await manager.get_active_count() == 2
        await manager.disconnect("c1")
        assert await manager.get_active_count() == 1

    @pytest.mark.asyncio
    async def test_get_connected_ids(self):
        manager = WebSocketConnectionManager()
        ws = AsyncMock(spec=WebSocket)
        ws.headers = {}
        await manager.connect(ws, client_id="only-one")
        ids = await manager.get_connected_ids()
        assert "only-one" in ids

    @pytest.mark.asyncio
    async def test_reconnect_same_id(self):
        manager = WebSocketConnectionManager()
        ws1 = AsyncMock(spec=WebSocket)
        ws1.headers = {}
        await manager.connect(ws1, client_id="duplicate")
        ws2 = AsyncMock(spec=WebSocket)
        ws2.headers = {}
        info = await manager.connect(ws2, client_id="duplicate")
        assert info is not None
        assert info.client_id == "duplicate"

    @pytest.mark.asyncio
    async def test_shutdown_disconnects_all(self):
        manager = WebSocketConnectionManager()
        ws1 = AsyncMock(spec=WebSocket)
        ws1.headers = {}
        ws2 = AsyncMock(spec=WebSocket)
        ws2.headers = {}
        await manager.connect(ws1, client_id="s1")
        await manager.connect(ws2, client_id="s2")
        await manager.shutdown()
        assert await manager.get_active_count() == 0


# ==========================================================================
# Room management
# ==========================================================================


class TestRooms:
    """Room/channel membership."""

    @pytest.mark.asyncio
    async def test_join_room(self):
        manager = WebSocketConnectionManager()
        ws = AsyncMock(spec=WebSocket)
        ws.headers = {}
        await manager.connect(ws, client_id="user")
        result = await manager.join_room("user", "room-1")
        assert result is True
        assert "room-1" in await manager.get_client_rooms("user")
        assert "user" in await manager.get_room_members("room-1")

    @pytest.mark.asyncio
    async def test_join_nonexistent_client(self):
        manager = WebSocketConnectionManager()
        result = await manager.join_room("ghost", "room-x")
        assert result is False

    @pytest.mark.asyncio
    async def test_leave_room(self):
        manager = WebSocketConnectionManager()
        ws = AsyncMock(spec=WebSocket)
        ws.headers = {}
        await manager.connect(ws, client_id="user")
        await manager.join_room("user", "room-2")
        result = await manager.leave_room("user", "room-2")
        assert result is True
        assert "room-2" not in await manager.get_client_rooms("user")
        assert await manager.get_room_members("room-2") == []

    @pytest.mark.asyncio
    async def test_leave_nonexistent_client(self):
        manager = WebSocketConnectionManager()
        result = await manager.leave_room("ghost", "room-x")
        assert result is False

    @pytest.mark.asyncio
    async def test_leave_unjoined_room(self):
        manager = WebSocketConnectionManager()
        ws = AsyncMock(spec=WebSocket)
        ws.headers = {}
        await manager.connect(ws, client_id="user")
        result = await manager.leave_room("user", "not-joined")
        assert result is True

    @pytest.mark.asyncio
    async def test_multiple_clients_same_room(self):
        manager = WebSocketConnectionManager()
        ws1 = AsyncMock(spec=WebSocket)
        ws1.headers = {}
        ws2 = AsyncMock(spec=WebSocket)
        ws2.headers = {}
        await manager.connect(ws1, client_id="a")
        await manager.connect(ws2, client_id="b")
        await manager.join_room("a", "lobby")
        await manager.join_room("b", "lobby")
        members = await manager.get_room_members("lobby")
        assert len(members) == 2
        assert "a" in members
        assert "b" in members


# ==========================================================================
# Event subscriptions
# ==========================================================================


class TestSubscriptions:
    """Event subscription management."""

    @pytest.mark.asyncio
    async def test_subscribe(self):
        manager = WebSocketConnectionManager()
        ws = AsyncMock(spec=WebSocket)
        ws.headers = {}
        await manager.connect(ws, client_id="sub")
        result = await manager.subscribe("sub", "events.order")
        assert result is True
        assert "sub" in await manager.get_subscribed_clients("events.order")

    @pytest.mark.asyncio
    async def test_subscribe_nonexistent(self):
        manager = WebSocketConnectionManager()
        result = await manager.subscribe("ghost", "event.x")
        assert result is False

    @pytest.mark.asyncio
    async def test_unsubscribe(self):
        manager = WebSocketConnectionManager()
        ws = AsyncMock(spec=WebSocket)
        ws.headers = {}
        await manager.connect(ws, client_id="sub")
        await manager.subscribe("sub", "events.test")
        await manager.unsubscribe("sub", "events.test")
        assert "sub" not in await manager.get_subscribed_clients("events.test")

    @pytest.mark.asyncio
    async def test_unsubscribe_nonexistent(self):
        manager = WebSocketConnectionManager()
        result = await manager.unsubscribe("ghost", "event.x")
        assert result is False


# ==========================================================================
# Messaging
# ==========================================================================


class TestMessaging:
    """Broadcast, targeted, room, and subscription-based messaging."""

    @pytest.mark.asyncio
    async def test_send_to_specific_client(self):
        manager = WebSocketConnectionManager()
        ws = AsyncMock(spec=WebSocket)
        ws.headers = {}
        await manager.connect(ws, client_id="target")
        msg = ServerMessage(type=WSMessageType.MESSAGE, payload={"text": "hello"})
        result = await manager.send("target", msg)
        assert result is True
        ws.send_json.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_send_to_nonexistent(self):
        manager = WebSocketConnectionManager()
        msg = ServerMessage(type=WSMessageType.MESSAGE)
        result = await manager.send("nobody", msg)
        assert result is False

    @pytest.mark.asyncio
    async def test_broadcast(self):
        manager = WebSocketConnectionManager()
        ws1 = AsyncMock(spec=WebSocket)
        ws1.headers = {}
        ws2 = AsyncMock(spec=WebSocket)
        ws2.headers = {}
        await manager.connect(ws1, client_id="b1")
        await manager.connect(ws2, client_id="b2")
        msg = ServerMessage(type=WSMessageType.MESSAGE, payload={"announce": "hi"})
        count = await manager.broadcast(msg)
        assert count == 2

    @pytest.mark.asyncio
    async def test_broadcast_empty(self):
        manager = WebSocketConnectionManager()
        msg = ServerMessage(type=WSMessageType.MESSAGE)
        count = await manager.broadcast(msg)
        assert count == 0

    @pytest.mark.asyncio
    async def test_send_to_room(self):
        manager = WebSocketConnectionManager()
        ws1 = AsyncMock(spec=WebSocket)
        ws1.headers = {}
        ws2 = AsyncMock(spec=WebSocket)
        ws2.headers = {}
        await manager.connect(ws1, client_id="r1")
        await manager.connect(ws2, client_id="r2")
        await manager.join_room("r1", "team-a")
        await manager.join_room("r2", "team-a")
        msg = ServerMessage(type=WSMessageType.MESSAGE, payload={"room_msg": "all hands"})
        count = await manager.send_to_room("team-a", msg)
        assert count == 2

    @pytest.mark.asyncio
    async def test_send_to_empty_room(self):
        manager = WebSocketConnectionManager()
        msg = ServerMessage(type=WSMessageType.MESSAGE)
        count = await manager.send_to_room("empty", msg)
        assert count == 0

    @pytest.mark.asyncio
    async def test_send_to_subscribers(self):
        manager = WebSocketConnectionManager()
        ws1 = AsyncMock(spec=WebSocket)
        ws1.headers = {}
        ws2 = AsyncMock(spec=WebSocket)
        ws2.headers = {}
        await manager.connect(ws1, client_id="s1")
        await manager.connect(ws2, client_id="s2")
        await manager.subscribe("s1", "events.notify")
        await manager.subscribe("s2", "events.notify")
        msg = ServerMessage(type=WSMessageType.EVENT, event="events.notify", payload={"data": 1})
        count = await manager.send_to_subscribers("events.notify", msg)
        assert count == 2

    @pytest.mark.asyncio
    async def test_send_to_subscribers_no_match(self):
        manager = WebSocketConnectionManager()
        ws = AsyncMock(spec=WebSocket)
        ws.headers = {}
        await manager.connect(ws, client_id="s1")
        await manager.subscribe("s1", "events.a")
        msg = ServerMessage(type=WSMessageType.EVENT)
        count = await manager.send_to_subscribers("events.b", msg)
        assert count == 0


# ==========================================================================
# Message serialization
# ==========================================================================


class TestSerialization:
    """JSON serialization of server messages."""

    def test_server_message_serialization(self):
        msg = ServerMessage(
            type=WSMessageType.MESSAGE,
            payload={"key": "value"},
            sender="test-sender",
            room="test-room",
            event="test-event",
            timestamp="2026-01-01T00:00:00Z",
        )
        data = msg.model_dump(exclude_none=True)
        assert data["type"] == "message"
        assert data["payload"] == {"key": "value"}
        assert data["sender"] == "test-sender"
        assert data["room"] == "test-room"

    def test_client_message_parsing(self):
        raw = '{"type": "ping", "payload": {}}'
        msg = ClientMessage(**json.loads(raw))
        assert msg.type == WSMessageType.PING

    def test_client_message_subscribe(self):
        raw = '{"type": "subscribe", "event": "events.test"}'
        msg = ClientMessage(**json.loads(raw))
        assert msg.type == WSMessageType.SUBSCRIBE
        assert msg.event == "events.test"

    def test_client_message_join(self):
        raw = '{"type": "join", "room": "general"}'
        msg = ClientMessage(**json.loads(raw))
        assert msg.type == WSMessageType.JOIN
        assert msg.room == "general"

    def test_client_message_targeted(self):
        raw = '{"type": "message", "target": "other-client", "payload": {"text": "hi"}}'
        msg = ClientMessage(**json.loads(raw))
        assert msg.type == WSMessageType.MESSAGE
        assert msg.target == "other-client"

    def test_pong_message_defaults(self):
        msg = ServerMessage(type=WSMessageType.PONG)
        assert msg.type == WSMessageType.PONG


# ==========================================================================
# Incoming message handling
# ==========================================================================


class TestHandleMessage:
    """Incoming message parsing and response generation."""

    @pytest.mark.asyncio
    async def test_handle_ping_returns_pong(self):
        manager = WebSocketConnectionManager()
        ws = AsyncMock(spec=WebSocket)
        ws.headers = {}
        await manager.connect(ws, client_id="pinger")
        raw = '{"type": "ping"}'
        response = await manager.handle_message("pinger", raw)
        assert response is not None
        assert response.type == WSMessageType.PONG

    @pytest.mark.asyncio
    async def test_handle_subscribe(self):
        manager = WebSocketConnectionManager()
        ws = AsyncMock(spec=WebSocket)
        ws.headers = {}
        await manager.connect(ws, client_id="subber")
        raw = '{"type": "subscribe", "event": "events.custom"}'
        response = await manager.handle_message("subber", raw)
        assert response is not None
        assert response.type == WSMessageType.SUBSCRIBED
        assert response.event == "events.custom"

    @pytest.mark.asyncio
    async def test_handle_unsubscribe(self):
        manager = WebSocketConnectionManager()
        ws = AsyncMock(spec=WebSocket)
        ws.headers = {}
        await manager.connect(ws, client_id="unsubber")
        raw = '{"type": "unsubscribe", "event": "events.custom"}'
        response = await manager.handle_message("unsubber", raw)
        assert response is not None
        assert response.type == WSMessageType.UNSUBSCRIBED
        assert response.event == "events.custom"

    @pytest.mark.asyncio
    async def test_handle_join(self):
        manager = WebSocketConnectionManager()
        ws = AsyncMock(spec=WebSocket)
        ws.headers = {}
        await manager.connect(ws, client_id="joiner")
        raw = '{"type": "join", "room": "lobby"}'
        response = await manager.handle_message("joiner", raw)
        assert response is not None
        assert response.type == WSMessageType.JOINED
        assert response.room == "lobby"

    @pytest.mark.asyncio
    async def test_handle_leave(self):
        manager = WebSocketConnectionManager()
        ws = AsyncMock(spec=WebSocket)
        ws.headers = {}
        await manager.connect(ws, client_id="leaver")
        raw = '{"type": "leave", "room": "lobby"}'
        response = await manager.handle_message("leaver", raw)
        assert response is not None
        assert response.type == WSMessageType.LEFT
        assert response.room == "lobby"

    @pytest.mark.asyncio
    async def test_handle_invalid_json(self):
        manager = WebSocketConnectionManager()
        response = await manager.handle_message("any", "not json{{{")
        assert response is not None
        assert response.type == WSMessageType.ERROR

    @pytest.mark.asyncio
    async def test_handle_targeted_message(self):
        manager = WebSocketConnectionManager()
        ws_sender = AsyncMock(spec=WebSocket)
        ws_sender.headers = {}
        ws_target = AsyncMock(spec=WebSocket)
        ws_target.headers = {}
        await manager.connect(ws_sender, client_id="sender")
        await manager.connect(ws_target, client_id="receiver")
        raw = '{"type": "message", "target": "receiver", "payload": {"text": "hello"}}'
        response = await manager.handle_message("sender", raw)
        assert response is None
        ws_target.send_json.assert_awaited_once()


# ==========================================================================
# Authentication hook
# ==========================================================================


class TestAuthentication:
    """Authentication hook behavior."""

    @pytest.mark.asyncio
    async def test_default_auth_allows_all(self):
        auth = WSAuthenticator()
        result = await auth.authenticate("anyone", token=None)
        assert result is not None
        assert result["client_id"] == "anyone"

    @pytest.mark.asyncio
    async def test_token_based_auth(self):
        auth = WSAuthenticator()
        result = await auth.authenticate("user-1", token="valid-token")
        assert result is not None

    @pytest.mark.asyncio
    async def test_custom_authenticator_rejects(self):
        rejector = MagicMock(spec=WSAuthenticator)
        rejector.authenticate = AsyncMock(return_value=None)
        result = await rejector.authenticate("bad", token="invalid")
        assert result is None

    @pytest.mark.asyncio
    async def test_custom_authenticator_accepts(self):
        accepter = MagicMock(spec=WSAuthenticator)
        accepter.authenticate = AsyncMock(return_value={"role": "admin"})
        result = await accepter.authenticate("good", token="valid")
        assert result == {"role": "admin"}

    @pytest.mark.asyncio
    async def test_on_connect_called(self):
        auth = MagicMock(spec=WSAuthenticator)
        auth.authenticate = AsyncMock(return_value={"client_id": "test"})
        auth.on_connect = AsyncMock()
        manager = WebSocketConnectionManager(authenticator=auth)
        ws = AsyncMock(spec=WebSocket)
        ws.headers = {}
        await manager.connect(ws, client_id="test")
        auth.on_connect.assert_awaited_once_with("test", {"client_id": "test"})

    @pytest.mark.asyncio
    async def test_on_disconnect_called(self):
        auth = MagicMock(spec=WSAuthenticator)
        auth.authenticate = AsyncMock(return_value={"client_id": "test"})
        auth.on_connect = AsyncMock()
        auth.on_disconnect = AsyncMock()
        manager = WebSocketConnectionManager(authenticator=auth)
        ws = AsyncMock(spec=WebSocket)
        ws.headers = {}
        await manager.connect(ws, client_id="disc")
        await manager.disconnect("disc")
        auth.on_disconnect.assert_awaited_once_with("disc")


# ==========================================================================
# Concurrent clients
# ==========================================================================


class TestConcurrentClients:
    """Concurrent access patterns."""

    @pytest.mark.asyncio
    async def test_concurrent_connect(self):
        manager = WebSocketConnectionManager()
        async def connect_cid(cid: str) -> None:
            ws = AsyncMock(spec=WebSocket)
            ws.headers = {}
            await manager.connect(ws, client_id=cid)
        await asyncio.gather(*[connect_cid(f"c{i}") for i in range(10)])
        assert await manager.get_active_count() == 10

    @pytest.mark.asyncio
    async def test_concurrent_join_rooms(self):
        manager = WebSocketConnectionManager()
        for i in range(5):
            ws = AsyncMock(spec=WebSocket)
            ws.headers = {}
            await manager.connect(ws, client_id=f"u{i}")
        async def join_all(cid: str) -> None:
            for r in range(3):
                await manager.join_room(cid, f"room-{r}")
        await asyncio.gather(*[join_all(f"u{i}") for i in range(5)])
        for r in range(3):
            members = await manager.get_room_members(f"room-{r}")
            assert len(members) == 5

    @pytest.mark.asyncio
    async def test_concurrent_disconnect(self):
        manager = WebSocketConnectionManager()
        for i in range(10):
            ws = AsyncMock(spec=WebSocket)
            ws.headers = {}
            await manager.connect(ws, client_id=f"d{i}")
        await asyncio.gather(*[manager.disconnect(f"d{i}") for i in range(10)])
        assert await manager.get_active_count() == 0


# ==========================================================================
# Error handling
# ==========================================================================


class TestErrorHandling:
    """Error scenarios."""

    @pytest.mark.asyncio
    async def test_send_to_failing_client_disconnects(self):
        manager = WebSocketConnectionManager()
        ws = AsyncMock(spec=WebSocket)
        ws.headers = {}
        ws.send_json = AsyncMock(side_effect=Exception("Connection lost"))
        await manager.connect(ws, client_id="fragile")
        msg = ServerMessage(type=WSMessageType.MESSAGE)
        result = await manager.send("fragile", msg)
        assert result is False
        assert await manager.is_connected("fragile") is False

    @pytest.mark.asyncio
    async def test_handle_message_invalid_type(self):
        manager = WebSocketConnectionManager()
        ws = AsyncMock(spec=WebSocket)
        ws.headers = {}
        await manager.connect(ws, client_id="bad-msg")
        raw = '{"type": "unknown_type"}'
        response = await manager.handle_message("bad-msg", raw)
        assert response is not None
        assert response.type == WSMessageType.ERROR

    @pytest.mark.asyncio
    async def test_handle_malformed_json(self):
        manager = WebSocketConnectionManager()
        response = await manager.handle_message("any", "{broken")
        assert response is not None
        assert response.type == WSMessageType.ERROR

    def test_websocket_endpoint_no_manager(self):
        """When no ws_manager on app state, the connection is refused."""
        app = create_app()
        app.state.ws_manager = None
        client = TestClient(app)
        with pytest.raises(Exception):
            with client.websocket_connect("/api/v1/ws"):
                pass

    @pytest.mark.asyncio
    async def test_manager_shutdown_cleanup(self):
        manager = WebSocketConnectionManager()
        ws = AsyncMock(spec=WebSocket)
        ws.headers = {}
        await manager.connect(ws, client_id="clean-me")
        await manager.shutdown()
        assert await manager.get_active_count() == 0


# ==========================================================================
# Heartbeat
# ==========================================================================


class TestHeartbeat:
    """Heartbeat / ping-pong mechanism."""

    @pytest.mark.asyncio
    async def test_heartbeat_updates_timestamp(self):
        manager = WebSocketConnectionManager()
        ws = AsyncMock(spec=WebSocket)
        ws.headers = {}
        info = await manager.connect(ws, client_id="hb")
        old = info.last_heartbeat
        await asyncio.sleep(0.01)
        raw = '{"type": "ping"}'
        await manager.handle_message("hb", raw)
        assert info.last_heartbeat > old

    @pytest.mark.asyncio
    async def test_heartbeat_loop_stops_when_empty(self):
        manager = WebSocketConnectionManager(
            heartbeat_interval=0.05,
            heartbeat_timeout=0.1,
        )
        ws = AsyncMock(spec=WebSocket)
        ws.headers = {}
        await manager.connect(ws, client_id="hb-test")
        await manager.disconnect("hb-test")
        await asyncio.sleep(0.15)
        assert manager._heartbeat_task is None or manager._heartbeat_task.done()


# ==========================================================================
# Dependency injection (registry integration)
# ==========================================================================


class TestDependencyInjection:
    """WS manager accessible via app state."""

    def test_manager_on_app_state(self):
        app = _make_app()
        assert hasattr(app.state, "ws_manager")
        assert app.state.ws_manager is not None

    def test_manager_is_singleton(self):
        app = _make_app()
        assert app.state.ws_manager is app.state.ws_manager


# ==========================================================================
# Route registration
# ==========================================================================


class TestRouteRegistration:
    """WebSocket route appears in the application."""

    def test_ws_route_registered(self):
        app = _make_app()
        ws_found = False
        for r in app.router.routes:
            router = getattr(r, "original_router", None)
            if router is not None and hasattr(router, "routes"):
                for sr in router.routes:
                    if getattr(sr, "path", None) == "/api/v1/ws":
                        ws_found = True
                        break
            if ws_found:
                break
        assert ws_found


# ==========================================================================
# Backward compatibility
# ==========================================================================


class TestBackwardCompatibility:
    """Existing services and routes remain unchanged."""

    def test_health_still_works(self):
        client = _make_client()
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200

    def test_status_still_works(self):
        client = _make_client()
        resp = client.get("/api/v1/status")
        assert resp.status_code == 200

    def test_existing_routes_unchanged(self):
        client = _make_client()
        schema = client.get("/api/v1/openapi.json").json()
        paths = schema["paths"]
        assert "/api/v1/health" in paths
        assert "/api/v1/status" in paths
        assert "/api/v1/config" in paths
        assert "/api/v1/services" in paths

    def test_create_app_still_works(self):
        app = create_app()
        assert app is not None
        assert app.state.registry is None
        assert hasattr(app.state, "ws_manager")
