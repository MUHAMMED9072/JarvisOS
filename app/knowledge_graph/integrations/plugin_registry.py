from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.knowledge_graph.store import GraphStore


@dataclass
class PluginRecord:
    plugin_id: str = ""
    name: str = ""
    version: str = ""
    status: str = "inactive"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "plugin_id": self.plugin_id,
            "name": self.name,
            "version": self.version,
            "status": self.status,
            "metadata": dict(self.metadata),
        }


class PluginRegistry:
    def __init__(self, graph_store: GraphStore) -> None:
        self._store = graph_store

    def register(self, name: str, version: str = "", status: str = "inactive") -> PluginRecord:
        entity = self._store.create_entity(
            type="plugin", name=name,
            properties={"version": version, "status": status},
        )
        return self._to_record(entity)

    def get(self, plugin_id: str) -> PluginRecord | None:
        entity = self._store.get_entity(plugin_id)
        if entity is None or entity.type != "plugin":
            return None
        return self._to_record(entity)

    def list(self, status: str | None = None) -> list[PluginRecord]:
        records = [self._to_record(e) for e in self._store.get_entities_by_type("plugin")]
        if status:
            records = [r for r in records if r.status == status]
        return records

    def search(self, query: str) -> list[PluginRecord]:
        return [self._to_record(e) for e in self._store.search(query) if e.type == "plugin"]

    def update_status(self, plugin_id: str, status: str) -> PluginRecord | None:
        entity = self._store.update_entity(plugin_id, properties={"status": status})
        if entity is None:
            return None
        return self._to_record(entity)

    def delete(self, plugin_id: str) -> bool:
        return self._store.delete_entity(plugin_id)

    def _to_record(self, entity: Any) -> PluginRecord:
        return PluginRecord(
            plugin_id=entity.id,
            name=entity.name,
            version=entity.properties.get("version", ""),
            status=entity.properties.get("status", "inactive"),
        )
