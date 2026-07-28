from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.knowledge_graph.pattern_matcher import PatternMatcher, PatternTemplate, MatchResult
from app.knowledge_graph.store import GraphStore
from app.knowledge_graph.traversal import (
    PathResult,
    all_paths,
    bfs_traverse,
    dfs_traverse,
    extract_subgraph,
    k_nearest_neighbors,
    shortest_path,
)


@dataclass
class QueryResult:
    success: bool = True
    data: Any = None
    error: str = ""
    execution_time_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "execution_time_ms": self.execution_time_ms,
        }


class QueryEngine:
    """Declarative graph query API.

    Provides high-level query methods: entity lookup, traversal, path
    finding, subgraph extraction, and pattern matching.
    """

    def __init__(self, store: GraphStore) -> None:
        self._store = store
        self._pattern_matcher = PatternMatcher(store)

    def get_entity(self, entity_id: str) -> QueryResult:
        entity = self._store.get_entity(entity_id)
        if entity is None:
            return QueryResult(success=False, error=f"Entity '{entity_id}' not found")
        return QueryResult(data=entity.to_dict())

    def find_entities(self, type: str | None = None, name: str | None = None) -> QueryResult:
        if name:
            entities = self._store.get_entity_by_name(name)
        elif type:
            entities = self._store.get_entities_by_type(type)
        else:
            entities = self._store.list_entities()
        return QueryResult(data=[e.to_dict() for e in entities])

    def search(self, query: str) -> QueryResult:
        entities = self._store.search(query)
        return QueryResult(data=[e.to_dict() for e in entities])

    def get_relationships(self, entity_id: str) -> QueryResult:
        outgoing = self._store.get_outgoing_relationships(entity_id)
        incoming = self._store.get_incoming_relationships(entity_id)
        return QueryResult(data={
            "outgoing": list(outgoing),
            "incoming": list(incoming),
        })

    def bfs(self, start_id: str, max_depth: int = 10) -> QueryResult:
        data = bfs_traverse(self._store, start_id, max_depth=max_depth)
        return QueryResult(data=data)

    def dfs(self, start_id: str, max_depth: int = 10) -> QueryResult:
        data = dfs_traverse(self._store, start_id, max_depth=max_depth)
        return QueryResult(data=data)

    def shortest_path(self, start_id: str, end_id: str, max_depth: int = 20) -> QueryResult:
        path = shortest_path(self._store, start_id, end_id, max_depth=max_depth)
        if path is None:
            return QueryResult(success=False, data=None, error="No path found")
        return QueryResult(data=path.to_dict())

    def all_paths(self, start_id: str, end_id: str, max_depth: int = 10) -> QueryResult:
        paths = all_paths(self._store, start_id, end_id, max_depth=max_depth)
        return QueryResult(data=[p.to_dict() for p in paths])

    def k_nearest(self, entity_id: str, k: int = 5, max_depth: int = 5) -> QueryResult:
        neighbors = k_nearest_neighbors(self._store, entity_id, k=k, max_depth=max_depth)
        return QueryResult(data=neighbors)

    def subgraph(self, center_id: str, radius: int = 2, max_nodes: int = 100) -> QueryResult:
        sg = extract_subgraph(self._store, center_id, radius=radius, max_nodes=max_nodes)
        return QueryResult(data=sg)

    def match_pattern(self, pattern: PatternTemplate, max_results: int = 50) -> QueryResult:
        matches = self._pattern_matcher.match(pattern, max_results=max_results)
        return QueryResult(data=[m.to_dict() for m in matches])

    @property
    def store(self) -> GraphStore:
        return self._store
