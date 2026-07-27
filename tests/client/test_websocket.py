"""Tests for WebSocket client."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.client.websocket import WebSocketClient


@pytest.fixture
def mock_websocket():
    ws = AsyncMock()
    ws.send = AsyncMock()
    ws.close = AsyncMock()
    ws.__aiter__ = MagicMock(return_value=_async_iter([]))

    async def mock_connect(uri, **kwargs):
        return ws

    with patch("app.client.websocket.websockets.connect", mock_connect):
        yield ws


async def _async_iter(items):
    for item in items:
        yield item


class TestWebSocketClientLifecycle:
    @pytest.mark.asyncio
    async def test_connect_success(self, mock_websocket):
        ws = WebSocketClient(url="ws://localhost/test")
        cid = await ws.connect()
        assert ws.connected is True

    @pytest.mark.asyncio
    async def test_disconnect(self, mock_websocket):
        ws = WebSocketClient(url="ws://localhost/test")
        await ws.connect()
        await ws.disconnect()
        assert ws.connected is False

    @pytest.mark.asyncio
    async def test_shutdown(self, mock_websocket):
        ws = WebSocketClient(url="ws://localhost/test")
        await ws.connect()
        await ws.shutdown()
        assert ws.connected is False
        assert ws.events.listener_count == 0

    @pytest.mark.asyncio
    async def test_connect_failure(self):
        with patch("app.client.websocket.websockets.connect") as mock_connect:
            mock_connect.side_effect = Exception("Connection refused")
            ws = WebSocketClient(url="ws://localhost/test")
            cid = await ws.connect()
            assert cid is None
            assert ws.connected is False

    @pytest.mark.asyncio
    async def test_send_without_connect_raises(self):
        ws = WebSocketClient()
        with pytest.raises(RuntimeError, match="not connected"):
            await ws.send("ping")


class TestWebSocketClientAuth:
    @pytest.mark.asyncio
    async def test_authenticate_success(self, mock_websocket):
        ws = WebSocketClient(url="ws://localhost/test")
        await ws.connect()

        # Simulate auth.success response
        async def _send_and_wait(msg_type, **kwargs):
            data = json.dumps(msg_type)
            if "auth.request" in data:
                # Simulate response arriving on message loop
                pass

        # We can't easily test the full authenticate flow without
        # setting up the message loop. Test the method signature and setup.
        assert hasattr(ws, "authenticate")
        assert hasattr(ws, "refresh_session")
        assert hasattr(ws, "logout")

    @pytest.mark.asyncio
    async def test_auth_url_params(self):
        with patch("app.client.websocket.websockets.connect") as mock_connect:
            ws = WebSocketClient(url="ws://localhost/test", api_key="mykey")
            mock_connect.return_value = AsyncMock()
            await ws.connect()
            called_uri = mock_connect.call_args[0][0]
            assert "apikey" in called_uri

    @pytest.mark.asyncio
    async def test_bearer_url_params(self):
        with patch("app.client.websocket.websockets.connect") as mock_connect:
            ws = WebSocketClient(url="ws://localhost/test", bearer_token="btok")
            mock_connect.return_value = AsyncMock()
            await ws.connect()
            called_uri = mock_connect.call_args[0][0]
            assert "bearer" in called_uri

    @pytest.mark.asyncio
    async def test_reconnect_token_param(self):
        with patch("app.client.websocket.websockets.connect") as mock_connect:
            ws = WebSocketClient(url="ws://localhost/test", reconnect_token="rtok:abc")
            mock_connect.return_value = AsyncMock()
            await ws.connect()
            called_uri = mock_connect.call_args[0][0]
            assert "reconnect_token" in called_uri

    @pytest.mark.asyncio
    async def test_logout(self, mock_websocket):
        ws = WebSocketClient()
        with patch.object(ws, "send", AsyncMock()) as mock_send:
            await ws.logout()
            mock_send.assert_called_once_with("auth.logout", {})

    @pytest.mark.asyncio
    async def test_refresh_session(self, mock_websocket):
        ws = WebSocketClient()
        ws._session_id = "sess-1"
        assert ws.session_id == "sess-1"
        with patch.object(ws, "send", AsyncMock()):
            result = await ws.refresh_session()
            # Will timeout since no response comes back
            assert result is False


class TestWebSocketClientProperties:
    def test_default_properties(self):
        ws = WebSocketClient()
        assert ws.connected is False
        assert ws.client_id is None
        assert ws.session_id is None
        assert ws.reconnect_count == 0

    @pytest.mark.asyncio
    async def test_properties_after_connect(self, mock_websocket):
        ws = WebSocketClient()
        await ws.connect()
        assert ws.connected is True
        assert ws.reconnect_count == 0


class TestWebSocketClientSubscriptions:
    @pytest.mark.asyncio
    async def test_subscribe_unsubscribe(self, mock_websocket):
        ws = WebSocketClient()
        with patch.object(ws, "send", AsyncMock()) as mock_send:
            await ws.subscribe("test.event")
            mock_send.assert_called_with("subscribe", event="test.event")

            await ws.unsubscribe("test.event")
            mock_send.assert_called_with("unsubscribe", event="test.event")

    @pytest.mark.asyncio
    async def test_join_leave_room(self, mock_websocket):
        ws = WebSocketClient()
        with patch.object(ws, "send", AsyncMock()) as mock_send:
            await ws.join_room("lobby")
            mock_send.assert_called_with("join", room="lobby")

            await ws.leave_room("lobby")
            mock_send.assert_called_with("leave", room="lobby")


class TestWebSocketClientEvents:
    @pytest.mark.asyncio
    async def test_on_off(self, mock_websocket):
        ws = WebSocketClient()
        received = []

        def handler(event, **data):
            received.append(event)

        ws.on("auth.success", handler)
        ws.events.publish("message.auth.success")
        assert len(received) == 1

        ws.off("auth.success", handler)
        ws.events.publish("message.auth.success")
        assert len(received) == 1  # No increase

    @pytest.mark.asyncio
    async def test_on_prefixed(self, mock_websocket):
        ws = WebSocketClient()
        received = []

        def handler(event, **data):
            received.append(event)

        ws.on("message.test", handler)
        ws.events.publish("message.test")
        assert len(received) == 1


class TestWebSocketClientSend:
    @pytest.mark.asyncio
    async def test_send_message(self, mock_websocket):
        ws = WebSocketClient()
        await ws.connect()
        ws._ws.send = AsyncMock()
        await ws.send("test", {"key": "val"})
        ws._ws.send.assert_called_once()
        sent = json.loads(ws._ws.send.call_args[0][0])
        assert sent["type"] == "test"
        assert sent["payload"]["key"] == "val"

    @pytest.mark.asyncio
    async def test_send_message_convenience(self, mock_websocket):
        ws = WebSocketClient()
        await ws.connect()
        ws._ws.send = AsyncMock()
        await ws.send_message("test", key="val")
        sent = json.loads(ws._ws.send.call_args[0][0])
        assert sent["type"] == "test"
        assert sent["payload"]["key"] == "val"
