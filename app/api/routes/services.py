from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.dependencies import get_registry
from app.api.schemas import ServiceInfo, ServiceListResponse
from app.core.registry import ServiceRegistry

router = APIRouter(tags=["Services"])


@router.get("/services", response_model=ServiceListResponse)
async def list_services(
    registry: ServiceRegistry | None = Depends(get_registry),
) -> ServiceListResponse:
    """Return the list of all registered services with availability."""
    services: list[ServiceInfo] = []
    if registry is not None:
        for name in registry.list_services():
            service = registry.get_optional(name)
            services.append(
                ServiceInfo(name=name, available=service is not None),
            )

    return ServiceListResponse(services=services)
