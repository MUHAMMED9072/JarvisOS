from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from .storage import MemoryStorage


class MemoryHistory:
    """Read/search access to long-term memory with TTL-based pruning."""

    def __init__(self, storage: MemoryStorage):
        self.storage = storage

    def get_all(self) -> list[dict[str, Any]]:
        """Return all stored memories."""
        return self.storage.get("items", [])

    def get_recent(self, limit: int = 10) -> list[dict[str, Any]]:
        """Return the most recent memories."""
        return self.storage.get("items", [])[-limit:]

    def search(self, query: str) -> list[dict[str, Any]]:
        """Search memories by content (case-insensitive)."""
        query = query.lower()
        return [
            memory
            for memory in self.storage.get("items", [])
            if query in memory.get("content", "").lower()
        ]

    def last_user_message(self) -> dict[str, Any] | None:
        """Return the last user message."""
        for memory in reversed(self.storage.get("items", [])):
            if memory.get("role") == "user":
                return memory
        return None

    def last_assistant_message(self) -> dict[str, Any] | None:
        """Return the last assistant message."""
        for memory in reversed(self.storage.get("items", [])):
            if memory.get("role") == "assistant":
                return memory
        return None

    def prune(self, ttl_days: int = 30) -> int:
        """Remove items whose timestamp is older than *ttl_days*.

        Returns the number of items removed.
        """
        items = self.storage.get("items", [])
        if not items:
            return 0

        cutoff = (datetime.now(timezone.utc) - timedelta(days=ttl_days)).isoformat()
        kept = [it for it in items if it.get("timestamp", "") >= cutoff]
        removed = len(items) - len(kept)
        if removed:
            self.storage.set("items", kept)
        return removed
