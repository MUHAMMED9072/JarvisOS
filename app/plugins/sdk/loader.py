from __future__ import annotations

import importlib
import importlib.util
import inspect
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core.logger import JarvisLogger
from app.plugins.sdk.base import Plugin
from app.plugins.sdk.manager import PluginManager
from app.plugins.sdk.models import (
    PluginDependency,
    PluginManifest,
    validate_manifest,
)


@dataclass
class DiscoveredPlugin:
    name: str
    path: Path
    manifest: PluginManifest
    errors: list[str] = field(default_factory=list)


_MANIFEST_NAMES = ("plugin.json", "manifest.json")


class PluginLoader:
    def __init__(
        self, manager: PluginManager, registry: Any = None,
    ) -> None:
        self._manager = manager
        self._registry = registry
        self._directories: list[Path] = []
        self._discovered: dict[str, DiscoveredPlugin] = {}
        self._modules: dict[str, Any] = {}
        self._module_paths: dict[str, Path] = {}

    def add_directory(self, path: str | Path) -> None:
        p = Path(path).resolve()
        if p.is_dir():
            self._directories.append(p)

    def discover(self) -> list[str]:
        self._discovered.clear()
        for directory in self._directories:
            if not directory.is_dir():
                continue
            for entry in sorted(directory.iterdir()):
                if not entry.is_dir():
                    continue
                manifest = self._load_manifest(entry)
                if manifest is None:
                    continue
                if manifest.name in self._discovered:
                    continue
                errs = validate_manifest(manifest)
                self._discovered[manifest.name] = DiscoveredPlugin(
                    name=manifest.name,
                    path=entry,
                    manifest=manifest,
                    errors=errs,
                )
        return list(self._discovered.keys())

    def _load_manifest(self, plugin_dir: Path) -> PluginManifest | None:
        for filename in _MANIFEST_NAMES:
            fpath = plugin_dir / filename
            if not fpath.is_file():
                continue
            try:
                data: dict[str, Any] = json.loads(
                    fpath.read_text(encoding="utf-8"),
                )
                deps = [
                    PluginDependency(**d)
                    for d in data.get("dependencies", [])
                ]
                return PluginManifest(
                    name=data.get("name", plugin_dir.name),
                    version=str(data.get("version", "1.0.0")),
                    description=data.get("description", ""),
                    author=data.get("author", ""),
                    min_core_version=str(
                        data.get("min_core_version", "0.4.0"),
                    ),
                    dependencies=deps,
                    capabilities=data.get("capabilities", []),
                    config_schema=data.get("config_schema"),
                )
            except Exception as exc:
                JarvisLogger.error(
                    "Failed to load manifest from %r: %s", fpath, exc,
                )
                return None
        return None

    def list_discovered(self) -> dict[str, DiscoveredPlugin]:
        return dict(self._discovered)

    def get_discovered(self, name: str) -> DiscoveredPlugin | None:
        return self._discovered.get(name)

    def resolve_dependencies(
        self, names: list[str] | None = None,
    ) -> list[str]:
        if names is None:
            names = list(self._discovered.keys())
        present = set(names)
        in_degree: dict[str, int] = {n: 0 for n in names}
        reverse_deps: dict[str, list[str]] = {n: [] for n in names}
        for name in names:
            dp = self._discovered.get(name)
            if dp is None:
                continue
            for dep in dp.manifest.dependencies:
                if dep.name in present:
                    in_degree[name] = in_degree.get(name, 0) + 1
                    reverse_deps.setdefault(dep.name, []).append(name)
        queue = [n for n in names if in_degree.get(n, 0) == 0]
        result: list[str] = []
        while queue:
            node = queue.pop(0)
            result.append(node)
            for dependent in reverse_deps.get(node, []):
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)
        return result

    def load_all(
        self, enable: bool = True,
    ) -> list[str]:
        self.discover()
        ordered = self.resolve_dependencies()
        loaded: list[str] = []
        for name in ordered:
            dp = self._discovered.get(name)
            if dp is None or dp.errors:
                JarvisLogger.error(
                    "Skipping plugin %r due to validation errors: %s",
                    name, dp.errors if dp else "unknown",
                )
                continue
            JarvisLogger.info("Loading plugin: %s", name)
            instance = self._instantiate(name)
            if instance is None:
                continue
            mgr = self._manager
            errs = mgr.register(instance, dp.manifest)
            if errs:
                JarvisLogger.error(
                    "Failed to register plugin %r: %s", name, errs,
                )
                dp.errors.extend(errs)
                continue
            mgr.load(dp.manifest.name)
            if enable:
                mgr.enable(dp.manifest.name)
            loaded.append(name)
        return loaded

    def _instantiate(self, name: str) -> Plugin | None:
        dp = self._discovered.get(name)
        if dp is None or not dp.path.is_dir():
            return None
        for module_file in ("main.py", "__init__.py", f"{name}.py"):
            candidate = dp.path / module_file
            if not candidate.is_file():
                continue
            try:
                module_name = f"_plugin_loader_{name}"
                spec = importlib.util.spec_from_file_location(
                    module_name, str(candidate),
                )
                if spec is None or spec.loader is None:
                    continue
                module = importlib.util.module_from_spec(spec)
                self._modules[name] = module
                self._module_paths[name] = candidate
                spec.loader.exec_module(module)
                for _, obj in inspect.getmembers(module, inspect.isclass):
                    if issubclass(obj, Plugin) and obj is not Plugin:
                        instance: Plugin = obj()
                        return instance
            except Exception as exc:
                JarvisLogger.error(
                    "Failed to instantiate plugin %r: %s", name, exc,
                )
                dp.errors.append(str(exc))
                return None
        JarvisLogger.error(
            "No Plugin subclass found in %r", dp.path,
        )
        dp.errors.append("No Plugin subclass found")
        return None

    def unload(self, name: str) -> bool:
        dp = self._discovered.get(name)
        if dp is None:
            JarvisLogger.error("Unload failed: %r not discovered", name)
            return False
        self._manager.unload(name, remove=True)
        module_name = f"_plugin_loader_{name}"
        if module_name in sys.modules:
            try:
                del sys.modules[module_name]
            except Exception:
                pass
        self._modules.pop(name, None)
        self._module_paths.pop(name, None)
        JarvisLogger.info("Plugin unloaded: %s", name)
        return True

    def reload(self, name: str) -> bool:
        dp = self._discovered.get(name)
        if dp is None:
            JarvisLogger.error("Reload failed: %r not discovered", name)
            return False
        self.unload(name)
        instance = self._instantiate(name)
        if instance is None:
            return False
        errs = self._manager.register(instance, dp.manifest)
        if errs:
            JarvisLogger.error(
                "Reload failed for %r: %s", name, errs,
            )
            dp.errors.extend(errs)
            return False
        self._manager.load(dp.manifest.name)
        self._manager.enable(dp.manifest.name)
        JarvisLogger.info("Plugin reloaded: %s", name)
        return True
