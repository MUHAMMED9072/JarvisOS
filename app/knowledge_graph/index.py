from __future__ import annotations

from collections import defaultdict
from threading import Lock
from typing import Any

from .entity import Entity


class EntityIndex:
    """In-memory indexes for O(1) entity lookups by ID, name, and type."""

    def __init__(self) -> None:
        self._by_id: dict[str, Entity] = {}
        self._by_name: dict[str, list[str]] = defaultdict(list)
        self._by_type: dict[str, list[str]] = defaultdict(list)
        self._snapshots: dict[str, tuple[str, str]] = {}  # entity_id -> (name, type)
        self._lock = Lock()

    def add(self, entity: Entity) -> None:
        with self._lock:
            self._by_id[entity.id] = entity
            self._by_name[entity.name].append(entity.id)
            self._by_type[entity.type].append(entity.id)
            self._snapshots[entity.id] = (entity.name, entity.type)

    def remove(self, entity_id: str) -> Entity | None:
        with self._lock:
            entity = self._by_id.pop(entity_id, None)
            if entity is not None:
                snap = self._snapshots.pop(entity_id, None)
                old_name = snap[0] if snap else entity.name
                old_type = snap[1] if snap else entity.type
                name_ids = self._by_name.get(old_name)
                if name_ids:
                    try:
                        name_ids.remove(entity_id)
                    except ValueError:
                        pass
                type_ids = self._by_type.get(old_type)
                if type_ids:
                    try:
                        type_ids.remove(entity_id)
                    except ValueError:
                        pass
            return entity

    def update(self, entity: Entity) -> None:
        with self._lock:
            snap = self._snapshots.get(entity.id)
            if snap is not None:
                old_name, old_type = snap
                if old_name != entity.name:
                    name_ids = self._by_name.get(old_name)
                    if name_ids:
                        try:
                            name_ids.remove(entity.id)
                        except ValueError:
                            pass
                    self._by_name[entity.name].append(entity.id)
                if old_type != entity.type:
                    type_ids = self._by_type.get(old_type)
                    if type_ids:
                        try:
                            type_ids.remove(entity.id)
                        except ValueError:
                            pass
                    self._by_type[entity.type].append(entity.id)
                self._snapshots[entity.id] = (entity.name, entity.type)
            else:
                self._by_name[entity.name].append(entity.id)
                self._by_type[entity.type].append(entity.id)
                self._snapshots[entity.id] = (entity.name, entity.type)
            self._by_id[entity.id] = entity

    def get_by_id(self, entity_id: str) -> Entity | None:
        with self._lock:
            return self._by_id.get(entity_id)

    def get_by_name(self, name: str) -> list[Entity]:
        with self._lock:
            return [self._by_id[eid] for eid in self._by_name.get(name, []) if eid in self._by_id]

    def get_by_type(self, type_name: str) -> list[Entity]:
        with self._lock:
            return [self._by_id[eid] for eid in self._by_type.get(type_name, []) if eid in self._by_id]

    def count(self) -> int:
        with self._lock:
            return len(self._by_id)

    def clear(self) -> None:
        with self._lock:
            self._by_id.clear()
            self._by_name.clear()
            self._by_type.clear()

    def all(self) -> list[Entity]:
        with self._lock:
            return list(self._by_id.values())


class RelationshipIndex:
    """Adjacency list for relationship traversal."""

    def __init__(self) -> None:
        self._by_id: dict[str, dict[str, Any]] = {}
        self._outgoing: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._incoming: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._by_type: dict[str, list[str]] = defaultdict(list)
        self._lock = Lock()

    def add(self, rel_id: str, rel_type: str, source_id: str, target_id: str, data: dict[str, Any]) -> None:
        entry = {
            "id": rel_id,
            "type": rel_type,
            "source_id": source_id,
            "target_id": target_id,
            **data,
        }
        with self._lock:
            self._by_id[rel_id] = entry
            self._outgoing[source_id].append(entry)
            self._incoming[target_id].append(entry)
            self._by_type[rel_type].append(rel_id)

    def remove(self, rel_id: str) -> bool:
        with self._lock:
            entry = self._by_id.pop(rel_id, None)
            if entry is None:
                return False
            self._remove_from_list(self._outgoing[entry["source_id"]], rel_id)
            self._remove_from_list(self._incoming[entry["target_id"]], rel_id)
            type_ids = self._by_type.get(entry["type"])
            if type_ids:
                try:
                    type_ids.remove(rel_id)
                except ValueError:
                    pass
            return True

    def _remove_from_list(self, lst: list[dict[str, Any]], rel_id: str) -> None:
        for i, entry in enumerate(lst):
            if entry["id"] == rel_id:
                lst.pop(i)
                break

    def get(self, rel_id: str) -> dict[str, Any] | None:
        with self._lock:
            return self._by_id.get(rel_id)

    def get_outgoing(self, entity_id: str) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._outgoing.get(entity_id, []))

    def get_incoming(self, entity_id: str) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._incoming.get(entity_id, []))

    def get_by_type(self, rel_type: str) -> list[dict[str, Any]]:
        with self._lock:
            return [self._by_id[rid] for rid in self._by_type.get(rel_type, []) if rid in self._by_id]

    def clear(self) -> None:
        with self._lock:
            self._by_id.clear()
            self._outgoing.clear()
            self._incoming.clear()
            self._by_type.clear()

    def count(self) -> int:
        with self._lock:
            return len(self._by_id)

    def bfs(self, start_id: str, max_depth: int = 10) -> list[dict[str, Any]]:
        visited: set[str] = set()
        queue: list[tuple[str, int]] = [(start_id, 0)]
        results: list[dict[str, Any]] = []

        while queue:
            current, depth = queue.pop(0)
            if current in visited or depth > max_depth:
                continue
            visited.add(current)

            with self._lock:
                neighbors = list(self._outgoing.get(current, []))

            next_depth = depth + 1
            for edge in neighbors:
                if next_depth <= max_depth:
                    results.append(edge)
                    queue.append((edge["target_id"], next_depth))

        return results

    def dfs(self, start_id: str, max_depth: int = 10) -> list[dict[str, Any]]:
        visited: set[str] = set()
        stack: list[tuple[str, int]] = [(start_id, 0)]
        results: list[dict[str, Any]] = []

        while stack:
            current, depth = stack.pop()
            if current in visited or depth > max_depth:
                continue
            visited.add(current)

            with self._lock:
                neighbors = list(self._outgoing.get(current, []))

            next_depth = depth + 1
            for edge in neighbors:
                if next_depth <= max_depth:
                    results.append(edge)
                    stack.append((edge["target_id"], next_depth))

        return results
