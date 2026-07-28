from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.knowledge_graph.store import GraphStore


@dataclass
class ToolRecord:
    tool_id: str = ""
    name: str = ""
    version: str = ""
    capabilities: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_id": self.tool_id,
            "name": self.name,
            "version": self.version,
            "capabilities": list(self.capabilities),
            "metadata": dict(self.metadata),
        }


class ToolRegistry:
    def __init__(self, graph_store: GraphStore) -> None:
        self._store = graph_store

    def register(self, name: str, version: str = "", capabilities: list[str] | None = None) -> ToolRecord:
        entity = self._store.create_entity(type="tool", name=name, properties={"version": version})
        for cap in (capabilities or []):
            caps = self._store.get_entity_by_name(cap)
            if caps:
                self._store.create_relationship(type="uses", source_id=entity.id, target_id=caps[0].id)
        return self._to_record(entity)

    def get(self, tool_id: str) -> ToolRecord | None:
        entity = self._store.get_entity(tool_id)
        if entity is None or entity.type != "tool":
            return None
        return self._to_record(entity)

    def list(self) -> list[ToolRecord]:
        return [self._to_record(e) for e in self._store.get_entities_by_type("tool")]

    def search(self, query: str) -> list[ToolRecord]:
        return [self._to_record(e) for e in self._store.search(query) if e.type == "tool"]

    def delete(self, tool_id: str) -> bool:
        return self._store.delete_entity(tool_id)

    def _to_record(self, entity: Any) -> ToolRecord:
        caps: list[str] = []
        for rel in self._store.get_outgoing_relationships(entity.id):
            target = self._store.get_entity(rel["target_id"])
            if target and rel["type"] == "uses":
                caps.append(target.name)
        return ToolRecord(
            tool_id=entity.id,
            name=entity.name,
            version=entity.properties.get("version", ""),
            capabilities=caps,
        )
