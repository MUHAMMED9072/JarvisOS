from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError

from app.api.errors import (
    APIException,
    api_exception_handler,
    general_exception_handler,
    validation_exception_handler,
)
from app.api.middleware import register_middleware
from app.api.routes import register_routes
from app.core.registry import ServiceRegistry
from app.monitor.service import SystemMonitorService
from app.ws.admin import AdminManager
from app.ws.ai_stream import AIStreamManager
from app.ws.auth import WSAuthenticator
from app.ws.bridge import EventStreamBridge
from app.ws.commands import CommandExecutionManager
from app.ws.diagnostics import WebSocketDiagnostics
from app.ws.file_transfer import FileTransferManager
from app.ws.health import WebSocketHealthMonitor
from app.ws.maintenance import WebSocketMaintenance
from app.ws.manager import WebSocketConnectionManager
from app.ws.metrics import WebsocketMetricsService
from app.ws.runtime_config import WebSocketRuntimeConfig
from app.ws.session import SessionStore


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan: start health monitor, yield, then clean up."""
    monitor: SystemMonitorService | None = getattr(app.state, "system_monitor", None)
    if monitor is not None:
        monitor.start()
    ws_health: WebSocketHealthMonitor | None = getattr(app.state, "ws_health", None)
    if ws_health is not None:
        await ws_health.start()
    yield
    if ws_health is not None:
        await ws_health.stop()
    if monitor is not None:
        await monitor.stop()
    bridge: EventStreamBridge | None = getattr(app.state, "ws_bridge", None)
    if bridge is not None:
        bridge.stop()
    ws_mgr: WebSocketConnectionManager | None = getattr(app.state, "ws_manager", None)
    if ws_mgr is not None:
        await ws_mgr.shutdown()


def create_app(
    registry: Any = None,
    *,
    title: str = "JARVIS OS API",
    version: str = "0.4.0",
) -> FastAPI:
    """Create and configure the FastAPI application.

    Parameters
    ----------
    registry:
        An optional ServiceRegistry instance. When provided, the
        registry is attached to ``app.state`` so route handlers can
        resolve services via dependency injection.
    title:
        OpenAPI title.
    version:
        OpenAPI version string.
    """
    app = FastAPI(
        title=title,
        version=version,
        docs_url="/api/v1/docs",
        redoc_url="/api/v1/redoc",
        openapi_url="/api/v1/openapi.json",
        lifespan=_lifespan,
    )

    app.state.registry = registry

    _init_ws_authenticator(app)
    _init_event_stream_bridge(app)
    _init_ai_stream_manager(app)
    _init_command_execution_manager(app)
    _init_file_transfer_manager(app)
    _init_system_monitor(app)
    _init_ws_observability(app)
    _init_admin_manager(app)

    register_routes(app)
    register_middleware(app)
    _register_error_handlers(app)

    return app


def _init_ws_authenticator(app: FastAPI) -> None:
    from app.core.config import Config

    registry: ServiceRegistry | None = getattr(app.state, "registry", None)
    event_bus = registry.get_optional("event_bus") if registry else None
    session_store = SessionStore(session_expiry=Config.WS_SESSION_EXPIRY)

    authenticator = WSAuthenticator(
        session_store=session_store,
        event_bus=event_bus,
        config=Config,
    )
    app.state.ws_authenticator = authenticator

    app.state.ws_manager = WebSocketConnectionManager(
        authenticator=authenticator,
    )


def _init_event_stream_bridge(app: FastAPI) -> None:
    """Create and start the EventBus → WebSocket bridge if possible."""
    registry: ServiceRegistry | None = getattr(app.state, "registry", None)
    if registry is None:
        return
    event_bus = registry.get_optional("event_bus")
    if event_bus is None:
        return
    bridge = EventStreamBridge(
        event_bus=event_bus,
        ws_manager=app.state.ws_manager,
    )
    bridge.start()
    app.state.ws_bridge = bridge


def _init_command_execution_manager(app: FastAPI) -> None:
    """Create the remote command execution manager."""
    registry: ServiceRegistry | None = getattr(app.state, "registry", None)
    if registry is None:
        return
    mgr = CommandExecutionManager(
        ws_manager=app.state.ws_manager,
        registry=registry,
    )
    app.state.command_execution_manager = mgr


def _init_ws_observability(app: FastAPI) -> None:
    """Create metrics, health, diagnostics, maintenance, and runtime config."""
    from app.core.config import Config

    ws_mgr = app.state.ws_manager
    registry: ServiceRegistry | None = getattr(app.state, "registry", None)
    event_bus = registry.get_optional("event_bus") if registry else None
    authenticator = app.state.ws_authenticator

    metrics = WebsocketMetricsService(ws_manager=ws_mgr, event_bus=event_bus)
    app.state.ws_metrics = metrics

    health = WebSocketHealthMonitor(
        ws_manager=ws_mgr,
        metrics_service=metrics,
        event_bus=event_bus,
        interval=Config.WS_HEALTH_INTERVAL,
    )
    app.state.ws_health = health

    session_store = getattr(authenticator, "_session_store", None)

    runtime_config = WebSocketRuntimeConfig(ws_manager=ws_mgr, config=Config)
    app.state.ws_runtime_config = runtime_config

    diagnostics = WebSocketDiagnostics(
        ws_manager=ws_mgr,
        session_store=session_store,
        authenticator=authenticator,
        metrics_service=metrics,
        health_monitor=health,
        runtime_config=runtime_config,
    )
    app.state.ws_diagnostics = diagnostics

    maintenance = WebSocketMaintenance(
        ws_manager=ws_mgr,
        session_store=session_store,
        authenticator=authenticator,
        metrics_service=metrics,
        runtime_config=runtime_config,
        event_bus=event_bus,
    )
    app.state.ws_maintenance = maintenance


def _init_admin_manager(app: FastAPI) -> None:
    """Create the remote administration manager."""
    registry: ServiceRegistry | None = getattr(app.state, "registry", None)
    if registry is None:
        return
    kernel = registry.get_optional("kernel")
    monitor: SystemMonitorService | None = getattr(app.state, "system_monitor", None)
    mgr = AdminManager(
        ws_manager=app.state.ws_manager,
        registry=registry,
        kernel=kernel,
        system_monitor=monitor,
        ws_metrics=getattr(app.state, "ws_metrics", None),
        ws_health=getattr(app.state, "ws_health", None),
        ws_diagnostics=getattr(app.state, "ws_diagnostics", None),
        ws_maintenance=getattr(app.state, "ws_maintenance", None),
        ws_runtime_config=getattr(app.state, "ws_runtime_config", None),
    )
    app.state.admin_manager = mgr


def _init_file_transfer_manager(app: FastAPI) -> None:
    """Create the remote file transfer manager."""
    from app.core.config import Config

    mgr = FileTransferManager(
        ws_manager=app.state.ws_manager,
        upload_dir=str(Config.FILE_DIR),
        download_dir=str(Config.FILE_DIR),
        max_file_size=Config.MAX_FILE_SIZE,
        chunk_size=Config.CHUNK_SIZE,
    )
    app.state.file_transfer_manager = mgr


def _init_ai_stream_manager(app: FastAPI) -> None:
    """Create the AI stream manager if ``ai_manager`` is available."""
    registry: ServiceRegistry | None = getattr(app.state, "registry", None)
    if registry is None:
        return
    ai_manager = registry.get_optional("ai_manager")
    if ai_manager is None:
        return
    mgr = AIStreamManager(
        ai_manager=ai_manager,
        ws_manager=app.state.ws_manager,
    )
    app.state.ai_stream_manager = mgr


def _init_system_monitor(app: FastAPI) -> None:
    """Create and start the system monitor if the event bus is available."""
    registry: ServiceRegistry | None = getattr(app.state, "registry", None)
    if registry is None:
        return
    event_bus = registry.get_optional("event_bus")
    if event_bus is None:
        return
    monitor = SystemMonitorService(
        registry=registry,
        event_bus=event_bus,
        interval=5.0,
    )
    app.state.system_monitor = monitor


def _register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(APIException, api_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, general_exception_handler)
