from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.dependencies import get_registry
from app.api.schemas import StatusResponse
from app.core.config import Config
from app.core.registry import ServiceRegistry

router = APIRouter(tags=["Status"])


@router.get("/status", response_model=StatusResponse)
async def status(
    registry: ServiceRegistry | None = Depends(get_registry),
) -> StatusResponse:
    """Return the detailed system status."""
    plugins = 0
    skills = 0
    services = 0
    memory_status = "unknown"
    voice_status = "disabled"

    if registry is not None:
        services = len(registry.list_services())

        plugin_mgr = registry.get_optional("plugin_manager")
        if plugin_mgr is not None:
            plugins = len(plugin_mgr.list_plugins())

        skill_mgr = registry.get_optional("skill_manager")
        if skill_mgr is not None:
            skills = len(skill_mgr.skills)

        memory = registry.get_optional("memory")
        if memory is not None:
            memory_status = "available"

        voice_config = registry.get_optional("voice_config")
        if voice_config is not None:
            voice_status = "enabled" if getattr(
                voice_config, "enabled", False,
            ) else "disabled"

    return StatusResponse(
        status="running",
        version=Config.VERSION,
        plugins=plugins,
        skills=skills,
        services=services,
        memory=memory_status,
        voice=voice_status,
    )
