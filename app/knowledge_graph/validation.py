from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.knowledge_graph.schema import ENTITY_TYPES
from app.knowledge_graph.store import GraphStore


@dataclass
class ValidationResult:
    valid: bool = True
    entity_count: int = 0
    relationship_count: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "entity_count": self.entity_count,
            "relationship_count": self.relationship_count,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }


class DataValidator:
    """Validates data integrity within the Knowledge Graph.

    Checks include:
    - All entity types are registered
    - All relationships reference valid source/target entities
    - No orphaned relationships
    - Entity schema compliance
    """

    def __init__(self, store: GraphStore) -> None:
        self._store = store

    def validate_all(self) -> ValidationResult:
        result = ValidationResult()
        entities = self._store.list_entities()
        result.entity_count = len(entities)
        result.relationship_count = self._store.relationship_count()

        # Validate entity types
        type_counts: dict[str, int] = {}
        for entity in entities:
            type_counts[entity.type] = type_counts.get(entity.type, 0) + 1
            if not ENTITY_TYPES.is_valid(entity.type):
                result.errors.append(
                    f"Entity '{entity.id}' has unknown type '{entity.type}'"
                )

        # Validate relationships
        orphaned = self._find_orphaned_relationships()
        for rel_id, source_id, target_id in orphaned:
            result.errors.append(
                f"Relationship '{rel_id}' references missing entity "
                f"('{source_id}' -> '{target_id}')"
            )

        # Warnings for types with very few entities
        for tname, count in sorted(type_counts.items()):
            if count == 0:
                result.warnings.append(f"Type '{tname}' has no entities")

        result.valid = len(result.errors) == 0
        return result

    def validate_entity(self, entity_id: str) -> ValidationResult:
        result = ValidationResult()
        entity = self._store.get_entity(entity_id)
        if entity is None:
            result.errors.append(f"Entity '{entity_id}' not found")
            result.valid = False
            return result
        result.entity_count = 1
        if not ENTITY_TYPES.is_valid(entity.type):
            result.errors.append(f"Entity '{entity_id}' has unknown type '{entity.type}'")
            result.valid = False
        return result

    def validate_relationship(self, rel_id: str) -> ValidationResult:
        result = ValidationResult()
        rel = self._store.get_relationship(rel_id)
        if rel is None:
            result.errors.append(f"Relationship '{rel_id}' not found")
            result.valid = False
            return result
        result.relationship_count = 1
        source = self._store.get_entity(rel["source_id"])
        target = self._store.get_entity(rel["target_id"])
        if source is None:
            result.errors.append(f"Relationship '{rel_id}' source entity not found")
            result.valid = False
        if target is None:
            result.errors.append(f"Relationship '{rel_id}' target entity not found")
            result.valid = False
        return result

    def _find_orphaned_relationships(self) -> list[tuple[str, str, str]]:
        orphaned: list[tuple[str, str, str]] = []
        import uuid

        # Iterate all entities to collect relationships
        visited_rel_ids: set[str] = set()
        for entity in self._store.list_entities():
            for rel in self._store.get_outgoing_relationships(entity.id):
                rid = rel.get("id", str(uuid.uuid4()))
                if rid in visited_rel_ids:
                    continue
                visited_rel_ids.add(rid)
                target = self._store.get_entity(rel["target_id"])
                if target is None:
                    orphaned.append((rid, rel["source_id"], rel["target_id"]))
            for rel in self._store.get_incoming_relationships(entity.id):
                rid = rel.get("id", str(uuid.uuid4()))
                if rid in visited_rel_ids:
                    continue
                visited_rel_ids.add(rid)
                source = self._store.get_entity(rel["source_id"])
                if source is None:
                    orphaned.append((rid, rel["source_id"], rel["target_id"]))
        return orphaned

    def health(self) -> dict[str, Any]:
        return {
            "alive": True,
            "validator_ready": True,
        }
