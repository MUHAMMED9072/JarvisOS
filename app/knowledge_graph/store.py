from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.event_bus import EventBus
from app.core.logger import JarvisLogger

from .entity import Entity
from .index import EntityIndex, RelationshipIndex
from .relationship import Relationship
from .schema import ENTITY_TYPES, RELATIONSHIP_TYPES


class KnowledgeGraphEvents:
    ENTITY_CREATED = "knowledge_graph.entity.created"
    ENTITY_UPDATED = "knowledge_graph.entity.updated"
    ENTITY_DELETED = "knowledge_graph.entity.deleted"
    RELATIONSHIP_CREATED = "knowledge_graph.relationship.created"
    RELATIONSHIP_UPDATED = "knowledge_graph.relationship.updated"
    RELATIONSHIP_DELETED = "knowledge_graph.relationship.deleted"
    TRANSACTION_COMMITTED = "knowledge_graph.transaction.committed"
    TRANSACTION_ROLLED_BACK = "knowledge_graph.transaction.rolled_back"
    STORE_CLEARED = "knowledge_graph.store.cleared"


@dataclass
class GraphTransaction:
    pending_entities: dict[str, Entity] = field(default_factory=dict)
    deleted_entity_ids: set[str] = field(default_factory=set)
    pending_relationships: dict[str, Relationship] = field(default_factory=dict)
    deleted_relationship_ids: set[str] = field(default_factory=set)
    _committed: bool = False

    def commit(self) -> None:
        self._committed = True

    @property
    def is_committed(self) -> bool:
        return self._committed


class GraphStore:
    """Core storage and query engine for the Knowledge Graph.

    Provides entity/relationship CRUD, in-memory indexes, atomic JSON
    persistence, transaction support, and event publishing.
    """

    def __init__(
        self,
        filename: str = "knowledge_graph.json",
        event_bus: EventBus | None = None,
    ) -> None:
        self.path = Path("data") / "knowledge_graph" / filename
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._event_bus = event_bus

        self._entity_index = EntityIndex()
        self._relationship_index = RelationshipIndex()
        self._lock = threading.RLock()

        self._load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for item in data.get("entities", []):
                entity = Entity.from_dict(item)
                self._entity_index.add(entity)
            for item in data.get("relationships", []):
                rel = Relationship.from_dict(item)
                self._relationship_index.add(
                    rel.id, rel.type, rel.source_id, rel.target_id, rel.to_dict()
                )
        except Exception:
            JarvisLogger.exception("GraphStore: failed to load data")

    def save(self) -> None:
        data: dict[str, Any] = {
            "entities": [e.to_dict() for e in self._entity_index.all()],
            "relationships": [],
        }
        # Collect relationships from index
        visited: set[str] = set()
        for entry in self._entity_index.all():
            for rel_data in self._relationship_index.get_outgoing(entry.id):
                if rel_data["id"] not in visited:
                    visited.add(rel_data["id"])
                    data["relationships"].append(rel_data)
        for entry in self._entity_index.all():
            for rel_data in self._relationship_index.get_incoming(entry.id):
                if rel_data["id"] not in visited:
                    visited.add(rel_data["id"])
                    data["relationships"].append(rel_data)

        fd, tmp = tempfile.mkstemp(
            dir=str(self.path.parent), prefix=".tmp_", suffix=".json"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(tmp, str(self.path))
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    # ------------------------------------------------------------------
    # Entity CRUD
    # ------------------------------------------------------------------

    def create_entity(
        self,
        type: str = "concept",
        name: str = "",
        properties: dict[str, Any] | None = None,
        id: str | None = None,
    ) -> Entity:
        if not ENTITY_TYPES.is_valid(type):
            raise ValueError(f"Invalid entity type '{type}'")
        entity = Entity.create(type=type, name=name, properties=properties, id=id)
        with self._lock:
            self._entity_index.add(entity)
        self._publish(KnowledgeGraphEvents.ENTITY_CREATED, entity=entity.to_dict())
        return entity

    def get_entity(self, entity_id: str) -> Entity | None:
        return self._entity_index.get_by_id(entity_id)

    def get_entity_by_name(self, name: str) -> list[Entity]:
        return self._entity_index.get_by_name(name)

    def get_entities_by_type(self, type_name: str) -> list[Entity]:
        return self._entity_index.get_by_type(type_name)

    def list_entities(self) -> list[Entity]:
        return self._entity_index.all()

    def update_entity(
        self,
        entity_id: str,
        name: str | None = None,
        properties: dict[str, Any] | None = None,
    ) -> Entity | None:
        with self._lock:
            entity = self._entity_index.get_by_id(entity_id)
            if entity is None:
                return None
            if name is not None:
                entity.name = name
            if properties is not None:
                entity.properties.update(properties)
            entity.updated = datetime.now(timezone.utc).isoformat()
            self._entity_index.update(entity)
        self._publish(KnowledgeGraphEvents.ENTITY_UPDATED, entity=entity.to_dict())
        return entity

    def delete_entity(self, entity_id: str) -> bool:
        with self._lock:
            entity = self._entity_index.remove(entity_id)
            if entity is None:
                return False
            # Cascade delete relationships
            for rel_data in self._relationship_index.get_outgoing(entity_id):
                self._relationship_index.remove(rel_data["id"])
            for rel_data in self._relationship_index.get_incoming(entity_id):
                self._relationship_index.remove(rel_data["id"])
        self._publish(KnowledgeGraphEvents.ENTITY_DELETED, entity_id=entity_id)
        return True

    def entity_count(self) -> int:
        return self._entity_index.count()

    # ------------------------------------------------------------------
    # Relationship CRUD
    # ------------------------------------------------------------------

    def create_relationship(
        self,
        type: str = "related_to",
        source_id: str = "",
        target_id: str = "",
        properties: dict[str, Any] | None = None,
        id: str | None = None,
    ) -> Relationship:
        if not RELATIONSHIP_TYPES.is_valid(type):
            raise ValueError(f"Invalid relationship type '{type}'")

        # Validate source and target exist
        source = self._entity_index.get_by_id(source_id)
        if source is None:
            raise ValueError(f"Source entity '{source_id}' not found")
        target = self._entity_index.get_by_id(target_id)
        if target is None:
            raise ValueError(f"Target entity '{target_id}' not found")

        rel = Relationship.create(
            type=type, source_id=source_id, target_id=target_id,
            properties=properties, id=id,
        )
        with self._lock:
            self._relationship_index.add(
                rel.id, rel.type, rel.source_id, rel.target_id, rel.to_dict()
            )
        self._publish(
            KnowledgeGraphEvents.RELATIONSHIP_CREATED,
            relationship=rel.to_dict(),
        )
        return rel

    def get_relationship(self, rel_id: str) -> dict[str, Any] | None:
        return self._relationship_index.get(rel_id)

    def get_outgoing_relationships(self, entity_id: str) -> list[dict[str, Any]]:
        return self._relationship_index.get_outgoing(entity_id)

    def get_incoming_relationships(self, entity_id: str) -> list[dict[str, Any]]:
        return self._relationship_index.get_incoming(entity_id)

    def get_relationships_by_type(self, rel_type: str) -> list[dict[str, Any]]:
        return self._relationship_index.get_by_type(rel_type)

    def update_relationship(
        self,
        rel_id: str,
        properties: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        with self._lock:
            entry = self._relationship_index.get(rel_id)
            if entry is None:
                return None
            if properties:
                rel_props = entry.setdefault("properties", {})
                rel_props.update(properties)
            entry["updated"] = datetime.now(timezone.utc).isoformat()
        self._publish(KnowledgeGraphEvents.RELATIONSHIP_UPDATED, relationship_id=rel_id)
        return entry

    def delete_relationship(self, rel_id: str) -> bool:
        with self._lock:
            result = self._relationship_index.remove(rel_id)
        if result:
            self._publish(KnowledgeGraphEvents.RELATIONSHIP_DELETED, relationship_id=rel_id)
        return result

    def relationship_count(self) -> int:
        return self._relationship_index.count()

    # ------------------------------------------------------------------
    # Traversal
    # ------------------------------------------------------------------

    def bfs(self, start_id: str, max_depth: int = 10) -> list[dict[str, Any]]:
        return self._relationship_index.bfs(start_id, max_depth=max_depth)

    def dfs(self, start_id: str, max_depth: int = 10) -> list[dict[str, Any]]:
        return self._relationship_index.dfs(start_id, max_depth=max_depth)

    # ------------------------------------------------------------------
    # Transactions
    # ------------------------------------------------------------------

    def begin_transaction(self) -> GraphTransaction:
        return GraphTransaction()

    def commit_transaction(self, tx: GraphTransaction) -> None:
        if tx.is_committed:
            return
        with self._lock:
            for eid in tx.deleted_entity_ids:
                self._entity_index.remove(eid)
            for eid, entity in tx.pending_entities.items():
                self._entity_index.add(entity)
            for rid in tx.deleted_relationship_ids:
                self._relationship_index.remove(rid)
            for rid, rel in tx.pending_relationships.items():
                self._relationship_index.add(
                    rel.id, rel.type, rel.source_id, rel.target_id, rel.to_dict()
                )
        tx.commit()
        self._publish(KnowledgeGraphEvents.TRANSACTION_COMMITTED)

    def rollback_transaction(self, tx: GraphTransaction) -> None:
        if tx.is_committed:
            return
        tx.pending_entities.clear()
        tx.deleted_entity_ids.clear()
        tx.pending_relationships.clear()
        tx.deleted_relationship_ids.clear()
        self._publish(KnowledgeGraphEvents.TRANSACTION_ROLLED_BACK)

    # ------------------------------------------------------------------
    # Admin
    # ------------------------------------------------------------------

    def clear(self) -> None:
        with self._lock:
            self._entity_index.clear()
            self._relationship_index.clear()
        self._publish(KnowledgeGraphEvents.STORE_CLEARED)

    def search(self, query: str) -> list[Entity]:
        q = query.lower()
        results: list[Entity] = []
        for entity in self._entity_index.all():
            if q in entity.name.lower() or q in entity.type.lower():
                results.append(entity)
                continue
            for key, value in entity.properties.items():
                if isinstance(value, str) and q in value.lower():
                    results.append(entity)
                    break
        return results

    def health(self) -> dict[str, Any]:
        return {
            "alive": True,
            "entity_count": self._entity_index.count(),
            "relationship_count": self._relationship_index.count(),
            "path": str(self.path),
        }

    def _publish(self, event: str, **data: Any) -> None:
        if self._event_bus:
            self._event_bus.publish(event, **data)
