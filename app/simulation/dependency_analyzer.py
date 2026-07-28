from __future__ import annotations

import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.knowledge_graph.store import GraphStore


class ConflictSeverity(Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class DependencyNode:
    entity_id: str = ""
    entity_type: str = ""
    entity_name: str = ""
    depth: int = 0
    version: str = ""
    dependencies: list[DependencyNode] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "entity_type": self.entity_type,
            "entity_name": self.entity_name,
            "depth": self.depth,
            "version": self.version,
            "dependencies": [d.to_dict() for d in self.dependencies],
            "metadata": dict(self.metadata),
        }


@dataclass
class ConflictReport:
    artifact_id: str = ""
    cycles: list[list[str]] = field(default_factory=list)
    missing_dependencies: list[str] = field(default_factory=list)
    version_mismatches: list[dict[str, Any]] = field(default_factory=list)
    severity: ConflictSeverity = ConflictSeverity.NONE

    @property
    def has_conflicts(self) -> bool:
        return bool(self.cycles or self.missing_dependencies or self.version_mismatches)

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "cycles": [list(c) for c in self.cycles],
            "missing_dependencies": list(self.missing_dependencies),
            "version_mismatches": list(self.version_mismatches),
            "severity": self.severity.value,
            "has_conflicts": self.has_conflicts,
        }


class DependencyAnalyzer:
    """Traverse the Knowledge Graph to find all dependencies of an artifact.

    Uses 'depends_on' relationships to build a dependency tree. Detects
    cycles, missing dependencies, and generates a ConflictReport with
    severity scoring.

    Thread-safe.
    """

    def __init__(self, graph_store: GraphStore) -> None:
        self._graph = graph_store
        self._lock = threading.RLock()

    def analyze(self, entity_id: str, max_depth: int = 20) -> DependencyNode:
        """Build the full dependency tree starting from `entity_id`.

        Returns a ``DependencyNode`` representing the root artifact with
        nested children for each dependency.
        """
        with self._lock:
            visited: set[str] = set()
            return self._build_tree(entity_id, 0, max_depth, visited)

    def _build_tree(
        self,
        entity_id: str,
        depth: int,
        max_depth: int,
        visited: set[str],
    ) -> DependencyNode:
        entity = self._graph.get_entity(entity_id)
        if entity is None:
            return DependencyNode(entity_id=entity_id, depth=depth)

        node = DependencyNode(
            entity_id=entity.id,
            entity_type=entity.type,
            entity_name=entity.name,
            depth=depth,
            version=entity.properties.get("version", ""),
            metadata=dict(entity.properties),
        )

        if depth >= max_depth:
            return node

        visited.add(entity_id)
        outgoing = self._graph.get_outgoing_relationships(entity_id)
        dep_rels = [r for r in outgoing if r.get("type") == "depends_on"]

        for rel in dep_rels:
            target_id = rel.get("target_id", "")
            if target_id in visited:
                continue
            child = self._build_tree(target_id, depth + 1, max_depth, visited)
            node.dependencies.append(child)

        visited.discard(entity_id)
        return node

    def detect_cycles(self, entity_id: str) -> list[list[str]]:
        """Detect dependency cycles reachable from `entity_id`.

        Uses DFS with path tracking. Returns a list of cycles, where each
        cycle is a list of entity IDs forming the cycle.
        """
        with self._lock:
            cycles: list[list[str]] = []
            visited: set[str] = set()
            rec_stack: set[str] = set()
            path: list[str] = []
            self._dfs_cycles(entity_id, visited, rec_stack, path, cycles)
            return cycles

    def _dfs_cycles(
        self,
        entity_id: str,
        visited: set[str],
        rec_stack: set[str],
        path: list[str],
        cycles: list[list[str]],
    ) -> None:
        visited.add(entity_id)
        rec_stack.add(entity_id)
        path.append(entity_id)

        outgoing = self._graph.get_outgoing_relationships(entity_id)
        dep_rels = [r for r in outgoing if r.get("type") == "depends_on"]

        for rel in dep_rels:
            target_id = rel.get("target_id", "")
            if target_id not in visited:
                self._dfs_cycles(target_id, visited, rec_stack, path, cycles)
            elif target_id in rec_stack:
                cycle_start = path.index(target_id)
                cycles.append(list(path[cycle_start:]))

        path.pop()
        rec_stack.discard(entity_id)

    def find_missing_dependencies(self, entity_id: str) -> list[str]:
        """Find dependencies that reference non-existent entities."""
        with self._lock:
            missing: list[str] = []
            visited: set[str] = set()
            self._find_missing(entity_id, visited, missing)
            return missing

    def _find_missing(
        self,
        entity_id: str,
        visited: set[str],
        missing: list[str],
    ) -> None:
        if entity_id in visited:
            return
        visited.add(entity_id)

        outgoing = self._graph.get_outgoing_relationships(entity_id)
        dep_rels = [r for r in outgoing if r.get("type") == "depends_on"]

        for rel in dep_rels:
            target_id = rel.get("target_id", "")
            if self._graph.get_entity(target_id) is None:
                if target_id not in missing:
                    missing.append(target_id)
            else:
                self._find_missing(target_id, visited, missing)

    def generate_report(self, entity_id: str, max_depth: int = 20) -> ConflictReport:
        """Generate a complete conflict report for the artifact.

        Combines cycle detection, missing dependency scan, and version
        mismatch analysis into a single ``ConflictReport``.
        """
        with self._lock:
            cycles = self.detect_cycles(entity_id)
            missing = self.find_missing_dependencies(entity_id)
            version_mismatches = self._detect_version_mismatches(entity_id, max_depth)

            severity = self._compute_severity(cycles, missing, version_mismatches)

            return ConflictReport(
                artifact_id=entity_id,
                cycles=cycles,
                missing_dependencies=missing,
                version_mismatches=version_mismatches,
                severity=severity,
            )

    def _detect_version_mismatches(
        self,
        entity_id: str,
        max_depth: int,
    ) -> list[dict[str, Any]]:
        mismatches: list[dict[str, Any]] = []
        seen: set[str] = set()
        self._scan_versions(entity_id, 0, max_depth, seen, mismatches)
        return mismatches

    def _scan_versions(
        self,
        entity_id: str,
        depth: int,
        max_depth: int,
        seen: set[str],
        mismatches: list[dict[str, Any]],
    ) -> None:
        if entity_id in seen or depth > max_depth:
            return
        seen.add(entity_id)

        entity = self._graph.get_entity(entity_id)
        if entity is None:
            return

        outgoing = self._graph.get_outgoing_relationships(entity_id)
        dep_rels = [r for r in outgoing if r.get("type") == "depends_on"]

        for rel in dep_rels:
            target_id = rel.get("target_id", "")
            rel_props = rel.get("properties", {}) or {}
            required_version = rel_props.get("version_requirement", "")

            if required_version:
                target = self._graph.get_entity(target_id)
                if target is not None:
                    actual_version = target.properties.get("version", "")
                    if actual_version and actual_version != required_version:
                        mismatches.append({
                            "artifact_id": entity_id,
                            "dependency_id": target_id,
                            "required": required_version,
                            "actual": actual_version,
                        })

            self._scan_versions(target_id, depth + 1, max_depth, seen, mismatches)

    def _compute_severity(
        self,
        cycles: list[list[str]],
        missing: list[str],
        mismatches: list[dict[str, Any]],
    ) -> ConflictSeverity:
        if cycles:
            return ConflictSeverity.CRITICAL
        if missing:
            return ConflictSeverity.HIGH
        if len(mismatches) > 3:
            return ConflictSeverity.MEDIUM
        if mismatches:
            return ConflictSeverity.LOW
        return ConflictSeverity.NONE

    def health(self) -> dict[str, Any]:
        return {"alive": True, "store_entity_count": self._graph.entity_count()}
