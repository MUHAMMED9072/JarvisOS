from __future__ import annotations

import asyncio
import time
from typing import Any, Callable

from app.client.api import RestClient
from app.client.models import (
    AuthState,
    ConnectionStatus,
    DiagnosticsReport,
    HealthCheck,
    MetricsSnapshot,
    PluginInfo,
    ServerInfo,
    SkillInfo,
    VoiceStatus,
)
from app.client.state import ClientState
from app.client.websocket import WebSocketClient


class JarvisClient:
    """Production desktop client for JARVIS OS.

    Combines REST and WebSocket clients with centralized state
    management and a clean lifecycle. Communicates only through
    the server's REST API and WebSocket endpoint — never accesses
    server internals.
    """

    def __init__(
        self,
        api_url: str = "http://localhost:8000",
        ws_url: str = "ws://localhost:8000/api/v1/ws",
        api_key: str | None = None,
        bearer_token: str | None = None,
        timeout: float = 30.0,
        retry_count: int = 3,
        heartbeat_interval: float = 30.0,
        auto_reconnect: bool = True,
    ) -> None:
        self._api_url = api_url
        self._ws_url = ws_url
        self._api_key = api_key
        self._bearer_token = bearer_token

        self.state = ClientState()

        self.rest = RestClient(
            base_url=api_url,
            timeout=timeout,
            retry_count=retry_count,
            api_key=api_key,
            bearer_token=bearer_token,
        )

        self.ws = WebSocketClient(
            url=ws_url,
            api_key=api_key,
            bearer_token=bearer_token,
            heartbeat_interval=heartbeat_interval,
            auto_reconnect=auto_reconnect,
        )

        self._health_task: asyncio.Task[None] | None = None
        self._started = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> bool:
        """Connect to the JARVIS server via REST and WebSocket.

        Returns ``True`` if both connections succeeded.
        """
        self.state.connection_status = ConnectionStatus.CONNECTING

        try:
            await self.rest.start()

            # Verify connectivity
            try:
                health_data = await self.rest.health()
                self.state.connection_status = ConnectionStatus.CONNECTED
            except Exception:
                self.state.connection_status = ConnectionStatus.DISCONNECTED
                return False

            # Connect WebSocket
            cid = await self.ws.connect()
            if cid is not None:
                self.state.client_id = cid
                self.state.connection_status = ConnectionStatus.CONNECTED
            else:
                self.state.connection_status = ConnectionStatus.DISCONNECTED
                return False

            # Wire WS events to state
            self._wire_events()

            self._started = True

            # Fetch initial data
            await self._refresh_state()

            return True
        except Exception:
            self.state.connection_status = ConnectionStatus.DISCONNECTED
            await self._cleanup()
            return False

    async def disconnect(self) -> None:
        """Disconnect from the server."""
        self.state.connection_status = ConnectionStatus.DISCONNECTING
        await self.ws.disconnect()
        await self.rest.stop()
        self.state.connection_status = ConnectionStatus.DISCONNECTED
        self.state.auth_state = AuthState.NONE
        self._started = False

    async def shutdown(self) -> None:
        """Full shutdown — disconnect and clear all state."""
        await self.disconnect()
        if self._health_task is not None:
            self._health_task.cancel()
            try:
                await self._health_task
            except asyncio.CancelledError:
                pass
            self._health_task = None
        self.state.reset()

    async def reconnect(self) -> bool:
        """Disconnect and reconnect."""
        await self.disconnect()
        return await self.connect()

    async def health_check(self) -> dict[str, Any]:
        """Perform a health check against the server."""
        try:
            data = await self.rest.health()
            health_check = HealthCheck(
                status=data.get("status", "unknown"),
                timestamp=time.time(),
            )
            self.state.health = health_check
            return data
        except Exception as exc:
            self.state.health = HealthCheck(status="unhealthy", timestamp=time.time())
            raise

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _wire_events(self) -> None:
        """Connect WebSocket events to state updates."""
        self.ws.events.subscribe("connection.opened", self._on_ws_opened)
        self.ws.events.subscribe("connection.closed", self._on_ws_closed)
        self.ws.events.subscribe("connection.reconnecting", self._on_ws_reconnecting)
        self.ws.events.subscribe("connection.reconnected", self._on_ws_reconnected)
        self.ws.events.subscribe("connection.error", self._on_ws_error)

    def _on_ws_opened(self, event: str, **data: Any) -> None:
        self.state.connection_status = ConnectionStatus.CONNECTED

    def _on_ws_closed(self, event: str, **data: Any) -> None:
        self.state.connection_status = ConnectionStatus.DISCONNECTED

    def _on_ws_reconnecting(self, event: str, **data: Any) -> None:
        self.state.connection_status = ConnectionStatus.RECONNECTING

    def _on_ws_reconnected(self, event: str, **data: Any) -> None:
        self.state.connection_status = ConnectionStatus.CONNECTED
        self.state.reconnect_count = data.get("count", 0)

    def _on_ws_error(self, event: str, **data: Any) -> None:
        pass

    async def _refresh_state(self) -> None:
        """Fetch initial server state after connecting."""
        try:
            status_data = await self.rest.status()
            self.state._server_info = ServerInfo(
                app_name=status_data.get("app_name", ""),
                version=status_data.get("version", ""),
            )
        except Exception:
            pass

        try:
            plugins_data = await self.rest.list_plugins()
            self.state._plugins = [
                PluginInfo(**p) for p in plugins_data
            ]
        except Exception:
            pass

    async def _cleanup(self) -> None:
        await self.rest.stop()
        await self.ws.disconnect()

    # ------------------------------------------------------------------
    # High-level operations
    # ------------------------------------------------------------------

    async def authenticate(self, token: str) -> bool:
        """Authenticate with the server using a token."""
        ok = await self.ws.authenticate(token)
        self.state.auth_state = AuthState.AUTHENTICATED if ok else AuthState.FAILED
        if ok:
            self.state.session_id = self.ws.session_id
        return ok

    async def subscribe(self, event: str) -> None:
        """Subscribe to a server event type."""
        await self.ws.subscribe(event)

    async def unsubscribe(self, event: str) -> None:
        await self.ws.unsubscribe(event)

    def on(self, event: str, callback: Callable[..., None]) -> None:
        """Register a callback for a WebSocket event."""
        self.ws.on(event, callback)

    def off(self, event: str, callback: Callable[..., None]) -> None:
        self.ws.off(event, callback)

    async def fetch_metrics(self) -> MetricsSnapshot:
        data = await self.rest.get_ws_metrics()
        metrics = MetricsSnapshot.from_dict(data)
        self.state.metrics = metrics
        return metrics

    async def fetch_health(self) -> HealthCheck:
        data = await self.rest.get_ws_health()
        hc = HealthCheck(
            status=data.get("status", "healthy"),
            checks=data.get("checks", {}),
            failures=data.get("failures", []),
            warnings=data.get("warnings", []),
            timestamp=data.get("timestamp", 0),
        )
        self.state.health = hc
        return hc

    async def fetch_diagnostics(self) -> DiagnosticsReport:
        data = await self.rest.get_ws_diagnostics()
        report = DiagnosticsReport(
            manager=data.get("manager", {}),
            sessions=data.get("sessions", {}),
            retry_queues=data.get("retry_queues", {}),
            offline_queues=data.get("offline_queues", {}),
            heartbeat=data.get("heartbeat", {}),
            rooms=data.get("rooms", {}),
            subscriptions=data.get("subscriptions", {}),
            active_streams=data.get("active_streams", {}),
            commands=data.get("commands", []),
            transfers=data.get("transfers", []),
            auth_stats=data.get("auth_stats", {}),
            metrics=data.get("metrics", {}),
            runtime_config=data.get("runtime_config", {}),
            timestamp=data.get("timestamp", 0),
        )
        self.state.diagnostics = report
        return report
