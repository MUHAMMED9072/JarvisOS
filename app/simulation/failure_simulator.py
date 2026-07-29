from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any

from app.knowledge_graph.store import GraphStore
from app.simulation.dependency_analyzer import DependencyAnalyzer, DependencyNode


_FAILURE_SEVERITY_BY_TYPE: dict[str, float] = {
    "system": 1.0,
    "kernel": 0.9,
    "executive": 0.85,
    "governance": 0.8,
    "agent_framework": 0.7,
    "knowledge_graph": 0.8,
    "ads": 0.6,
    "simulation": 0.5,
    "tool": 0.4,
    "agent": 0.4,
    "skill": 0.3,
    "plugin": 0.3,
    "workflow": 0.25,
    "pipeline": 0.2,
    "concept": 0.1,
}


@dataclass
class CascadeNode:
    entity_id: str = ""
    entity_name: str = ""
    entity_type: str = ""
    depth: int = 0
    failure_probability: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "entity_name": self.entity_name,
            "entity_type": self.entity_type,
            "depth": self.depth,
            "failure_probability": self.failure_probability,
        }


@dataclass
class CascadeAnalysis:
    affected_entities: list[CascadeNode] = field(default_factory=list)
    total_affected: int = 0
    max_depth: int = 0
    critical_affected: int = 0
    cascade_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "affected_entities": [n.to_dict() for n in self.affected_entities],
            "total_affected": self.total_affected,
            "max_depth": self.max_depth,
            "critical_affected": self.critical_affected,
            "cascade_score": self.cascade_score,
        }


@dataclass
class DegradationAnalysis:
    can_operate_without: bool = True
    degraded_capabilities: list[str] = field(default_factory=list)
    critical_functions_lost: list[str] = field(default_factory=list)
    degradation_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "can_operate_without": self.can_operate_without,
            "degraded_capabilities": list(self.degraded_capabilities),
            "critical_functions_lost": list(self.critical_functions_lost),
            "degradation_score": self.degradation_score,
        }


@dataclass
class RecoveryAnalysis:
    can_recover: bool = True
    recovery_steps: list[str] = field(default_factory=list)
    estimated_recovery_time: str = ""
    recovery_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "can_recover": self.can_recover,
            "recovery_steps": list(self.recovery_steps),
            "estimated_recovery_time": self.estimated_recovery_time,
            "recovery_score": self.recovery_score,
        }


@dataclass
class FailureImpactReport:
    artifact_name: str = ""
    artifact_type: str = ""
    cascade: CascadeAnalysis = field(default_factory=CascadeAnalysis)
    degradation: DegradationAnalysis = field(default_factory=DegradationAnalysis)
    recovery: RecoveryAnalysis = field(default_factory=RecoveryAnalysis)
    failure_impact_score: float = 0.0
    passed: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_name": self.artifact_name,
            "artifact_type": self.artifact_type,
            "cascade": self.cascade.to_dict(),
            "degradation": self.degradation.to_dict(),
            "recovery": self.recovery.to_dict(),
            "failure_impact_score": self.failure_impact_score,
            "passed": self.passed,
        }


class FailureSimulator:
    """Simulate failure scenarios to understand impact when an artifact fails.

    Evaluates cascade effects, system degradation, and recovery
    feasibility.

    Thread-safe.
    """

    def __init__(
        self,
        graph_store: GraphStore | None = None,
        dependency_analyzer: DependencyAnalyzer | None = None,
    ) -> None:
        self._graph = graph_store
        self._dep_analyzer = dependency_analyzer or (
            DependencyAnalyzer(graph_store) if graph_store else None
        )
        self._lock = threading.RLock()

    def simulate(
        self,
        artifact_name: str = "",
        artifact_type: str = "agent",
        entity_id: str = "",
        dependencies: list[dict[str, Any]] | None = None,
    ) -> FailureImpactReport:
        cascade = self._analyze_cascade(entity_id, artifact_type, dependencies or [])
        degradation = self._analyze_degradation(entity_id, artifact_type, cascade)
        recovery = self._analyze_recovery(entity_id, artifact_type, cascade)

        cascade_score = cascade.cascade_score * 0.4
        degradation_score = degradation.degradation_score * 0.35
        recovery_score = recovery.recovery_score * 0.25

        failure_impact_score = min(1.0, cascade_score + degradation_score + recovery_score)

        return FailureImpactReport(
            artifact_name=artifact_name,
            artifact_type=artifact_type,
            cascade=cascade,
            degradation=degradation,
            recovery=recovery,
            failure_impact_score=failure_impact_score,
            passed=failure_impact_score < 0.7,
        )

    def _analyze_cascade(
        self,
        entity_id: str,
        artifact_type: str,
        dependencies: list[dict[str, Any]],
    ) -> CascadeAnalysis:
        affected: list[CascadeNode] = []
        seen: set[str] = set()

        if entity_id:
            self._traverse_cascade(entity_id, 0, seen, affected)

        if not affected and entity_id:
            pass

        total = len(affected)
        max_depth = max((n.depth for n in affected), default=0)
        critical = sum(1 for n in affected if n.failure_probability > 0.7)

        score = 0.0
        if total > 0:
            score += min(total * 0.05, 0.3)
            score += min(max_depth * 0.05, 0.2)
            score += min(critical * 0.1, 0.3)
            base = _FAILURE_SEVERITY_BY_TYPE.get(artifact_type, 0.3)
            score += base * 0.2
        score = min(1.0, score)

        return CascadeAnalysis(
            affected_entities=affected,
            total_affected=total,
            max_depth=max_depth,
            critical_affected=critical,
            cascade_score=score,
        )

    def _traverse_cascade(
        self,
        entity_id: str,
        depth: int,
        seen: set[str],
        affected: list[CascadeNode],
        max_depth: int = 10,
    ) -> None:
        if entity_id in seen or depth > max_depth:
            return
        seen.add(entity_id)

        if self._graph is None:
            return
        incoming = self._graph.get_incoming_relationships(entity_id)
        for rel in incoming:
            source_id = rel.get("source_id", "")
            if source_id in seen:
                continue
            source = self._graph.get_entity(source_id)
            if source is None:
                continue
            prob = self._failure_probability(source.type, depth)
            affected.append(CascadeNode(
                entity_id=source.id,
                entity_name=source.name,
                entity_type=source.type,
                depth=depth + 1,
                failure_probability=prob,
            ))
            self._traverse_cascade(source.id, depth + 1, seen, affected, max_depth)

    def _failure_probability(self, entity_type: str, depth: int) -> float:
        base = _FAILURE_SEVERITY_BY_TYPE.get(entity_type, 0.3)
        decay = max(0.1, 1.0 - depth * 0.15)
        return min(1.0, base * decay)

    def _analyze_degradation(
        self,
        entity_id: str,
        artifact_type: str,
        cascade: CascadeAnalysis,
    ) -> DegradationAnalysis:
        degraded: list[str] = []
        critical_lost: list[str] = []
        severity = _FAILURE_SEVERITY_BY_TYPE.get(artifact_type, 0.3)

        for node in cascade.affected_entities:
            if node.failure_probability > 0.5:
                degraded.append(f"{node.entity_type}:{node.entity_name or node.entity_id}")
            if node.failure_probability > 0.8:
                critical_lost.append(f"{node.entity_type}:{node.entity_name or node.entity_id}")

        score = 0.0
        if cascade.total_affected > 0:
            score = severity * 0.5
        if len(critical_lost) > 0:
            score += min(len(critical_lost) * 0.1, 0.3)
        if len(degraded) > 5:
            score += 0.2
        elif len(degraded) > 0:
            score += 0.1

        return DegradationAnalysis(
            can_operate_without=cascade.total_affected == 0,
            degraded_capabilities=degraded,
            critical_functions_lost=critical_lost,
            degradation_score=min(1.0, score),
        )

    def _analyze_recovery(
        self,
        entity_id: str,
        artifact_type: str,
        cascade: CascadeAnalysis,
    ) -> RecoveryAnalysis:
        steps: list[str] = []
        severity = _FAILURE_SEVERITY_BY_TYPE.get(artifact_type, 0.3)

        if cascade.total_affected > 0:
            steps.append("Stop all affected entities")
            steps.append("Isolate failing artifact")
            steps.append("Restore from backup or regenerate")

        if cascade.critical_affected > 0:
            steps.append("Restart critical system components")
            steps.append("Verify data integrity")
            steps.append("Gradually restart non-critical components")
            steps.insert(0, "Activate emergency fallback")
            est_time = "> 5 minutes"
            score = 0.7
        elif cascade.total_affected > 5:
            est_time = "2-5 minutes"
            score = 0.4
        elif cascade.total_affected > 0:
            est_time = "< 1 minute"
            score = 0.2
        else:
            est_time = "immediate"
            score = 0.0

        can_recover = severity < 0.9
        steps.append("Update Knowledge Graph with recovery status")

        return RecoveryAnalysis(
            can_recover=can_recover,
            recovery_steps=steps,
            estimated_recovery_time=est_time,
            recovery_score=score,
        )

    def health(self) -> dict[str, Any]:
        return {"alive": True}
