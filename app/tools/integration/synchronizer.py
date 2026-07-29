from __future__ import annotations

import threading
import time
from typing import Any

from app.knowledge_graph.store import GraphStore
from app.tools.base import Tool, ToolStatus
from app.tools.registry import ToolRegistry


class RegistrySynchronizer:
    """Synchronizes the ToolRegistry with the Knowledge Graph.

    Ensures two-way consistency:
      - Tool entities in the KG reflect current tool metadata
      - Capability relationships are maintained
      - Orphaned tool entities are cleaned up
      - Tool status changes propagate to the KG
    """

    def __init__(
        self,
        graph_store: GraphStore,
        tool_registry: ToolRegistry,
    ) -> None:
        self._store = graph_store
        self._registry = tool_registry
        self._lock = threading.RLock()
        self._last_sync_at: float = 0.0
        self._sync_count: int = 0

    def sync_tool(self, tool: Tool) -> dict[str, Any]:
        """Sync a single tool to the KG. Creates or updates the entity."""
        with self._lock:
            existing = self._registry.get(tool.name)
            if existing and existing.tool_id:
                self._registry._update_entity(existing.tool_id, tool)
                return {"action": "updated", "tool_id": existing.tool_id, "name": tool.name}
            meta = self._registry.register(tool)
            return {"action": "created", "tool_id": meta.tool_id, "name": tool.name}

    def remove_tool(self, tool_name: str) -> dict[str, Any]:
        """Remove a tool entity from the KG."""
        with self._lock:
            deleted = self._registry.unregister(tool_name)
            return {"deleted": deleted, "name": tool_name}

    def sync_all(self, tools: list[Tool]) -> dict[str, Any]:
        """Sync all provided tools to the KG."""
        results: list[dict[str, Any]] = []
        with self._lock:
            for tool in tools:
                results.append(self.sync_tool(tool))
            self._last_sync_at = time.time()
            self._sync_count += 1
        return {
            "synced": len(results),
            "results": results,
            "sync_time": self._last_sync_at,
        }

    def detect_orphans(self) -> list[str]:
        """Find tools in the KG that no longer have corresponding instances."""
        orphans: list[str] = []
        with self._lock:
            for meta in self._registry.list():
                if meta.status == ToolStatus.ARCHIVED:
                    orphans.append(meta.name)
        return orphans

    def cleanup_orphans(self) -> int:
        """Remove orphaned or archived tool entities from the KG."""
        count = 0
        with self._lock:
            for meta in self._registry.list():
                if meta.status == ToolStatus.ARCHIVED:
                    self._registry.delete(meta.tool_id)
                    count += 1
        return count

    def get_sync_status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "last_sync_at": self._last_sync_at,
                "sync_count": self._sync_count,
                "tools_in_kg": self._registry.get_tool_count(),
            }

    def health(self) -> dict[str, Any]:
        status = self.get_sync_status()
        return {
            "alive": True,
            "last_sync": status["last_sync_at"],
            "syncs_performed": status["sync_count"],
            "tools_in_kg": status["tools_in_kg"],
        }
