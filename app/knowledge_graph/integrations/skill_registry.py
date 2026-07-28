from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.knowledge_graph.store import GraphStore


@dataclass
class SkillRecord:
    skill_id: str = ""
    name: str = ""
    version: str = ""
    intents: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "name": self.name,
            "version": self.version,
            "intents": list(self.intents),
            "metadata": dict(self.metadata),
        }


class SkillRegistry:
    def __init__(self, graph_store: GraphStore) -> None:
        self._store = graph_store

    def register(self, name: str, version: str = "", intents: list[str] | None = None) -> SkillRecord:
        entity = self._store.create_entity(type="skill", name=name, properties={"version": version})
        return SkillRecord(
            skill_id=entity.id,
            name=entity.name,
            version=entity.properties.get("version", ""),
            intents=intents or [],
        )

    def get(self, skill_id: str) -> SkillRecord | None:
        entity = self._store.get_entity(skill_id)
        if entity is None or entity.type != "skill":
            return None
        return self._to_record(entity)

    def list(self) -> list[SkillRecord]:
        return [self._to_record(e) for e in self._store.get_entities_by_type("skill")]

    def search(self, query: str) -> list[SkillRecord]:
        return [self._to_record(e) for e in self._store.search(query) if e.type == "skill"]

    def delete(self, skill_id: str) -> bool:
        return self._store.delete_entity(skill_id)

    def _to_record(self, entity: Any) -> SkillRecord:
        return SkillRecord(
            skill_id=entity.id,
            name=entity.name,
            version=entity.properties.get("version", ""),
        )
