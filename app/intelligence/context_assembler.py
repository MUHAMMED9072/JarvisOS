from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any

from app.knowledge_graph.store import GraphStore


@dataclass
class Context:
    relevant_entities: list[dict[str, Any]] = field(default_factory=list)
    recent_goals: list[dict[str, Any]] = field(default_factory=list)
    user_preferences: list[dict[str, Any]] = field(default_factory=list)
    constraints: list[dict[str, Any]] = field(default_factory=list)
    related_artifacts: list[dict[str, Any]] = field(default_factory=list)
    gathered_at: float = field(default_factory=time.time)
    query_time_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "relevant_entities": list(self.relevant_entities),
            "recent_goals": list(self.recent_goals),
            "user_preferences": list(self.user_preferences),
            "constraints": list(self.constraints),
            "related_artifacts": list(self.related_artifacts),
            "gathered_at": self.gathered_at,
            "query_time_ms": round(self.query_time_ms, 2),
        }


class ContextAssembler:
    """Gathers relevant context from the Knowledge Graph for a given goal.

    Queries include:
      - Entities matching the goal's domain/type
      - Recent goal history
      - User preferences and constraints
      - Related artifacts (tools, skills, agents)

    Thread-safe.
    """

    def __init__(self, graph_store: GraphStore) -> None:
        self._graph = graph_store
        self._lock = threading.RLock()

    def assemble(self, goal_description: str, goal_type: str = "") -> Context:
        """Query the Knowledge Graph and assemble context for the given goal."""
        with self._lock:
            start = time.time()
            ctx = Context()

            search_terms = self._extract_search_terms(goal_description, goal_type)
            seen_ids: set[str] = set()

            for term in search_terms:
                if not term:
                    continue
                entities = self._graph.search(term)
                for entity in entities:
                    if entity.id not in seen_ids:
                        seen_ids.add(entity.id)
                        ctx.relevant_entities.append(entity.to_dict())

            recent = self._graph.search("goal")
            ctx.recent_goals = [e.to_dict() for e in recent[-10:]]

            prefs = self._graph.search("preference")
            ctx.user_preferences = [e.to_dict() for e in prefs[:10]]

            for etype in ("tool", "skill", "agent"):
                items = self._graph.get_entities_by_type(etype)
                for item in items:
                    if self._matches_goal(item, goal_description, goal_type):
                        ctx.related_artifacts.append(item.to_dict())

            ctx.query_time_ms = (time.time() - start) * 1000.0
            return ctx

    def _extract_search_terms(self, description: str, goal_type: str) -> list[str]:
        terms: list[str] = []
        if goal_type:
            terms.append(goal_type)
        words = description.lower().split()
        stop_words = {
            "a", "an", "the", "is", "are", "was", "were", "to", "of",
            "in", "for", "on", "with", "at", "by", "from", "and", "or",
            "but", "i", "we", "you", "it", "this", "that", "be", "have",
            "do", "will", "would", "could", "should", "can", "may", "might",
        }
        for word in words:
            clean = word.strip(".,;:!?\"'()[]{}")
            if len(clean) > 3 and clean not in stop_words:
                terms.append(clean)
        return terms[:10]

    def _matches_goal(
        self,
        entity: Any,
        description: str,
        goal_type: str,
    ) -> bool:
        desc_lower = description.lower()
        name_lower = entity.name.lower() if entity.name else ""
        type_lower = entity.type.lower() if entity.type else ""

        if goal_type and goal_type.lower() in type_lower:
            return True
        if name_lower and name_lower in desc_lower:
            return True

        for val in entity.properties.values():
            if isinstance(val, str) and val.lower() in desc_lower:
                return True
        return False

    def health(self) -> dict[str, Any]:
        return {"alive": True}
