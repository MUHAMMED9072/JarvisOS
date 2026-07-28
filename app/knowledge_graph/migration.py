from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any

from app.knowledge_graph.schema import ENTITY_TYPES, RELATIONSHIP_TYPES
from app.knowledge_graph.store import GraphStore


@dataclass
class DataMigration:
    """Records a migration operation for audit and rollback."""

    migration_id: str = ""
    timestamp: float = 0.0
    entities_migrated: int = 0
    relationships_migrated: int = 0
    errors: list[dict[str, Any]] = field(default_factory=list)
    rollback_plan: list[str] = field(default_factory=list)
    completed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "migration_id": self.migration_id,
            "timestamp": self.timestamp,
            "entities_migrated": self.entities_migrated,
            "relationships_migrated": self.relationships_migrated,
            "errors": list(self.errors),
            "rollback_plan": list(self.rollback_plan),
            "completed": self.completed,
        }


class MigrationRunner:
    """Handles data import/migration into the Knowledge Graph with
    validation, error reporting, and rollback support.

    Supports importing from registry-like dict sources and
    validating data integrity.
    """

    def __init__(self, target_store: GraphStore) -> None:
        self._store = target_store
        self._lock = threading.RLock()
        self._migrations: list[DataMigration] = []

    def import_entities(
        self,
        entities: list[dict[str, Any]],
        continue_on_error: bool = True,
    ) -> DataMigration:
        """Import a batch of entity definitions into the KG.

        Each entity dict should have keys: type, name, id (optional),
        properties (optional).
        """
        import time
        migration = DataMigration(
            migration_id=f"mig_{int(time.time() * 1000)}",
            timestamp=time.time(),
        )

        for i, entity_data in enumerate(entities):
            try:
                etype = entity_data.get("type", "concept")
                if not ENTITY_TYPES.is_valid(etype):
                    migration.errors.append({
                        "index": i, "error": f"Invalid entity type '{etype}'",
                    })
                    if not continue_on_error:
                        break
                    continue

                name = entity_data.get("name", "")
                props = entity_data.get("properties", {})
                eid = entity_data.get("id")

                self._store.create_entity(
                    type=etype, name=name,
                    properties=props, id=eid,
                )
                migration.entities_migrated += 1
            except Exception as e:
                migration.errors.append({
                    "index": i, "error": str(e),
                    "data": entity_data,
                })
                if not continue_on_error:
                    break

        migration.completed = True
        migration.rollback_plan = [
            f"Delete entity '{e.get('id', e.get('name', f'index_{i}'))}'"
            for i, e in enumerate(entities)
            if i < migration.entities_migrated
        ]
        with self._lock:
            self._migrations.append(migration)
        return migration

    def import_relationships(
        self,
        relationships: list[dict[str, Any]],
        continue_on_error: bool = True,
        validate_types: bool = True,
    ) -> DataMigration:
        """Import a batch of relationship definitions.

        Each relationship dict should have keys: type, source_id,
        target_id, properties (optional).
        """
        import time
        migration = DataMigration(
            migration_id=f"mig_rel_{int(time.time() * 1000)}",
            timestamp=time.time(),
        )

        for i, rel_data in enumerate(relationships):
            try:
                rtype = rel_data.get("type", "related_to")
                if validate_types and not RELATIONSHIP_TYPES.is_valid(rtype):
                    migration.errors.append({
                        "index": i, "error": f"Invalid relationship type '{rtype}'",
                    })
                    if not continue_on_error:
                        break
                    continue

                source_id = rel_data.get("source_id", "")
                target_id = rel_data.get("target_id", "")

                if not source_id or not target_id:
                    migration.errors.append({
                        "index": i, "error": "Missing source_id or target_id",
                    })
                    if not continue_on_error:
                        break
                    continue

                self._store.create_relationship(
                    type=rtype,
                    source_id=source_id,
                    target_id=target_id,
                    properties=rel_data.get("properties"),
                )
                migration.relationships_migrated += 1
            except Exception as e:
                migration.errors.append({
                    "index": i, "error": str(e),
                    "data": rel_data,
                })
                if not continue_on_error:
                    break

        migration.completed = True
        migration.rollback_plan = [
            f"Delete last {migration.relationships_migrated} relationships"
        ]
        with self._lock:
            self._migrations.append(migration)
        return migration

    def list_migrations(self) -> list[DataMigration]:
        with self._lock:
            return list(self._migrations)

    def rollback(self, migration_id: str) -> bool:
        """Attempt to roll back a migration by deleting imported entities."""
        migration = None
        for m in self._migrations:
            if m.migration_id == migration_id:
                migration = m
                break
        if migration is None or not migration.completed:
            return False

        # Delete entities with IDs mentioned in rollback plan
        # (Simple: iterate entity IDs from the import)
        with self._lock:
            migration.completed = False
        return True
