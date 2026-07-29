from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any

from app.knowledge_graph.store import GraphStore
from app.simulation.compatibility_checker import CompatibilityChecker, CompatibilityResult
from app.simulation.dependency_analyzer import DependencyAnalyzer


_SCOPE_WEIGHTS: dict[str, float] = {
    "system": 1.0,
    "governance": 0.9,
    "kernel": 0.9,
    "executive": 0.85,
    "agent_framework": 0.7,
    "knowledge_graph": 0.6,
    "ads": 0.5,
    "simulation": 0.4,
    "tool": 0.3,
    "agent": 0.3,
    "skill": 0.2,
    "plugin": 0.2,
    "workflow": 0.15,
    "pipeline": 0.1,
}


@dataclass
class DependencyDepthAnalysis:
    max_depth: int = 0
    avg_depth: float = 0.0
    total_dependencies: int = 0
    depth_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_depth": self.max_depth,
            "avg_depth": self.avg_depth,
            "total_dependencies": self.total_dependencies,
            "depth_score": self.depth_score,
        }


@dataclass
class ScopeAnalysis:
    affected_entities: int = 0
    affected_types: dict[str, int] = field(default_factory=dict)
    scope_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "affected_entities": self.affected_entities,
            "affected_types": dict(self.affected_types),
            "scope_score": self.scope_score,
        }


@dataclass
class HistoricalMatch:
    pattern: str = ""
    match_count: int = 0
    regression_count: int = 0
    regression_rate: float = 0.0
    score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "pattern": self.pattern,
            "match_count": self.match_count,
            "regression_count": self.regression_count,
            "regression_rate": self.regression_rate,
            "score": self.score,
        }


@dataclass
class RegressionRiskReport:
    artifact_name: str = ""
    artifact_type: str = ""
    dependency_depth: DependencyDepthAnalysis = field(default_factory=DependencyDepthAnalysis)
    scope: ScopeAnalysis = field(default_factory=ScopeAnalysis)
    historical_matches: list[HistoricalMatch] = field(default_factory=list)
    risk_score: float = 0.0
    passed: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_name": self.artifact_name,
            "artifact_type": self.artifact_type,
            "dependency_depth": self.dependency_depth.to_dict(),
            "scope": self.scope.to_dict(),
            "historical_matches": [m.to_dict() for m in self.historical_matches],
            "risk_score": self.risk_score,
            "passed": self.passed,
        }


class RegressionScorer:
    """Score the risk of regression (breaking existing functionality).

    Evaluates dependency depth, scope of affected entities, and
    historical regression patterns.

    Thread-safe.
    """

    def __init__(
        self,
        graph_store: GraphStore | None = None,
        dependency_analyzer: DependencyAnalyzer | None = None,
        compatibility_checker: CompatibilityChecker | None = None,
    ) -> None:
        self._graph = graph_store
        self._dep_analyzer = dependency_analyzer or (
            DependencyAnalyzer(graph_store) if graph_store else None
        )
        self._compat = compatibility_checker or CompatibilityChecker()
        self._lock = threading.RLock()
        self._history: list[dict[str, Any]] = []
        self._min_risk = 0.0
        self._max_risk = 1.0

    def score(
        self,
        artifact_name: str = "",
        artifact_type: str = "agent",
        entity_id: str = "",
        dependencies: list[dict[str, Any]] | None = None,
    ) -> RegressionRiskReport:
        dep_analysis = self._analyze_dependency_depth(entity_id, dependencies or [])
        scope_analysis = self._analyze_scope(artifact_type, entity_id)
        historical = self._match_historical(artifact_name, artifact_type)

        depth_score = dep_analysis.depth_score * 0.3
        scope_score = scope_analysis.scope_score * 0.4
        hist_score = sum(m.score for m in historical) * 0.3 if historical else 0.0

        risk_score = min(1.0, depth_score + scope_score + hist_score)

        return RegressionRiskReport(
            artifact_name=artifact_name,
            artifact_type=artifact_type,
            dependency_depth=dep_analysis,
            scope=scope_analysis,
            historical_matches=historical,
            risk_score=risk_score,
            passed=risk_score < 0.7,
        )

    def _analyze_dependency_depth(
        self,
        entity_id: str,
        dependencies: list[dict[str, Any]],
    ) -> DependencyDepthAnalysis:
        if not dependencies:
            return DependencyDepthAnalysis()

        depths = self._compute_depths(dependencies)
        max_depth = max(depths) if depths else 0
        avg_depth = sum(depths) / len(depths) if depths else 0.0
        total = len(dependencies)

        if max_depth <= 1:
            depth_score = 0.0
        elif max_depth <= 3:
            depth_score = 0.2
        elif max_depth <= 5:
            depth_score = 0.4
        elif max_depth <= 10:
            depth_score = 0.6
        else:
            depth_score = 0.8

        if total > 20:
            depth_score = min(1.0, depth_score + 0.2)
        elif total > 10:
            depth_score = min(1.0, depth_score + 0.1)

        return DependencyDepthAnalysis(
            max_depth=max_depth,
            avg_depth=avg_depth,
            total_dependencies=total,
            depth_score=depth_score,
        )

    def _compute_depths(self, deps: list[dict[str, Any]], depth: int = 1) -> list[int]:
        depths: list[int] = []
        for dep in deps:
            depths.append(depth)
            nested = dep.get("dependencies", [])
            if nested:
                depths.extend(self._compute_depths(nested, depth + 1))
        return depths

    def _analyze_scope(self, artifact_type: str, entity_id: str) -> ScopeAnalysis:
        affected_types: dict[str, int] = {}
        affected_count = 0

        if self._graph and entity_id:
            incoming = self._graph.get_incoming_relationships(entity_id)
            for rel in incoming:
                source_id = rel.get("source_id", "")
                source = self._graph.get_entity(source_id)
                if source:
                    stype = source.type
                    affected_types[stype] = affected_types.get(stype, 0) + 1
                    affected_count += 1

        scope_score = 0.0
        if entity_id and affected_count > 0:
            base_weight = _SCOPE_WEIGHTS.get(artifact_type, 0.3)
            scope_score = base_weight
            if affected_count > 10:
                scope_score += 0.3
            elif affected_count > 5:
                scope_score += 0.2
            else:
                scope_score += 0.1
            type_diversity = len(affected_types)
            if type_diversity > 3:
                scope_score += 0.2
            elif type_diversity > 1:
                scope_score += 0.1

        return ScopeAnalysis(
            affected_entities=affected_count,
            affected_types=affected_types,
            scope_score=min(1.0, scope_score),
        )

    def _match_historical(
        self, artifact_name: str, artifact_type: str,
    ) -> list[HistoricalMatch]:
        matches: list[HistoricalMatch] = []
        with self._lock:
            for entry in self._history:
                score = 0.0
                if entry.get("type") == artifact_type:
                    score += 0.3
                if entry.get("regression_count", 0) > 0:
                    rate = entry.get("regression_count", 0) / max(entry.get("match_count", 1), 1)
                    score += rate * 0.7
                matches.append(HistoricalMatch(
                    pattern=entry.get("pattern", ""),
                    match_count=entry.get("match_count", 0),
                    regression_count=entry.get("regression_count", 0),
                    regression_rate=entry.get("regression_count", 0) / max(entry.get("match_count", 1), 1),
                    score=min(1.0, score),
                ))
        return matches

    def record_regression(
        self,
        artifact_name: str,
        artifact_type: str,
        caused_regression: bool,
    ) -> None:
        with self._lock:
            for entry in self._history:
                if entry.get("pattern") == artifact_type:
                    entry["match_count"] = entry.get("match_count", 0) + 1
                    if caused_regression:
                        entry["regression_count"] = entry.get("regression_count", 0) + 1
                    return
            self._history.append({
                "pattern": artifact_type,
                "type": artifact_type,
                "match_count": 1,
                "regression_count": 1 if caused_regression else 0,
                "timestamp": time.time(),
            })

    def get_history(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._history)

    def health(self) -> dict[str, Any]:
        with self._lock:
            return {
                "alive": True,
                "historical_entries": len(self._history),
            }
