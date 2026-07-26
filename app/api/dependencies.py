from __future__ import annotations

from typing import Any

from fastapi import Request

from app.core.registry import ServiceRegistry


def get_registry(request: Request) -> ServiceRegistry | None:
    """Extract the ServiceRegistry from the request's app state."""
    registry: ServiceRegistry | None = getattr(request.app.state, "registry", None)
    return registry


def get_service(name: str) -> Any:
    """Return a FastAPI dependency that resolves a named service."""

    def _resolve(request: Request) -> Any:
        registry = get_registry(request)
        if registry is None:
            return None
        return registry.get_optional(name)

    return _resolve


def require_service(name: str) -> Any:
    """Return a FastAPI dependency that requires a named service.

    Raises 503 if the service is not registered.
    """

    def _resolve(request: Request) -> Any:
        from app.api.errors import ServiceUnavailableError

        registry = get_registry(request)
        if registry is None:
            raise ServiceUnavailableError("Service registry not available")
        service = registry.get_optional(name)
        if service is None:
            raise ServiceUnavailableError(
                f"Service {name!r} is not available",
            )
        return service

    return _resolve
