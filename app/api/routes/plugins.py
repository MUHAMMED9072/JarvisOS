from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request

from app.api.dependencies import get_service, require_service
from app.api.errors import NotFoundError
from app.api.schemas import (
    PluginActionResponse,
    PluginDiscoverResponse,
    PluginInfo,
    PluginListResponse,
    PluginNameRequest,
    PluginPackageInfo,
    PluginPackageListResponse,
    PluginPermissionInfo,
    PluginPermissionListResponse,
    PluginServiceInfo,
    PluginServiceListResponse,
)
from app.core.registry import ServiceRegistry
from app.plugins.sdk.manager import PluginManager
from app.plugins.sdk.models import PluginManifest

router = APIRouter(prefix="/api/v1/plugins", tags=["Plugins"])

PLUGIN_MGR = Depends(require_service("plugin_manager"))

_PERMISSION_DESCRIPTIONS: dict[str, str] = {
    "ai": "Access to AI chat, planning, and reasoning services",
    "events": "Ability to subscribe to and publish events",
    "services": "Ability to register and export services",
    "skills": "Ability to register and unregister skills",
    "config": "Ability to read and write plugin configuration",
    "memory": "Access to the memory system",
    "filesystem": "Access to the file system",
    "network": "Access to network resources",
}


def _plugin_to_info(manager: PluginManager, name: str) -> PluginInfo:
    plugin = manager.get_plugin(name)
    manifest = manager.get_manifest(name)
    errors = manager.get_errors(name)
    services = manager.get_plugin_services(name)
    return PluginInfo(
        name=name,
        version=manifest.version if manifest else (plugin.version if plugin else ""),
        enabled=plugin.enabled if plugin else False,
        description=manifest.description if manifest else "",
        author=manifest.author if manifest else "",
        min_core_version=manifest.min_core_version if manifest else "",
        capabilities=list(manifest.capabilities) if manifest else [],
        permissions=list(manifest.permissions) if manifest else [],
        services=services,
        errors=errors,
    )


# ------------------------------------------------------------------
# List all plugins
# ------------------------------------------------------------------


@router.get("", response_model=PluginListResponse)
async def list_plugins(
    mgr: PluginManager = PLUGIN_MGR,
) -> PluginListResponse:
    plugins = sorted(
        (_plugin_to_info(mgr, name) for name in mgr.list_plugins()),
        key=lambda p: p.name.lower(),
    )
    return PluginListResponse(plugins=plugins)


# ------------------------------------------------------------------
# Discover plugins from filesystem
# ------------------------------------------------------------------


@router.post("/discover", response_model=PluginDiscoverResponse)
async def discover_plugins(
    request: Request,
    mgr: PluginManager = PLUGIN_MGR,
) -> PluginDiscoverResponse:
    from app.plugins.sdk.loader import PluginLoader

    registry: ServiceRegistry | None = getattr(request.app.state, "registry", None)
    loader = PluginLoader(mgr, registry)
    from app.core.config import Config

    plugin_dir = Config.PLUGIN_DIR
    if plugin_dir.is_dir():
        loader.add_directory(plugin_dir)
    discovered = loader.discover()
    loaded = loader.load_all()
    return PluginDiscoverResponse(
        status="ok",
        count=len(loaded),
        plugins=sorted(loaded),
    )


# ------------------------------------------------------------------
# Load a plugin
# ------------------------------------------------------------------


@router.post("/load", response_model=PluginActionResponse)
async def load_plugin(
    body: PluginNameRequest,
    mgr: PluginManager = PLUGIN_MGR,
) -> PluginActionResponse:
    if mgr.get_plugin(body.name) is None:
        raise NotFoundError(f"Plugin {body.name!r} not found")
    mgr.load(body.name)
    return PluginActionResponse(
        status="ok",
        message=f"Plugin {body.name!r} loaded",
        name=body.name,
    )


# ------------------------------------------------------------------
# Unload a plugin
# ------------------------------------------------------------------


@router.post("/unload", response_model=PluginActionResponse)
async def unload_plugin(
    body: PluginNameRequest,
    mgr: PluginManager = PLUGIN_MGR,
) -> PluginActionResponse:
    if mgr.get_plugin(body.name) is None:
        raise NotFoundError(f"Plugin {body.name!r} not found")
    mgr.unload(body.name)
    return PluginActionResponse(
        status="ok",
        message=f"Plugin {body.name!r} unloaded",
        name=body.name,
    )


# ------------------------------------------------------------------
# Reload a plugin (uses PluginLoader for filesystem-backed plugins)
# ------------------------------------------------------------------


@router.post("/reload", response_model=PluginActionResponse)
async def reload_plugin(
    body: PluginNameRequest,
    request: Request,
    mgr: PluginManager = PLUGIN_MGR,
) -> PluginActionResponse:
    from app.plugins.sdk.loader import PluginLoader

    registry: ServiceRegistry | None = getattr(request.app.state, "registry", None)
    loader = PluginLoader(mgr, registry)
    success = loader.reload(body.name)
    if not success:
        raise NotFoundError(
            f"Plugin {body.name!r} not found or reload failed",
        )
    return PluginActionResponse(
        status="ok",
        message=f"Plugin {body.name!r} reloaded",
        name=body.name,
    )


# ------------------------------------------------------------------
# Enable a plugin
# ------------------------------------------------------------------


@router.post("/enable", response_model=PluginActionResponse)
async def enable_plugin(
    body: PluginNameRequest,
    mgr: PluginManager = PLUGIN_MGR,
) -> PluginActionResponse:
    if mgr.get_plugin(body.name) is None:
        raise NotFoundError(f"Plugin {body.name!r} not found")
    mgr.enable(body.name)
    return PluginActionResponse(
        status="ok",
        message=f"Plugin {body.name!r} enabled",
        name=body.name,
    )


# ------------------------------------------------------------------
# Disable a plugin
# ------------------------------------------------------------------


@router.post("/disable", response_model=PluginActionResponse)
async def disable_plugin(
    body: PluginNameRequest,
    mgr: PluginManager = PLUGIN_MGR,
) -> PluginActionResponse:
    if mgr.get_plugin(body.name) is None:
        raise NotFoundError(f"Plugin {body.name!r} not found")
    mgr.disable(body.name)
    return PluginActionResponse(
        status="ok",
        message=f"Plugin {body.name!r} disabled",
        name=body.name,
    )


# ------------------------------------------------------------------
# List all plugin-registered services
# ------------------------------------------------------------------


@router.get("/services", response_model=PluginServiceListResponse)
async def list_plugin_services(
    mgr: PluginManager = PLUGIN_MGR,
) -> PluginServiceListResponse:
    all_services = mgr.get_all_services()
    services = sorted(
        (
            PluginServiceInfo(plugin=name, services=sorted(svcs))
            for name, svcs in all_services.items()
        ),
        key=lambda s: s.plugin.lower(),
    )
    return PluginServiceListResponse(services=services)


# ------------------------------------------------------------------
# List all available permission types
# ------------------------------------------------------------------


@router.get("/permissions", response_model=PluginPermissionListResponse)
async def list_permissions() -> PluginPermissionListResponse:
    from app.plugins.sdk.security import Permission

    perms = [
        PluginPermissionInfo(
            name=p,
            description=_PERMISSION_DESCRIPTIONS.get(p, ""),
        )
        for p in Permission.all_permissions()
    ]
    return PluginPermissionListResponse(permissions=perms)


# ------------------------------------------------------------------
# List installed packages
# ------------------------------------------------------------------


@router.get("/packages", response_model=PluginPackageListResponse)
async def list_packages(
    request: Request,
) -> PluginPackageListResponse:
    registry: ServiceRegistry | None = getattr(request.app.state, "registry", None)
    pm = None
    if registry is not None:
        pm = registry.get_optional("package_manager")
    if pm is None and registry is not None:
        mgr = registry.get_optional("plugin_manager")
        if mgr is not None:
            from app.plugins.sdk.package import PackageManager

            pm = PackageManager(mgr)
    if pm is None:
        return PluginPackageListResponse(packages=[])
    installed = pm.list_installed()
    packages = sorted(
        (
            PluginPackageInfo(
                name=pkg.name,
                version=pkg.version,
                installed_at=pkg.installed_at,
                package_hash=pkg.package_hash,
            )
            for pkg in installed
        ),
        key=lambda p: p.name.lower(),
    )
    return PluginPackageListResponse(packages=packages)


# ------------------------------------------------------------------
# Get a single plugin (must be last to avoid path conflicts)
# ------------------------------------------------------------------


@router.get("/{name}", response_model=PluginInfo)
async def get_plugin(
    name: str,
    mgr: PluginManager = PLUGIN_MGR,
) -> PluginInfo:
    if mgr.get_plugin(name) is None:
        raise NotFoundError(f"Plugin {name!r} not found")
    return _plugin_to_info(mgr, name)
