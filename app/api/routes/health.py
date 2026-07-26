from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.dependencies import get_registry
from app.api.schemas import HealthResponse
from app.core.config import Config
from app.core.registry import ServiceRegistry

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthResponse)
async def health(
    registry: ServiceRegistry | None = Depends(get_registry),
) -> HealthResponse:
    """Return the current health status of the system."""
    healthy_count = 0
    if registry is not None:
        for name in registry.list_services():
            service = registry.get_optional(name)
            if service is not None:
                healthy_count += 1

    return HealthResponse(
        status="healthy",
        version=Config.VERSION,
        services_healthy=healthy_count,
    )
