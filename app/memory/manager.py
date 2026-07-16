from typing import Any

from .history import MemoryHistory
from .models import MemoryItem
from .session import SessionMemory
from .storage import MemoryStorage


class MemoryManager:
    """
    Main interface for the JARVIS Memory Engine.
    """

    def __init__(self) -> None:
        self.storage = MemoryStorage("history.json")
        self.session = SessionMemory()
        self.history = MemoryHistory(self.storage)

    def remember(
        self,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:

        item = MemoryItem.create(
            role=role,
            content=content,
            metadata=metadata,
        )

        items = self.storage.get("items", [])
        items.append(item.to_dict())
        self.storage.set("items", items)

        self.session.add_message(role, content)

    def set_context(
        self,
        *,
        intent: str |None = None,
        entities: dict | None = None,
        skill: str | None = None,
    ) -> None:

        self.session.set_context(
            intent=intent,
            entities=entities,
            skill=skill,
        )

    def get_recent(self, limit: int = 10):
        return self.history.get_recent(limit)

    def search(self, query: str):
        return self.history.search(query)

    def get_session_messages(self):
        return self.session.get_messages()

    def get_last_application(self) -> str | None:
        """
        Return the last opened application.
        """

        if self.session.last_application:
            return self.session.last_application

        memories = self.history.get_all()

        for memory in reversed(memories):
            metadata = memory.get("metadata", {})

            entities = metadata.get("entities", {})

            app = entities.get("application")

            if app:
                return app

        return None

    def clear(self):
        self.storage.clear()
        self.session.clear()