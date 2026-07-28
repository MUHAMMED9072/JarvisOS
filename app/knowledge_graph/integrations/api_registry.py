from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.knowledge_graph.store import GraphStore


@dataclass
class ApiRecord:
    api_id: str = ""
    name: str = ""
    method: str = "GET"
    path: str = ""
    auth_required: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "api_id": self.api_id,
            "name": self.name,
            "method": self.method,
            "path": self.path,
            "auth_required": self.auth_required,
            "metadata": dict(self.metadata),
        }


class ApiRegistry:
    def __init__(self, graph_store: GraphStore) -> None:
        self._store = graph_store

    def register(self, name: str, method: str = "GET", path: str = "", auth_required: bool = False) -> ApiRecord:
        entity = self._store.create_entity(
            type="api_endpoint", name=name,
            properties={"method": method, "path": path, "auth_required": auth_required},
        )
        return self._to_record(entity)

    def get(self, api_id: str) -> ApiRecord | None:
        entity = self._store.get_entity(api_id)
        if entity is None or entity.type != "api_endpoint":
            return None
        return self._to_record(entity)

    def list(self) -> list[ApiRecord]:
        return [self._to_record(e) for e in self._store.get_entities_by_type("api_endpoint")]

    def search(self, query: str) -> list[ApiRecord]:
        return [self._to_record(e) for e in self._store.search(query) if e.type == "api_endpoint"]

    def delete(self, api_id: str) -> bool:
        return self._store.delete_entity(api_id)

    def _to_record(self, entity: Any) -> ApiRecord:
        return ApiRecord(
            api_id=entity.id,
            name=entity.name,
            method=entity.properties.get("method", "GET"),
            path=entity.properties.get("path", ""),
            auth_required=entity.properties.get("auth_required", False),
        )
