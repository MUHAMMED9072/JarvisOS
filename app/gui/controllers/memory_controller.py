from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from app.cortex.handlers.memory_handler import MemoryHandler


@dataclass
class MemoryStats:
    total_items: int = 0
    session_messages: int = 0
    last_application: str | None = None


@dataclass
class SearchResult:
    content: str
    role: str
    timestamp: float = 0.0


class MemoryController:
    """Orchestrates the Memory Center page."""

    def __init__(self, registry) -> None:
        self.registry = registry
        self._handler = MemoryHandler(registry)

    # ------------------------------------------------------------------
    # Session messages (via handler)
    # ------------------------------------------------------------------

    def get_session_messages(self) -> list[dict[str, Any]]:
        ctx = self._handler.get_session_context()
        return ctx.get("messages", [])

    def get_session_context(self) -> dict[str, Any]:
        return self._handler.get_session_context()

    # ------------------------------------------------------------------
    # Search (direct access — handler recall limits to 3 str results)
    # ------------------------------------------------------------------

    def search_memories(self, query: str) -> list[SearchResult]:
        if not query.strip():
            return []
        memory = self.registry.get("memory")
        results = memory.search(query)
        parsed: list[SearchResult] = []
        for item in results:
            parsed.append(
                SearchResult(
                    content=getattr(item, "content", str(item)),
                    role=getattr(item, "role", "assistant"),
                    timestamp=getattr(item, "timestamp", 0.0),
                )
            )
        return parsed

    # ------------------------------------------------------------------
    # Statistics (direct access for aggregate data)
    # ------------------------------------------------------------------

    def get_statistics(self) -> MemoryStats:
        memory = self.registry.get("memory")
        all_items = memory.history.get_all()
        session_msgs = memory.get_session_messages()
        last_app = memory.get_last_application()
        return MemoryStats(
            total_items=len(all_items),
            session_messages=len(session_msgs),
            last_application=last_app,
        )

    # ------------------------------------------------------------------
    # Stored preferences (direct access)
    # ------------------------------------------------------------------

    def get_preferences(self) -> dict[str, Any]:
        memory = self.registry.get("memory")
        return dict(memory.storage.get("preferences", {}))

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def clear_session(self) -> None:
        memory = self.registry.get("memory")
        memory.session.clear()

    def clear_all(self) -> None:
        memory = self.registry.get("memory")
        memory.clear()
