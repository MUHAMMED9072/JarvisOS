from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any


_IMPACT_BY_TYPE: dict[str, dict[str, float]] = {
    "agent": {"cpu": 0.3, "memory_mb": 256, "disk_mb": 50, "network": 0.2},
    "tool": {"cpu": 0.1, "memory_mb": 64, "disk_mb": 10, "network": 0.1},
    "skill": {"cpu": 0.2, "memory_mb": 128, "disk_mb": 30, "network": 0.1},
    "plugin": {"cpu": 0.15, "memory_mb": 96, "disk_mb": 20, "network": 0.05},
    "workflow": {"cpu": 0.05, "memory_mb": 32, "disk_mb": 5, "network": 0.0},
    "file": {"cpu": 0.01, "memory_mb": 8, "disk_mb": 1, "network": 0.0},
    "memory": {"cpu": 0.02, "memory_mb": 16, "disk_mb": 2, "network": 0.0},
    "task": {"cpu": 0.1, "memory_mb": 64, "disk_mb": 5, "network": 0.0},
    "project": {"cpu": 0.05, "memory_mb": 32, "disk_mb": 10, "network": 0.0},
    "concept": {"cpu": 0.0, "memory_mb": 4, "disk_mb": 1, "network": 0.0},
}

_DEFAULT_IMPACT: dict[str, float] = {"cpu": 0.1, "memory_mb": 64, "disk_mb": 10, "network": 0.05}


@dataclass
class ResourceImpact:
    cpu: float = 0.0
    memory_mb: float = 0.0
    disk_mb: float = 0.0
    network: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "cpu": round(self.cpu, 4),
            "memory_mb": round(self.memory_mb, 2),
            "disk_mb": round(self.disk_mb, 2),
            "network": round(self.network, 4),
        }


@dataclass
class ImpactEstimate:
    artifact_id: str = ""
    artifact_type: str = ""
    artifact_name: str = ""
    direct: ResourceImpact = field(default_factory=ResourceImpact)
    transitive: ResourceImpact = field(default_factory=ResourceImpact)
    total: ResourceImpact = field(default_factory=ResourceImpact)
    dependency_count: int = 0
    confidence: float = 0.5

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "artifact_type": self.artifact_type,
            "artifact_name": self.artifact_name,
            "direct": self.direct.to_dict(),
            "transitive": self.transitive.to_dict(),
            "total": self.total.to_dict(),
            "dependency_count": self.dependency_count,
            "confidence": self.confidence,
        }


class ImpactEstimator:
    """Estimates resource impact of deploying or evolving an artifact.

    Uses per-type base estimates and scales by the artifact's dependency
    tree. The estimate includes direct (the artifact itself) and transitive
    (all dependencies) resource consumption.

    Thread-safe.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._custom_estimates: dict[str, dict[str, float]] = {}

    def set_type_estimate(self, entity_type: str, impact: dict[str, float]) -> None:
        with self._lock:
            self._custom_estimates[entity_type] = dict(impact)

    def get_base_impact(self, entity_type: str) -> dict[str, float]:
        with self._lock:
            if entity_type in self._custom_estimates:
                return dict(self._custom_estimates[entity_type])
            return dict(_IMPACT_BY_TYPE.get(entity_type, _DEFAULT_IMPACT))

    def estimate(
        self,
        entity_type: str,
        entity_name: str = "",
        dependency_tree: list[dict[str, Any]] | None = None,
    ) -> ImpactEstimate:
        """Estimate the resource impact of an artifact.

        Args:
            entity_type: The type of artifact (e.g. 'agent', 'tool').
            entity_name: Optional display name.
            dependency_tree: List of dependency dicts, each with at least
                ``entity_type`` and optionally ``dependencies`` (nested).

        Returns:
            ``ImpactEstimate`` with direct, transitive, and total impacts.
        """
        with self._lock:
            base = self.get_base_impact(entity_type)
            direct = ResourceImpact(
                cpu=base["cpu"],
                memory_mb=base["memory_mb"],
                disk_mb=base["disk_mb"],
                network=base["network"],
            )

            transitive = ResourceImpact()
            dep_count = 0
            if dependency_tree:
                for dep in dependency_tree:
                    dep_impact = self._estimate_dependency(dep)
                    transitive.cpu += dep_impact.cpu
                    transitive.memory_mb += dep_impact.memory_mb
                    transitive.disk_mb += dep_impact.disk_mb
                    transitive.network += dep_impact.network
                    dep_count += 1

            total = ResourceImpact(
                cpu=direct.cpu + transitive.cpu,
                memory_mb=direct.memory_mb + transitive.memory_mb,
                disk_mb=direct.disk_mb + transitive.disk_mb,
                network=direct.network + transitive.network,
            )

            confidence = self._compute_confidence(entity_type, dep_count)

            return ImpactEstimate(
                artifact_id="",
                artifact_type=entity_type,
                artifact_name=entity_name,
                direct=direct,
                transitive=transitive,
                total=total,
                dependency_count=dep_count,
                confidence=confidence,
            )

    def _estimate_dependency(self, dep: dict[str, Any]) -> ResourceImpact:
        dep_type = dep.get("entity_type", "concept")
        base = self.get_base_impact(dep_type)
        result = ResourceImpact(
            cpu=base["cpu"],
            memory_mb=base["memory_mb"],
            disk_mb=base["disk_mb"],
            network=base["network"],
        )
        nested = dep.get("dependencies", [])
        for child in nested:
            child_impact = self._estimate_dependency(child)
            result.cpu += child_impact.cpu
            result.memory_mb += child_impact.memory_mb
            result.disk_mb += child_impact.disk_mb
            result.network += child_impact.network
        return result

    def _compute_confidence(self, entity_type: str, dep_count: int) -> float:
        base = 0.7 if entity_type in _IMPACT_BY_TYPE else 0.3
        if dep_count > 50:
            return base * 0.5
        if dep_count > 20:
            return base * 0.7
        return base

    def health(self) -> dict[str, Any]:
        return {"alive": True}
