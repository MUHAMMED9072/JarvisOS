from __future__ import annotations

import enum
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any


class MemoryType(enum.Enum):
    WORKING = "working"
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"
    SHARED = "shared"
    REFLECTION = "reflection"


@dataclass
class MemoryEntry:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    agent_id: str = ""
    memory_type: MemoryType = MemoryType.WORKING
    key: str = ""
    content: Any = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    ttl_seconds: float = 0.0  # 0 = no expiration
    tags: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)  # agent_ids with access

    def is_expired(self) -> bool:
        if self.ttl_seconds <= 0:
            return False
        return (time.time() - self.created_at) > self.ttl_seconds

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "agent_id": self.agent_id,
            "memory_type": self.memory_type.value,
            "key": self.key,
            "content": self.content,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "ttl_seconds": self.ttl_seconds,
            "tags": list(self.tags),
            "permissions": list(self.permissions),
        }


class AgentMemory:
    """Per-agent sandboxed memory store with six memory types.

    Thread-safe.  Each agent gets its own memory space identified
    by agent_id.  Memory entries are isolated — one agent cannot
    read another's entries unless Shared memory grants permission.
    """

    def __init__(self, agent_id: str) -> None:
        self._agent_id = agent_id
        self._lock = threading.RLock()
        self._entries: dict[str, dict[str, MemoryEntry]] = {
            mt.value: {} for mt in MemoryType
        }

    @property
    def agent_id(self) -> str:
        return self._agent_id

    # ------------------------------------------------------------------
    # CRUD per memory type
    # ------------------------------------------------------------------

    def store(
        self,
        memory_type: MemoryType,
        key: str,
        content: Any,
        ttl_seconds: float = 0.0,
        tags: list[str] | None = None,
        permissions: list[str] | None = None,
    ) -> MemoryEntry:
        entry = MemoryEntry(
            agent_id=self._agent_id,
            memory_type=memory_type,
            key=key,
            content=content,
            ttl_seconds=ttl_seconds,
            tags=tags or [],
            permissions=permissions or [],
        )
        with self._lock:
            self._entries[memory_type.value][key] = entry
        return entry

    def retrieve(self, memory_type: MemoryType, key: str) -> MemoryEntry | None:
        with self._lock:
            entry = self._entries[memory_type.value].get(key)
            if entry is None or entry.is_expired():
                if entry is not None:
                    self._delete_internal(memory_type, key)
                return None
            return entry

    def update(self, memory_type: MemoryType, key: str, content: Any) -> bool:
        with self._lock:
            entry = self._entries[memory_type.value].get(key)
            if entry is None or entry.is_expired():
                return False
            entry.content = content
            entry.updated_at = time.time()
            return True

    def delete(self, memory_type: MemoryType, key: str) -> bool:
        with self._lock:
            return self._delete_internal(memory_type, key)

    def _delete_internal(self, memory_type: MemoryType, key: str) -> bool:
        mt = memory_type.value
        if key in self._entries[mt]:
            del self._entries[mt][key]
            return True
        return False

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def list(self, memory_type: MemoryType) -> list[MemoryEntry]:
        with self._lock:
            self._expire(memory_type)
            return list(self._entries[memory_type.value].values())

    def search(self, query: str, memory_type: MemoryType | None = None) -> list[MemoryEntry]:
        q = query.lower()
        results: list[MemoryEntry] = []
        types = [memory_type] if memory_type else list(MemoryType)
        with self._lock:
            for mt in types:
                self._expire(mt)
                for entry in self._entries[mt.value].values():
                    if q in entry.key.lower():
                        results.append(entry)
                        continue
                    if isinstance(entry.content, str) and q in entry.content.lower():
                        results.append(entry)
                        continue
                    for tag in entry.tags:
                        if q in tag.lower():
                            results.append(entry)
                            break
        return results

    def count(self, memory_type: MemoryType | None = None) -> int:
        with self._lock:
            if memory_type:
                self._expire(memory_type)
                return len(self._entries[memory_type.value])
            total = 0
            for mt in MemoryType:
                self._expire(mt)
                total += len(self._entries[mt.value])
            return total

    # ------------------------------------------------------------------
    # Working memory
    # ------------------------------------------------------------------

    def clear_working(self) -> int:
        count = 0
        with self._lock:
            count = len(self._entries[MemoryType.WORKING.value])
            self._entries[MemoryType.WORKING.value].clear()
        return count

    # ------------------------------------------------------------------
    # Cross-agent access (Shared memory)
    # ------------------------------------------------------------------

    def grant_access(self, key: str, agent_id: str) -> bool:
        with self._lock:
            entry = self._entries[MemoryType.SHARED.value].get(key)
            if entry is None:
                return False
            if agent_id not in entry.permissions:
                entry.permissions.append(agent_id)
            return True

    def read_shared(self, owner_agent_id: str, key: str) -> MemoryEntry | None:
        """Read a shared memory entry from another agent."""
        if owner_agent_id == self._agent_id:
            return self.retrieve(MemoryType.SHARED, key)
        # In a real system this would require cross-agent lookup.
        return None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _expire(self, memory_type: MemoryType) -> None:
        mt = memory_type.value
        expired_keys = [
            k for k, v in self._entries[mt].items() if v.is_expired()
        ]
        for k in expired_keys:
            del self._entries[mt][k]

    def health(self) -> dict[str, Any]:
        return {
            "alive": True,
            "agent_id": self._agent_id,
            "total_entries": self.count(),
            "memory_types": {mt.value: self.count(mt) for mt in MemoryType},
        }
