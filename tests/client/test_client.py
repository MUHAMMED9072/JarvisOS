"""Tests for JarvisClient lifecycle and high-level operations."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.client.client import JarvisClient
from app.client.models import AuthState, ConnectionStatus, HealthCheck, MetricsSnapshot


class TestJarvisClientInit:
    def test_default_construction(self):
        client = JarvisClient()
        assert client._api_url == "http://localhost:8000"
        assert client._ws_url == "ws://localhost:8000/api/v1/ws"
        assert client._api_key is None
        assert client._bearer_token is None
        assert client.state.connection_status == ConnectionStatus.DISCONNECTED

    def test_custom_construction(self):
        client = JarvisClient(
            api_url="https://example.com",
            ws_url="wss://example.com/ws",
            api_key="test-key",
            timeout=15.0,
            retry_count=5,
            heartbeat_interval=10.0,
            auto_reconnect=False,
        )
        assert client._api_url == "https://example.com"
        assert client._ws_url == "wss://example.com/ws"
        assert client._api_key == "test-key"
        assert client.rest._timeout == 15.0
        assert client.rest._retry_count == 5
        assert client.ws._heartbeat_interval == 10.0
        assert client.ws._auto_reconnect is False

    def test_sub_clients_created(self):
        client = JarvisClient()
        assert hasattr(client, "rest")
        assert hasattr(client, "ws")
        assert hasattr(client, "state")


class TestJarvisClientConnect:
    @pytest.mark.asyncio
    async def test_connect_failure_no_server(self):
        client = JarvisClient()
        result = await client.connect()
        assert result is False
        assert client.state.connection_status == ConnectionStatus.DISCONNECTED


class TestJarvisClientStateManagement:
    def test_state_initial_values(self):
        client = JarvisClient()
        s = client.state
        assert s.connection_status == ConnectionStatus.DISCONNECTED
        assert s.auth_state == AuthState.NONE

    @pytest.mark.asyncio
    async def test_authenticate_updates_state(self):
        client = JarvisClient()
        with patch.object(client.ws, "authenticate", AsyncMock(return_value=True)):
            ok = await client.authenticate("test-token")
            assert ok is True
            assert client.state.auth_state == AuthState.AUTHENTICATED

    @pytest.mark.asyncio
    async def test_authenticate_failure(self):
        client = JarvisClient()
        with patch.object(client.ws, "authenticate", AsyncMock(return_value=False)):
            ok = await client.authenticate("bad-token")
            assert ok is False
            assert client.state.auth_state == AuthState.FAILED

    @pytest.mark.asyncio
    async def test_authenticate_sets_session_id(self):
        client = JarvisClient()
        client.ws._session_id = "sess-123"
        with patch.object(client.ws, "authenticate", AsyncMock(return_value=True)):
            await client.authenticate("tok")
            assert client.state.session_id == "sess-123"


class TestJarvisClientSubscriptions:
    @pytest.mark.asyncio
    async def test_subscribe_delegates(self):
        client = JarvisClient()
        with patch.object(client.ws, "subscribe", AsyncMock()) as mock_sub:
            await client.subscribe("ai.*")
            mock_sub.assert_called_once_with("ai.*")

    @pytest.mark.asyncio
    async def test_unsubscribe_delegates(self):
        client = JarvisClient()
        with patch.object(client.ws, "unsubscribe", AsyncMock()) as mock_unsub:
            await client.unsubscribe("ai.*")
            mock_unsub.assert_called_once_with("ai.*")

    def test_on_delegates(self):
        client = JarvisClient()

        def handler(event, **data):
            pass

        with patch.object(client.ws, "on") as mock_on:
            client.on("test.event", handler)
            mock_on.assert_called_once_with("test.event", handler)

    def test_off_delegates(self):
        client = JarvisClient()

        def handler(event, **data):
            pass

        with patch.object(client.ws, "off") as mock_off:
            client.off("test.event", handler)
            mock_off.assert_called_once_with("test.event", handler)


class TestJarvisClientRestDelegation:
    @pytest.mark.asyncio
    async def test_fetch_metrics(self):
        client = JarvisClient()
        with patch.object(client.rest, "get_ws_metrics", AsyncMock(
            return_value={"active_connections": 3, "bytes_sent": 100},
        )):
            metrics = await client.fetch_metrics()
            assert isinstance(metrics, MetricsSnapshot)
            assert metrics.active_connections == 3
            assert client.state.metrics.active_connections == 3

    @pytest.mark.asyncio
    async def test_fetch_health(self):
        client = JarvisClient()
        with patch.object(client.rest, "get_ws_health", AsyncMock(
            return_value={"status": "degraded", "failures": ["high_latency"]},
        )):
            hc = await client.fetch_health()
            assert hc.status == "degraded"
            assert "high_latency" in hc.failures
            assert client.state.health.status == "degraded"

    @pytest.mark.asyncio
    async def test_fetch_diagnostics(self):
        client = JarvisClient()
        with patch.object(client.rest, "get_ws_diagnostics", AsyncMock(
            return_value={"manager": {"active_connections": 5}},
        )):
            report = await client.fetch_diagnostics()
            assert report.manager["active_connections"] == 5

    @pytest.mark.asyncio
    async def test_health_check_success(self):
        client = JarvisClient()
        with patch.object(client.rest, "health", AsyncMock(
            return_value={"status": "healthy"},
        )):
            result = await client.health_check()
            assert result["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_health_check_failure(self):
        client = JarvisClient()
        with patch.object(client.rest, "health", AsyncMock(side_effect=Exception("down"))):
            with pytest.raises(Exception, match="down"):
                await client.health_check()


class TestJarvisClientEvents:
    @pytest.mark.asyncio
    async def test_ws_events_update_state(self):
        client = JarvisClient()
        # Wire events manually (normally done in connect())
        client._wire_events()
        # Simulate WS events
        client.ws.events.publish("connection.opened")
        assert client.state.connection_status == ConnectionStatus.CONNECTED

        client.ws.events.publish("connection.closed")
        assert client.state.connection_status == ConnectionStatus.DISCONNECTED

        client.ws.events.publish("connection.reconnecting")
        assert client.state.connection_status == ConnectionStatus.RECONNECTING

        client.ws.events.publish("connection.reconnected", count=3)
        assert client.state.connection_status == ConnectionStatus.CONNECTED
        assert client.state.reconnect_count == 3


class TestJarvisClientShutdown:
    @pytest.mark.asyncio
    async def test_shutdown_resets_state(self):
        client = JarvisClient()
        client.state.connection_status = ConnectionStatus.CONNECTED
        client.state.auth_state = AuthState.AUTHENTICATED
        client.state.session_id = "sess-1"

        with patch.object(client.ws, "disconnect", AsyncMock()):
            with patch.object(client.rest, "stop", AsyncMock()):
                await client.shutdown()

        assert client.state.connection_status == ConnectionStatus.DISCONNECTED
        assert client.state.auth_state == AuthState.NONE
        assert client.state.session_id is None


class TestJarvisClientBackwardCompatibility:
    def test_client_does_not_access_server_internals(self):
        """Verify the client only depends on external communication."""
        import inspect
        from app.client import client

        src = inspect.getsource(client)
        # The client should never import server internals
        assert "ServiceRegistry" not in src
        assert "EventBus" not in src
        assert "Kernel" not in src
        assert "WebSocketConnectionManager" not in src

    def test_client_only_uses_rest_and_ws(self):
        from app.client.client import JarvisClient
        client = JarvisClient()
        # The client's communication paths are only through rest and ws
        assert hasattr(client, "rest")
        assert hasattr(client, "ws")
        # No direct server access
        assert not hasattr(client, "registry")
        assert not hasattr(client, "event_bus")
        assert not hasattr(client, "kernel")
