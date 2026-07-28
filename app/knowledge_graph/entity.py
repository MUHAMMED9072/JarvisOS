from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .schema import ENTITY_TYPES


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return uuid.uuid4().hex


@dataclass
class Entity:
    id: str = field(default_factory=_new_id)
    type: str = "concept"
    name: str = ""
    properties: dict[str, Any] = field(default_factory=dict)
    created: str = field(default_factory=_utcnow)
    updated: str = field(default_factory=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "name": self.name,
            "properties": dict(self.properties),
            "created": self.created,
            "updated": self.updated,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Entity:
        return cls(
            id=data["id"],
            type=data.get("type", "concept"),
            name=data.get("name", ""),
            properties=data.get("properties", {}),
            created=data.get("created", _utcnow()),
            updated=data.get("updated", _utcnow()),
        )

    @classmethod
    def create(
        cls,
        type: str,
        name: str,
        properties: dict[str, Any] | None = None,
        id: str | None = None,
    ) -> Entity:
        if not ENTITY_TYPES.is_valid(type):
            raise ValueError(f"Invalid entity type '{type}'")
        entity_type = ENTITY_TYPES.get(type)
        props = dict(properties or {})
        if "name" in (entity_type.fields if entity_type else {}) and "name" not in props:
            props["name"] = name
        errors = entity_type.validate(props) if entity_type else []
        if errors:
            raise ValueError(f"Entity type '{type}' validation failed: {'; '.join(errors)}")
        return cls(
            id=id or _new_id(),
            type=type,
            name=name,
            properties=props,
        )
