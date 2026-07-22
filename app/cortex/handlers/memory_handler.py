from __future__ import annotations

from typing import Any

from app.cortex.handlers import BaseHandler


class MemoryHandler(BaseHandler):
    """Thin wrapper around MemoryManager."""

    def recall(self, query: str) -> str:
        memory = self.registry.get("memory")
        results = memory.search(query)
        if not results:
            return "No relevant memories found."
        return "\n".join(str(r) for r in results[-3:])

    def get_recent(self, limit: int = 5) -> list[dict[str, Any]]:
        memory = self.registry.get("memory")
        return memory.get_recent(limit)

    def get_session_context(self) -> dict[str, Any]:
        memory = self.registry.get("memory")
        messages = memory.get_session_messages()
        return {"messages": messages}
