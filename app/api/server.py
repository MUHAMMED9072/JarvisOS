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
from app.ws.manager import WebSocketConnectionManager


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan: shutdown only (startup done in create_app)."""
    yield
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
    app.state.ws_manager = WebSocketConnectionManager()

    register_routes(app)
    register_middleware(app)
    _register_error_handlers(app)

    return app


def _register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(APIException, api_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, general_exception_handler)
