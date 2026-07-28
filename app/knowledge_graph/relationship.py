from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .schema import RELATIONSHIP_TYPES


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return uuid.uuid4().hex


@dataclass
class Relationship:
    id: str = field(default_factory=_new_id)
    type: str = "related_to"
    source_id: str = ""
    target_id: str = ""
    properties: dict[str, Any] = field(default_factory=dict)
    created: str = field(default_factory=_utcnow)
    updated: str = field(default_factory=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "properties": dict(self.properties),
            "created": self.created,
            "updated": self.updated,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Relationship:
        return cls(
            id=data["id"],
            type=data.get("type", "related_to"),
            source_id=data["source_id"],
            target_id=data["target_id"],
            properties=data.get("properties", {}),
            created=data.get("created", _utcnow()),
            updated=data.get("updated", _utcnow()),
        )

    @classmethod
    def create(
        cls,
        type: str,
        source_id: str,
        target_id: str,
        properties: dict[str, Any] | None = None,
        id: str | None = None,
    ) -> Relationship:
        rel_type = RELATIONSHIP_TYPES.get(type)
        if rel_type is None:
            raise ValueError(f"Unknown relationship type '{type}'")
        if rel_type.source_types or rel_type.target_types:
            pass  # Validation requires entity types, done at store level
        return cls(
            id=id or _new_id(),
            type=type,
            source_id=source_id,
            target_id=target_id,
            properties=properties or {},
        )

    def reversed(self) -> Relationship:
        return Relationship(
            type=self.type,
            source_id=self.target_id,
            target_id=self.source_id,
            properties=dict(self.properties),
        )
