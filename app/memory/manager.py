from typing import Any

import numpy as np

from .context import ContextManager
from .embeddings import EmbeddingProvider, get_embedding_provider
from .history import MemoryHistory
from .knowledge import KnowledgeBase
from .models import MemoryItem
from .preferences import UserPreferences
from .projects import ProjectMemory
from .search import HybridSearch, SearchResult
from .session import SessionMemory
from .storage import MemoryStorage
from .vector import VectorStore


class MemoryManager:
    """Main interface for the JARVIS Memory Engine."""

    def __init__(
        self,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> None:
        self.storage = MemoryStorage("history.json")
        self.session = SessionMemory()
        self.history = MemoryHistory(self.storage)
        self.vector_store = VectorStore(
            embedding_provider=embedding_provider,
        )
        self.knowledge = KnowledgeBase()
        self.preferences = UserPreferences()
        self.projects = ProjectMemory()
        self.context = ContextManager()
        self.search_engine = HybridSearch(
            vector_store=self.vector_store,
            history=self.history,
        )

    # ------------------------------------------------------------------
    # History (conversation memory)
    # ------------------------------------------------------------------

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

        # Also add to vector store for semantic search
        self.vector_store.add(content=content, metadata=metadata or {})

    def get_recent(self, limit: int = 10):
        return self.history.get_recent(limit)

    def get_session_messages(self):
        return self.session.get_messages()

    def prune_all(self, ttl_days: int = 30) -> int:
        """Remove history items older than *ttl_days*.

        Returns the number of items removed.
        """
        history_removed = self.history.prune(ttl_days)
        vector_removed = self.vector_store.prune(ttl_days=ttl_days)
        return history_removed + vector_removed

    # ------------------------------------------------------------------
    # Context
    # ------------------------------------------------------------------

    def set_context(
        self,
        *,
        intent: str | None = None,
        entities: dict | None = None,
        skill: str | None = None,
    ) -> None:
        self.session.set_context(
            intent=intent,
            entities=entities,
            skill=skill,
        )
        if intent is not None:
            self.context.set_intent(intent)
        if entities is not None:
            self.context.set_entities(entities)
        if skill is not None:
            self.context.set_skill(skill)

    def get_last_application(self) -> str | None:
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

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(self, query: str) -> list[dict[str, Any]]:
        return self.history.search(query)

    def semantic_search(
        self,
        query: str,
        top_k: int = 10,
        min_score: float = 0.0,
    ) -> list[SearchResult]:
        return self.search_engine.semantic_search(
            query=query, top_k=top_k, min_score=min_score
        )

    def hybrid_search(
        self,
        query: str,
        top_k: int = 10,
        keyword_weight: float = 0.3,
        vector_weight: float = 0.7,
        min_score: float = 0.0,
    ) -> list[SearchResult]:
        return self.search_engine.search(
            query=query,
            top_k=top_k,
            keyword_weight=keyword_weight,
            vector_weight=vector_weight,
            min_score=min_score,
        )

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def clear(self):
        self.storage.clear()
        self.session.clear()
        self.vector_store.clear()
        self.knowledge.clear()
        self.preferences.clear()
        self.projects.clear()
        self.context.clear()

    def save_all(self) -> None:
        self.storage.save(self.storage.load())
        self.vector_store.save()
        self.knowledge.save()
        self.preferences.save()
        self.projects.save()
        self.context.save()