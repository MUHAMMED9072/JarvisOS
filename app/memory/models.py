from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


def utc_now() -> str:
    return datetime.utcnow().isoformat()


@dataclass
class MemoryRecord:
    key: str
    value: Any
    created: str = field(default_factory=utc_now)
    updated: str = field(default_factory=utc_now)

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "value": self.value,
            "created": self.created,
            "updated": self.updated,
        }

    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            key=data["key"],
            value=data["value"],
            created=data.get("created", utc_now()),
            updated=data.get("updated", utc_now()),
        )


@dataclass
class MemoryItem:
    role: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=utc_now)

    def to_dict(self) -> dict:
        return {
            "role": self.role,
            "content": self.content,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
        }

    @classmethod
    def create(
        cls,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> MemoryItem:
        return cls(role=role, content=content, metadata=metadata or {})

    @classmethod
    def from_dict(cls, data: dict) -> MemoryItem:
        return cls(
            role=data["role"],
            content=data["content"],
            metadata=data.get("metadata", {}),
            timestamp=data.get("timestamp", utc_now()),
        )