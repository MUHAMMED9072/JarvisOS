from __future__ import annotations

import threading
from typing import Any

from app.knowledge_graph.store import GraphStore
from app.tools.base import Tool, ToolMetadata, ToolStatus


class ToolRegistry:
    """Tool registry backed by the Knowledge Graph.

    Provides CRUD, search, and discovery of tools by metadata.
    Optionally tracks Tool instances for live instances.

    Thread-safe.  Follows the same pattern as AgentRegistry, ToolRegistry
    (in kg/integrations), SkillRegistry, etc.
    """

    def __init__(self, graph_store: GraphStore) -> None:
        self._store = graph_store
        self._lock = threading.RLock()

    def register(self, tool: Tool) -> ToolMetadata:
        with self._lock:
            name = tool.metadata.name
            version = tool.metadata.version
            existing = self._store.get_entity_by_name(name)
            if existing:
                for ent in existing:
                    if ent.type == "tool":
                        self._update_entity(ent.id, tool)
                        tool.metadata.tool_id = ent.id
                        return tool.metadata

            entity = self._store.create_entity(
                type="tool",
                name=name,
                properties={
                    "version": version,
                    "tool_type": tool.metadata.tool_type,
                    "description": tool.metadata.description,
                    "status": tool.metadata.status.value,
                    "permissions_required": ",".join(tool.metadata.permissions_required),
                    "owner": tool.metadata.owner,
                    "tags": ",".join(tool.metadata.tags),
                },
            )
            tool.metadata.tool_id = entity.id

            for cap in tool.metadata.capabilities:
                caps = self._store.get_entity_by_name(cap)
                if caps:
                    self._store.create_relationship(
                        type="uses",
                        source_id=entity.id,
                        target_id=caps[0].id,
                    )

            return tool.metadata

    def _update_entity(self, entity_id: str, tool: Tool) -> None:
        self._store.update_entity(
            entity_id,
            name=tool.metadata.name,
            properties={
                "version": tool.metadata.version,
                "tool_type": tool.metadata.tool_type,
                "description": tool.metadata.description,
                "status": tool.metadata.status.value,
                "permissions_required": ",".join(tool.metadata.permissions_required),
                "owner": tool.metadata.owner,
                "tags": ",".join(tool.metadata.tags),
            },
        )

    def get(self, name: str) -> ToolMetadata | None:
        with self._lock:
            entities = self._store.get_entity_by_name(name)
            if not entities:
                return None
            for ent in entities:
                if ent.type == "tool":
                    return self._entity_to_metadata(ent)
            return None

    def get_by_id(self, tool_id: str) -> ToolMetadata | None:
        with self._lock:
            entity = self._store.get_entity(tool_id)
            if entity is None or entity.type != "tool":
                return None
            return self._entity_to_metadata(entity)

    def list(self) -> list[ToolMetadata]:
        with self._lock:
            entities = self._store.get_entities_by_type("tool")
            return [self._entity_to_metadata(e) for e in entities]

    def search(self, query: str) -> list[ToolMetadata]:
        with self._lock:
            all_ents = self._store.search(query)
            return [
                self._entity_to_metadata(e)
                for e in all_ents
                if e.type == "tool"
            ]

    def get_by_capability(self, capability: str) -> list[ToolMetadata]:
        with self._lock:
            cap_entities = self._store.get_entity_by_name(capability)
            if not cap_entities:
                return []
            cap = cap_entities[0]
            results: list[ToolMetadata] = []
            for rel in self._store.get_incoming_relationships(cap.id):
                if rel["type"] == "uses":
                    ent = self._store.get_entity(rel["source_id"])
                    if ent and ent.type == "tool":
                        results.append(self._entity_to_metadata(ent))
            return results

    def unregister(self, name: str) -> bool:
        with self._lock:
            entities = self._store.get_entity_by_name(name)
            for ent in entities:
                if ent.type == "tool":
                    return self._store.delete_entity(ent.id)
            return False

    def delete(self, tool_id: str) -> bool:
        with self._lock:
            entity = self._store.get_entity(tool_id)
            if entity and entity.type == "tool":
                return self._store.delete_entity(tool_id)
            return False

    def get_tool_count(self) -> int:
        with self._lock:
            return len(self._store.get_entities_by_type("tool"))

    def _entity_to_metadata(self, entity: Any) -> ToolMetadata:
        caps: list[str] = []
        for rel in self._store.get_outgoing_relationships(entity.id):
            target = self._store.get_entity(rel["target_id"])
            if target and rel["type"] == "uses":
                caps.append(target.name)
        perms_raw = entity.properties.get("permissions_required", "")
        perms = [p for p in perms_raw.split(",") if p] if perms_raw else []
        tags_raw = entity.properties.get("tags", "")
        tags = [t for t in tags_raw.split(",") if t] if tags_raw else []
        return ToolMetadata(
            tool_id=entity.id,
            name=entity.name,
            version=entity.properties.get("version", ""),
            description=entity.properties.get("description", ""),
            tool_type=entity.properties.get("tool_type", "builtin"),
            status=ToolStatus(entity.properties.get("status", "design")) if entity.properties.get("status") else ToolStatus.DESIGN,
            capabilities=caps,
            permissions_required=perms,
            owner=entity.properties.get("owner", ""),
            tags=tags,
        )

    def health(self) -> dict[str, Any]:
        with self._lock:
            return {
                "alive": True,
                "tool_count": self.get_tool_count(),
            }
