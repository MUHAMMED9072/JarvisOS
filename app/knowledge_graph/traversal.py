from __future__ import annotations

import heapq
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from app.knowledge_graph.store import GraphStore


@dataclass
class PathResult:
    nodes: list[str] = field(default_factory=list)
    edges: list[dict[str, Any]] = field(default_factory=list)
    total_weight: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": list(self.nodes),
            "edges": list(self.edges),
            "total_weight": self.total_weight,
        }


def shortest_path(
    store: GraphStore,
    start_id: str,
    end_id: str,
    max_depth: int = 20,
) -> PathResult | None:
    """BFS-based shortest path (unweighted). Returns None if no path."""
    if start_id == end_id:
        return PathResult(nodes=[start_id])

    visited: set[str] = set()
    queue: deque[tuple[str, list[str], list[dict[str, Any]]]] = deque()
    queue.append((start_id, [start_id], []))

    while queue:
        current, path, edges = queue.popleft()
        if current in visited:
            continue
        if len(path) > max_depth:
            continue
        visited.add(current)

        for rel in store.get_outgoing_relationships(current):
            nxt = rel["target_id"]
            if nxt in visited:
                continue
            new_path = path + [nxt]
            new_edges = edges + [rel]
            if nxt == end_id:
                return PathResult(nodes=new_path, edges=new_edges)
            queue.append((nxt, new_path, new_edges))

    return None


def all_paths(
    store: GraphStore,
    start_id: str,
    end_id: str,
    max_depth: int = 10,
) -> list[PathResult]:
    """Find all simple paths between start and end up to max_depth."""
    results: list[PathResult] = []

    def _dfs(current: str, target: str, path: list[str], edges: list[dict[str, Any]], depth: int) -> None:
        if depth > max_depth:
            return
        if current == target and path:
            results.append(PathResult(nodes=list(path), edges=list(edges)))
            return
        for rel in store.get_outgoing_relationships(current):
            nxt = rel["target_id"]
            if nxt in path:
                continue
            path.append(nxt)
            edges.append(rel)
            _dfs(nxt, target, path, edges, depth + 1)
            path.pop()
            edges.pop()

    _dfs(start_id, end_id, [start_id], [], 0)
    return results


def bfs_traverse(store: GraphStore, start_id: str, max_depth: int = 10) -> list[dict[str, Any]]:
    return store.bfs(start_id, max_depth=max_depth)


def dfs_traverse(store: GraphStore, start_id: str, max_depth: int = 10) -> list[dict[str, Any]]:
    return store.dfs(start_id, max_depth=max_depth)


def k_nearest_neighbors(
    store: GraphStore,
    entity_id: str,
    k: int = 5,
    max_depth: int = 5,
) -> list[dict[str, Any]]:
    """Find k nearest neighbor entities via BFS."""
    visited: set[str] = set()
    queue: deque[tuple[str, int]] = deque()
    queue.append((entity_id, 0))
    neighbors: list[dict[str, Any]] = []

    while queue and len(neighbors) < k:
        current, depth = queue.popleft()
        if current in visited or depth > max_depth:
            continue
        visited.add(current)

        for rel in store.get_outgoing_relationships(current):
            nxt = rel["target_id"]
            if nxt not in visited and len(neighbors) < k:
                entry = store.get_entity(nxt)
                if entry:
                    neighbors.append({
                        "entity": entry.to_dict(),
                        "relationship": rel,
                        "distance": depth + 1,
                    })
                queue.append((nxt, depth + 1))

    return neighbors


def extract_subgraph(
    store: GraphStore,
    center_id: str,
    radius: int = 2,
    max_nodes: int = 100,
) -> dict[str, Any]:
    """Extract connected subgraph around a center node up to given radius."""
    entities: dict[str, Any] = {}
    relationships: list[dict[str, Any]] = []
    visited: set[str] = set()
    queue: deque[tuple[str, int]] = deque()
    queue.append((center_id, 0))
    visited.add(center_id)

    center = store.get_entity(center_id)
    if center:
        entities[center.id] = center.to_dict()

    while queue and len(entities) < max_nodes:
        current, depth = queue.popleft()
        if depth >= radius:
            continue

        for rel in store.get_outgoing_relationships(current):
            nxt = rel["target_id"]
            relationships.append(rel)
            if nxt not in visited and len(entities) < max_nodes:
                visited.add(nxt)
                ent = store.get_entity(nxt)
                if ent:
                    entities[ent.id] = ent.to_dict()
                queue.append((nxt, depth + 1))

        for rel in store.get_incoming_relationships(current):
            nxt = rel["source_id"]
            relationships.append(rel)
            if nxt not in visited and len(entities) < max_nodes:
                visited.add(nxt)
                ent = store.get_entity(nxt)
                if ent:
                    entities[ent.id] = ent.to_dict()
                queue.append((nxt, depth + 1))

    return {
        "center_id": center_id,
        "entities": list(entities.values()),
        "relationships": relationships,
        "node_count": len(entities),
        "edge_count": len(relationships),
    }
