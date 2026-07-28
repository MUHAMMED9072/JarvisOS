from __future__ import annotations

from collections import deque
from typing import Any

from app.knowledge_graph.store import GraphStore


class CircularDependencyError(ValueError):
    """Raised when adding a relationship would create a circular dependency."""

    def __init__(self, source_id: str, target_id: str, path: list[str]) -> None:
        self.source_id = source_id
        self.target_id = target_id
        self.path = path
        super().__init__(
            f"Circular dependency detected: adding {source_id} -> {target_id} "
            f"would create cycle: {' -> '.join(path)}"
        )


def would_create_cycle(
    store: GraphStore,
    source_id: str,
    target_id: str,
    max_depth: int = 50,
) -> list[str]:
    """Check if adding a relationship source_id -> target_id would create
    a cycle.  Returns the cycle path if one exists, empty list otherwise.

    Uses BFS from target_id to see if source_id is reachable.
    """
    if source_id == target_id:
        return [source_id, target_id]

    visited: set[str] = set()
    parent: dict[str, str | None] = {target_id: None}
    queue: deque[str] = deque([target_id])

    while queue and len(visited) < max_depth:
        current = queue.popleft()
        if current in visited:
            continue
        visited.add(current)

        for rel in store.get_outgoing_relationships(current):
            nxt = rel["target_id"]
            if nxt in visited:
                continue
            parent[nxt] = current
            if nxt == source_id:
                # Reconstruct path
                path: list[str] = [source_id]
                node = current
                while node is not None:
                    path.append(node)
                    node = parent.get(node)
                path.reverse()
                return path
            queue.append(nxt)

    return []


def validate_and_create(
    store: GraphStore,
    rel_type: str,
    source_id: str,
    target_id: str,
    properties: dict[str, Any] | None = None,
    check_cycle: bool = True,
) -> Any:
    """Create a relationship with optional cycle detection."""
    if check_cycle:
        cycle = would_create_cycle(store, source_id, target_id)
        if cycle:
            raise CircularDependencyError(source_id, target_id, cycle)
    return store.create_relationship(
        type=rel_type,
        source_id=source_id,
        target_id=target_id,
        properties=properties,
    )
