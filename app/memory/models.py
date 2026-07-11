from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any


@dataclass(slots=True)
class MemoryItem:
    """
    Represents a single memory entry.
    """

    timestamp: str
    role: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> "MemoryItem":
        return cls(
            timestamp=datetime.now(timezone.utc).isoformat(),
            role=role,
            content=content,
            metadata=metadata or {},
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)