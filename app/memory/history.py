from typing import Any

from .storage import MemoryStorage


class MemoryHistory:
    """
    Provides read/search access to long-term memory.
    """

    def __init__(self, storage: MemoryStorage):
        self.storage = storage

    def get_all(self) -> list[dict[str, Any]]:
        """Return all stored memories."""
        return self.storage.get("items", [])

    def get_recent(self, limit: int = 10) -> list[dict[str, Any]]:
        """Return the most recent memories."""
        return self.storage.get("items", [])[-limit:]

    def search(self, query: str) -> list[dict[str, Any]]:
        """
        Search memories by content.
        """
        query = query.lower()

        return [
            memory
            for memory in self.storage.get("items", [])
            if query in memory.get("content", "").lower()
        ]

    def last_user_message(self) -> dict[str, Any] | None:
        """Return the last user message."""
        memories = self.storage.get("items", [])

        for memory in reversed(memories):
            if memory.get("role") == "user":
                return memory

        return None

    def last_assistant_message(self) -> dict[str, Any] | None:
        """Return the last assistant message."""
        memories = self.storage.get("items", [])

        for memory in reversed(memories):
            if memory.get("role") == "assistant":
                return memory

        return None