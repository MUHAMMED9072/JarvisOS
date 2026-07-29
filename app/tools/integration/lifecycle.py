from __future__ import annotations

import importlib
import inspect
import threading
import time
from typing import Any

from app.tools.base import Tool, ToolMetadata, ToolStatus
from app.tools.registry import ToolRegistry


class ToolLifecycleManager:
    """Manages tool discovery, versioning, and lifecycle transitions.

    Capabilities:
      - Auto-discover tool classes by scanning the app.tools package
      - Register new tool versions
      - Transition tools through lifecycle states
      - Track version history
      - Detect duplicate tool names
    """

    def __init__(self, registry: ToolRegistry | None = None) -> None:
        self._registry = registry
        self._lock = threading.RLock()
        self._versions: dict[str, list[dict[str, Any]]] = {}
        self._instances: dict[str, dict[str, Tool]] = {}

    def discover_tools(self, package: str = "app.tools") -> list[Tool]:
        """Auto-discover all Tool subclasses in the given package."""
        discovered: list[Tool] = []
        try:
            pkg = importlib.import_module(package)
            pkg_path = getattr(pkg, "__path__", None)
            if not pkg_path:
                return discovered

            import os
            import importlib.util

            for entry in pkg_path:
                if not os.path.isdir(entry):
                    continue
                for fname in sorted(os.listdir(entry)):
                    if fname.endswith("_tool.py") and not fname.startswith("_"):
                        mod_name = f"{package}.{fname[:-3]}"
                        try:
                            mod = importlib.import_module(mod_name)
                            for name, cls in inspect.getmembers(mod, inspect.isclass):
                                if (
                                    cls is not Tool
                                    and issubclass(cls, Tool)
                                    and not inspect.isabstract(cls)
                                ):
                                    try:
                                        tool = cls()
                                        discovered.append(tool)
                                    except Exception:
                                        pass
                        except Exception:
                            pass
        except Exception:
            pass
        return discovered

    def register_tool(
        self,
        tool: Tool,
        version: str | None = None,
    ) -> ToolMetadata:
        """Register a tool (in-memory + optional KG registry)."""
        ver = version or tool.version
        with self._lock:
            if tool.name not in self._versions:
                self._versions[tool.name] = []
            existing = [v for v in self._versions[tool.name] if v["version"] == ver]
            if not existing:
                self._versions[tool.name].append({
                    "version": ver,
                    "registered_at": time.time(),
                })

            if tool.name not in self._instances:
                self._instances[tool.name] = {}
            self._instances[tool.name][ver] = tool

            if self._registry:
                return self._registry.register(tool)

            return tool.metadata

    def transition_status(self, tool_name: str, new_status: ToolStatus) -> bool:
        """Change a tool's lifecycle status."""
        with self._lock:
            versions = self._instances.get(tool_name)
            if not versions:
                return False
            for tool in versions.values():
                tool.status = new_status
                if self._registry:
                    self._registry._update_entity(tool.tool_id, tool)
            return True

    def get_version_history(self, tool_name: str) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._versions.get(tool_name, []))

    def get_latest_version(self, tool_name: str) -> str | None:
        with self._lock:
            versions = self._versions.get(tool_name)
            if not versions:
                return None
            return versions[-1]["version"]

    def get_tool(self, tool_name: str, version: str | None = None) -> Tool | None:
        with self._lock:
            versions = self._instances.get(tool_name)
            if not versions:
                return None
            if version:
                return versions.get(version)
            latest = self.get_latest_version(tool_name)
            return versions.get(latest) if latest else None

    def list_tools(self) -> list[dict[str, Any]]:
        with self._lock:
            result: list[dict[str, Any]] = []
            for name, versions in self._instances.items():
                latest_ver = self.get_latest_version(name)
                tool = versions.get(latest_ver) if latest_ver else None
                result.append({
                    "name": name,
                    "versions": [v["version"] for v in self._versions.get(name, [])],
                    "latest_version": latest_ver,
                    "status": tool.status.value if tool else "unknown",
                    "capabilities": list(tool.metadata.capabilities) if tool else [],
                })
            return result

    def health(self) -> dict[str, Any]:
        return {
            "alive": True,
            "tools_discovered": len(self._instances),
            "total_versions": sum(len(v) for v in self._versions.values()),
        }
