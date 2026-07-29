from __future__ import annotations

import threading
from typing import Any

from app.knowledge_graph.capability_registry import CapabilityRegistry
from app.knowledge_graph.store import GraphStore
from app.tools.base import Tool
from app.tools.registry import ToolRegistry


class ToolCapabilityMapper:
    """Maps tool capabilities to the Knowledge Graph CapabilityRegistry.

    For each registered tool:
      1. Ensures each capability exists as a KG entity
      2. Creates 'uses' relationships from tool to capability
      3. Enables capability-based tool discovery via CapabilityRegistry
      4. Tracks quality scores per tool
    """

    def __init__(
        self,
        graph_store: GraphStore,
        tool_registry: ToolRegistry,
        capability_registry: CapabilityRegistry | None = None,
    ) -> None:
        self._store = graph_store
        self._tool_registry = tool_registry
        self._cap_reg = capability_registry or CapabilityRegistry(graph_store)
        self._lock = threading.RLock()

    def register_tool_capabilities(self, tool: Tool) -> int:
        """Register all capabilities of a tool in the KG.

        Returns the number of capabilities registered.
        """
        count = 0
        with self._lock:
            tool_meta = self._tool_registry.get(tool.name)
            if tool_meta is None or not tool_meta.tool_id:
                return 0

            for cap_name in tool.metadata.capabilities:
                cap_id = self._cap_reg.register_capability(cap_name)
                existing_rels = self._store.get_outgoing_relationships(tool_meta.tool_id)
                already = any(
                    r["type"] == "uses" and r["target_id"] == cap_id
                    for r in existing_rels
                )
                if not already:
                    self._store.create_relationship(
                        type="uses",
                        source_id=tool_meta.tool_id,
                        target_id=cap_id,
                    )
                count += 1

            return count

    def find_tools_by_capability(self, capability: str) -> list[dict[str, Any]]:
        """Find tools that provide a specific capability."""
        providers = self._cap_reg.find_providers(capability)
        return [p.to_dict() for p in providers]

    def find_tool_capability_gaps(
        self,
        required_capabilities: list[str],
    ) -> dict[str, Any]:
        """Find which required capabilities are missing from registered tools."""
        analysis = self._cap_reg.find_gaps(required_capabilities)
        return analysis.to_dict()

    def update_tool_quality_score(self, tool_name: str, score: float) -> None:
        """Update quality/confidence score for a tool."""
        meta = self._tool_registry.get(tool_name)
        if meta and meta.tool_id:
            self._cap_reg.update_quality_score(meta.tool_id, score)

    def get_tool_quality_score(self, tool_name: str) -> float:
        meta = self._tool_registry.get(tool_name)
        if meta and meta.tool_id:
            return self._cap_reg.get_quality_score(meta.tool_id)
        return 0.0

    def health(self) -> dict[str, Any]:
        return {
            "alive": True,
            "capability_count": len(self._store.get_entities_by_type("capability")),
        }
