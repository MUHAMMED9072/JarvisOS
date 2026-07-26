from __future__ import annotations

import importlib
import inspect
import pkgutil
from pathlib import Path
from typing import Any

from app.core.config import Config
from app.core.logger import JarvisLogger
from app.plugins.sdk.base import Plugin
from app.plugins.sdk.context import PluginContext
from app.plugins.sdk.models import (
    PluginManifest,
    check_version_compatibility,
    validate_manifest,
)
from app.plugins.sdk.security import PermissionManager


class PluginManager:
    def __init__(self, registry: Any | None = None) -> None:
        self._plugins: dict[str, Plugin] = {}
        self._manifests: dict[str, PluginManifest] = {}
        self._errors: dict[str, list[str]] = {}
        self._registry = registry
        self._plugin_services: dict[str, list[str]] = {}

    @property
    def plugins(self) -> dict[str, Plugin]:
        return dict(self._plugins)

    def list_plugins(self) -> list[str]:
        return list(self._plugins.keys())

    def get_manifest(self, name: str) -> PluginManifest | None:
        return self._manifests.get(name)

    def get_plugin(self, name: str) -> Plugin | None:
        return self._plugins.get(name)

    def get_errors(self, name: str) -> list[str]:
        return list(self._errors.get(name, []))

    def register_plugin_service(self, plugin_name: str, service_name: str) -> None:
        if plugin_name not in self._plugin_services:
            self._plugin_services[plugin_name] = []
        self._plugin_services[plugin_name].append(service_name)

    def get_plugin_services(self, plugin_name: str) -> list[str]:
        return list(self._plugin_services.get(plugin_name, []))

    def get_all_services(self) -> dict[str, list[str]]:
        return {k: list(v) for k, v in self._plugin_services.items()}

    def _cleanup_plugin_services(self, plugin_name: str) -> None:
        service_names = self._plugin_services.pop(plugin_name, [])
        if self._registry is not None:
            for svc_name in service_names:
                self._registry.remove(svc_name)

    def register(
        self,
        plugin: Plugin,
        manifest: PluginManifest | None = None,
    ) -> list[str]:
        errors: list[str] = []
        effective_manifest = manifest or plugin.manifest
        if effective_manifest is None:
            if not plugin.name:
                err = (
                    f"Plugin {type(plugin).__name__} has no name and no "
                    f"manifest"
                )
                return [err]
            effective_manifest = PluginManifest(
                name=plugin.name,
                version=plugin.version,
            )
        errors = validate_manifest(effective_manifest)
        if errors:
            self._errors[effective_manifest.name] = errors
            return errors

        name = effective_manifest.name
        if name in self._plugins:
            err = f"Plugin {name!r} is already registered"
            self._errors[name] = [err]
            return [err]

        if effective_manifest.min_core_version:
            if not check_version_compatibility(
                effective_manifest.min_core_version, Config.VERSION,
            ):
                err = (
                    f"Plugin {name!r} requires core "
                    f"{effective_manifest.min_core_version}, "
                    f"current is {Config.VERSION}"
                )
                self._errors[name] = [err]
                return [err]

        self._plugins[name] = plugin
        self._manifests[name] = effective_manifest
        JarvisLogger.info(
            "Plugin registered: %s v%s", name, effective_manifest.version,
        )
        return []

    def _plugin_config_dir(self, name: str) -> Path:
        return Config.DATA_DIR / "plugins" / name

    def _plugin_permissions(self, name: str) -> list[str]:
        manifest = self._manifests.get(name)
        if manifest is None:
            return []
        if manifest.permissions:
            return list(manifest.permissions)
        return list(manifest.capabilities)

    def load(self, name: str) -> None:
        plugin = self._plugins.get(name)
        if plugin is None:
            JarvisLogger.error("Plugin load failed: %r not registered", name)
            return
        try:
            config_dir = self._plugin_config_dir(name)
            ctx = PluginContext(
                self._registry, name, config_dir=config_dir,
            )
            ctx._set_manager(self)
            plugin._inject(ctx)
            manifest = self._manifests.get(name)
            if manifest and manifest.config_schema:
                ctx.config.set_schema(manifest.config_schema)
            perms = self._plugin_permissions(name)
            perm_mgr = PermissionManager(name, permissions=perms)
            ctx.set_permissions(perm_mgr)
            ctx.load_config()
            plugin.on_load()
            JarvisLogger.info("Plugin loaded: %s", name)
        except Exception as exc:
            JarvisLogger.exception(
                "Plugin load failed for %r: %s", name, exc,
            )

    def enable(self, name: str) -> None:
        plugin = self._plugins.get(name)
        if plugin is None:
            JarvisLogger.error("Plugin enable failed: %r not registered", name)
            return
        try:
            plugin._enabled = True
            plugin.on_enable()
            JarvisLogger.info("Plugin enabled: %s", name)
        except Exception as exc:
            plugin._enabled = False
            JarvisLogger.exception(
                "Plugin enable failed for %r: %s", name, exc,
            )

    def disable(self, name: str) -> None:
        plugin = self._plugins.get(name)
        if plugin is None:
            JarvisLogger.error("Plugin disable failed: %r not registered", name)
            return
        try:
            plugin.on_disable()
        except Exception as exc:
            JarvisLogger.exception(
                "Plugin disable failed for %r: %s", name, exc,
            )
        plugin._enabled = False
        JarvisLogger.info("Plugin disabled: %s", name)

    def unload(self, name: str, remove: bool = False) -> None:
        plugin = self._plugins.get(name)
        if plugin is None:
            JarvisLogger.error("Plugin unload failed: %r not registered", name)
            return
        try:
            if plugin._enabled:
                self.disable(name)
            plugin.on_uninstall()
            JarvisLogger.info("Plugin unloaded: %s", name)
        except Exception as exc:
            JarvisLogger.exception(
                "Plugin unload failed for %r: %s", name, exc,
            )
        self._cleanup_plugin_services(name)
        plugin = self._plugins.get(name)
        if plugin is not None and plugin.context is not None:
            plugin.context.save_config()
            plugin.context._cleanup_subscriptions()
            plugin.context._cleanup_skills()
        if remove:
            self._plugins.pop(name, None)
            self._manifests.pop(name, None)
            self._errors.pop(name, None)

    def discover(self, registry: Any, package: Any = None) -> None:
        if package is None:
            import app.plugins
            package = app.plugins
        pkg_name = getattr(package, "__name__", str(package))
        pkg_path = getattr(package, "__path__", [])
        for _, module_name, _ in pkgutil.walk_packages(pkg_path, pkg_name + "."):
            if module_name.endswith((".sdk", ".sdk.models", ".sdk.context", ".sdk.base", ".sdk.manager")):
                continue
            try:
                module = importlib.import_module(module_name)
            except Exception as exc:
                JarvisLogger.error(
                    "Plugin discovery: failed to import %r: %s",
                    module_name, exc,
                )
                continue
            for _, obj in inspect.getmembers(module, inspect.isclass):
                if not issubclass(obj, Plugin) or obj is Plugin:
                    continue
                try:
                    instance: Plugin = obj()
                    errors = self.register(instance)
                    if errors:
                        JarvisLogger.error(
                            "Plugin discovery: registration failed for "
                            "%r: %s", module_name, errors,
                        )
                        continue
                    self.load(instance.name or module_name)
                except Exception as exc:
                    JarvisLogger.error(
                        "Plugin discovery: failed for %r: %s",
                        module_name, exc,
                    )

    def shutdown_all(self) -> None:
        for name in list(self._plugins.keys()):
            self.unload(name, remove=True)
        self._plugin_services.clear()
        JarvisLogger.info("All plugins shut down")
