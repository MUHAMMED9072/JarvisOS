from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# =========================================================================
# Entity Types
# =========================================================================


@dataclass(frozen=True)
class EntityType:
    """Schema definition for a node type in the Knowledge Graph."""

    name: str
    fields: dict[str, type] = field(default_factory=dict)
    description: str = ""

    def validate(self, properties: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        for field_name, expected_type in self.fields.items():
            if field_name not in properties:
                errors.append(f"Missing required field '{field_name}'")
                continue
            value = properties[field_name]
            if not isinstance(value, expected_type):
                errors.append(
                    f"Field '{field_name}' expected {expected_type.__name__}, "
                    f"got {type(value).__name__}"
                )
        return errors


class EntityTypeRegistry:
    """Registry of all defined entity (node) types."""

    def __init__(self) -> None:
        self._types: dict[str, EntityType] = {}

    def register(self, entity_type: EntityType) -> None:
        self._types[entity_type.name] = entity_type

    def get(self, name: str) -> EntityType | None:
        return self._types.get(name)

    def is_valid(self, name: str) -> bool:
        return name in self._types

    def list_types(self) -> list[EntityType]:
        return list(self._types.values())

    def validate_properties(self, type_name: str, properties: dict[str, Any]) -> list[str]:
        entity_type = self._types.get(type_name)
        if entity_type is None:
            return [f"Unknown entity type '{type_name}'"]
        return entity_type.validate(properties)

    def clear(self) -> None:
        self._types.clear()


# =========================================================================
# Relationship Types
# =========================================================================


@dataclass(frozen=True)
class RelationshipType:
    """Schema definition for a relationship (edge) type in the Knowledge Graph."""

    name: str
    source_types: list[str] = field(default_factory=list)
    target_types: list[str] = field(default_factory=list)
    properties: dict[str, type] = field(default_factory=dict)
    description: str = ""

    def validate_source(self, source_type: str) -> bool:
        if not self.source_types:
            return True
        return source_type in self.source_types

    def validate_target(self, target_type: str) -> bool:
        if not self.target_types:
            return True
        return target_type in self.target_types


class RelationshipTypeRegistry:
    """Registry of all defined relationship (edge) types."""

    def __init__(self) -> None:
        self._types: dict[str, RelationshipType] = {}

    def register(self, rel_type: RelationshipType) -> None:
        self._types[rel_type.name] = rel_type

    def get(self, name: str) -> RelationshipType | None:
        return self._types.get(name)

    def is_valid(self, name: str) -> bool:
        return name in self._types

    def list_types(self) -> list[RelationshipType]:
        return list(self._types.values())

    def clear(self) -> None:
        self._types.clear()


# =========================================================================
# Built-in types
# =========================================================================

ENTITY_TYPES = EntityTypeRegistry()
ENTITY_TYPES.register(EntityType("agent", fields={"name": str}, description="An AI agent"))
ENTITY_TYPES.register(EntityType("tool", fields={"name": str}, description="A tool or function"))
ENTITY_TYPES.register(
    EntityType("memory", fields={"type": str}, description="A memory entry")
)
ENTITY_TYPES.register(
    EntityType("project", fields={"name": str}, description="A project")
)
ENTITY_TYPES.register(
    EntityType("task", fields={"name": str, "status": str}, description="A task")
)
ENTITY_TYPES.register(
    EntityType("file", fields={"path": str}, description="A file or module")
)
ENTITY_TYPES.register(
    EntityType("capability", fields={"name": str}, description="A capability")
)
ENTITY_TYPES.register(
    EntityType("skill", fields={"name": str}, description="A skill")
)
ENTITY_TYPES.register(
    EntityType("plugin", fields={"name": str}, description="A plugin")
)
ENTITY_TYPES.register(
    EntityType("workflow", fields={"name": str}, description="A workflow definition")
)
ENTITY_TYPES.register(
    EntityType("concept", description="A generic concept or idea")
)

RELATIONSHIP_TYPES = RelationshipTypeRegistry()
RELATIONSHIP_TYPES.register(
    RelationshipType(
        "depends_on",
        description="A depends on B",
    )
)
RELATIONSHIP_TYPES.register(
    RelationshipType(
        "contains",
        description="A contains B",
    )
)
RELATIONSHIP_TYPES.register(
    RelationshipType(
        "uses",
        description="A uses B",
    )
)
RELATIONSHIP_TYPES.register(
    RelationshipType(
        "created_by",
        description="A was created by B",
    )
)
RELATIONSHIP_TYPES.register(
    RelationshipType(
        "references",
        description="A references B",
    )
)
RELATIONSHIP_TYPES.register(
    RelationshipType(
        "implements",
        description="A implements B",
    )
)
RELATIONSHIP_TYPES.register(
    RelationshipType(
        "extends",
        description="A extends B",
    )
)
RELATIONSHIP_TYPES.register(
    RelationshipType(
        "related_to",
        description="A is related to B",
    )
)
