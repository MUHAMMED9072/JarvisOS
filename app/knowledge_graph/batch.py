from __future__ import annotations

import time
from typing import Any

from app.knowledge_graph.cascade import validate_and_create
from app.knowledge_graph.store import GraphStore


class BatchResult:
    """Result of a batch operation."""

    def __init__(self) -> None:
        self.created: int = 0
        self.skipped: int = 0
        self.errors: list[dict[str, Any]] = []
        self.duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "created": self.created,
            "skipped": self.skipped,
            "errors": list(self.errors),
            "duration_ms": self.duration_ms,
        }


def batch_create_relationships(
    store: GraphStore,
    relationships: list[dict[str, Any]],
    check_cycle: bool = False,
    continue_on_error: bool = True,
) -> BatchResult:
    """Create multiple relationships in batch.

    Each relationship is a dict with keys: type, source_id, target_id,
    and optional properties.
    """
    result = BatchResult()
    start = time.time()

    for i, rel in enumerate(relationships):
        rtype = rel.get("type", "related_to")
        source_id = rel.get("source_id", "")
        target_id = rel.get("target_id", "")
        properties = rel.get("properties")

        if not source_id or not target_id:
            result.skipped += 1
            result.errors.append({
                "index": i, "error": "Missing source_id or target_id",
            })
            if not continue_on_error:
                break
            continue

        try:
            validate_and_create(
                store, rtype, source_id, target_id,
                properties=properties, check_cycle=check_cycle,
            )
            result.created += 1
        except Exception as e:
            result.skipped += 1
            result.errors.append({
                "index": i, "error": str(e),
                "type": rtype, "source": source_id, "target": target_id,
            })
            if not continue_on_error:
                break

    result.duration_ms = (time.time() - start) * 1000.0
    return result


def batch_delete_relationships(
    store: GraphStore,
    rel_ids: list[str],
    continue_on_error: bool = True,
) -> BatchResult:
    """Delete multiple relationships by ID."""
    result = BatchResult()
    start = time.time()

    for i, rid in enumerate(rel_ids):
        try:
            if store.delete_relationship(rid):
                result.created += 1
            else:
                result.skipped += 1
        except Exception as e:
            result.skipped += 1
            result.errors.append({
                "index": i, "error": str(e), "rel_id": rid,
            })
            if not continue_on_error:
                break

    result.duration_ms = (time.time() - start) * 1000.0
    return result
