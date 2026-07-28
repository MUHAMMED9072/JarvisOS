from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.knowledge_graph.store import GraphStore


@dataclass
class ModelRecord:
    model_id: str = ""
    name: str = ""
    provider: str = ""
    version: str = ""
    capabilities: list[str] = field(default_factory=list)
    cost_per_call: float = 0.0
    latency_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "name": self.name,
            "provider": self.provider,
            "version": self.version,
            "capabilities": list(self.capabilities),
            "cost_per_call": self.cost_per_call,
            "latency_ms": self.latency_ms,
            "metadata": dict(self.metadata),
        }


class ModelRegistry:
    def __init__(self, graph_store: GraphStore) -> None:
        self._store = graph_store

    def register(
        self,
        name: str,
        provider: str = "",
        version: str = "",
        cost_per_call: float = 0.0,
        latency_ms: float = 0.0,
    ) -> ModelRecord:
        entity = self._store.create_entity(
            type="model", name=name,
            properties={
                "provider": provider,
                "version": version,
                "cost_per_call": cost_per_call,
                "latency_ms": latency_ms,
            },
        )
        return self._to_record(entity)

    def get(self, model_id: str) -> ModelRecord | None:
        entity = self._store.get_entity(model_id)
        if entity is None or entity.type != "model":
            return None
        return self._to_record(entity)

    def list(self) -> list[ModelRecord]:
        return [self._to_record(e) for e in self._store.get_entities_by_type("model")]

    def search(self, query: str) -> list[ModelRecord]:
        return [self._to_record(e) for e in self._store.search(query) if e.type == "model"]

    def delete(self, model_id: str) -> bool:
        return self._store.delete_entity(model_id)

    def _to_record(self, entity: Any) -> ModelRecord:
        return ModelRecord(
            model_id=entity.id,
            name=entity.name,
            provider=entity.properties.get("provider", ""),
            version=entity.properties.get("version", ""),
            cost_per_call=entity.properties.get("cost_per_call", 0.0),
            latency_ms=entity.properties.get("latency_ms", 0.0),
        )
