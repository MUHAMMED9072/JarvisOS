from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any

from app.knowledge_graph.store import GraphStore
from app.simulation.impact_estimator import ImpactEstimator, ResourceImpact


# Default base estimates per artifact type (used when no KG historical data)
_PERF_BY_TYPE: dict[str, dict[str, float]] = {
    "agent": {"cpu": 0.3, "memory_mb": 256.0, "disk_mb": 50.0, "network": 0.2},
    "tool": {"cpu": 0.1, "memory_mb": 64.0, "disk_mb": 10.0, "network": 0.1},
    "plugin": {"cpu": 0.15, "memory_mb": 96.0, "disk_mb": 20.0, "network": 0.05},
    "skill": {"cpu": 0.2, "memory_mb": 128.0, "disk_mb": 30.0, "network": 0.1},
    "workflow": {"cpu": 0.05, "memory_mb": 32.0, "disk_mb": 5.0, "network": 0.0},
    "pipeline": {"cpu": 0.1, "memory_mb": 64.0, "disk_mb": 10.0, "network": 0.05},
    "knowledge_pack": {"cpu": 0.02, "memory_mb": 16.0, "disk_mb": 50.0, "network": 0.0},
    "test_suite": {"cpu": 0.05, "memory_mb": 32.0, "disk_mb": 5.0, "network": 0.0},
    "integration": {"cpu": 0.1, "memory_mb": 64.0, "disk_mb": 10.0, "network": 0.1},
    "documentation": {"cpu": 0.01, "memory_mb": 8.0, "disk_mb": 2.0, "network": 0.0},
}

_DEFAULT_PERF: dict[str, float] = {"cpu": 0.1, "memory_mb": 64.0, "disk_mb": 10.0, "network": 0.05}

_MIN_CONFIDENCE = 0.1
_MAX_CONFIDENCE = 0.95


@dataclass
class CalibrationEntry:
    artifact_name: str = ""
    artifact_type: str = ""
    estimated_cpu: float = 0.0
    actual_cpu: float = 0.0
    estimated_memory_mb: float = 0.0
    actual_memory_mb: float = 0.0
    estimated_disk_mb: float = 0.0
    actual_disk_mb: float = 0.0
    estimated_network: float = 0.0
    actual_network: float = 0.0
    error_pct: float = 0.0
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_name": self.artifact_name,
            "artifact_type": self.artifact_type,
            "estimated_cpu": self.estimated_cpu,
            "actual_cpu": self.actual_cpu,
            "estimated_memory_mb": self.estimated_memory_mb,
            "actual_memory_mb": self.actual_memory_mb,
            "estimated_disk_mb": self.estimated_disk_mb,
            "actual_disk_mb": self.actual_disk_mb,
            "estimated_network": self.estimated_network,
            "actual_network": self.actual_network,
            "error_pct": self.error_pct,
            "timestamp": self.timestamp,
        }


@dataclass
class PerformanceEstimate:
    artifact_name: str = ""
    artifact_type: str = ""
    cpu: float = 0.0
    memory_mb: float = 0.0
    disk_mb: float = 0.0
    network: float = 0.0
    confidence: float = _MIN_CONFIDENCE
    calibration_count: int = 0
    calibration_accuracy: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_name": self.artifact_name,
            "artifact_type": self.artifact_type,
            "cpu": round(self.cpu, 4),
            "memory_mb": round(self.memory_mb, 2),
            "disk_mb": round(self.disk_mb, 2),
            "network": round(self.network, 4),
            "confidence": round(self.confidence, 4),
            "calibration_count": self.calibration_count,
            "calibration_accuracy": round(self.calibration_accuracy, 4),
        }


@dataclass
class ModelCalibration:
    type: str = ""
    count: int = 0
    avg_error_pct: float = 0.0
    cpu_error_pct: float = 0.0
    memory_error_pct: float = 0.0
    disk_error_pct: float = 0.0
    network_error_pct: float = 0.0
    last_calibrated: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "count": self.count,
            "avg_error_pct": round(self.avg_error_pct, 4),
            "cpu_error_pct": round(self.cpu_error_pct, 4),
            "memory_error_pct": round(self.memory_error_pct, 4),
            "disk_error_pct": round(self.disk_error_pct, 4),
            "network_error_pct": round(self.network_error_pct, 4),
            "last_calibrated": self.last_calibrated,
        }


class PerformanceModeler:
    """Estimate CPU, memory, disk, and network impact of artifacts.

    Uses per-type base models calibrated against historical measurement
    data stored in the Knowledge Graph. Confidence increases with more
    calibration data and lower average error.

    Thread-safe.
    """

    def __init__(
        self,
        graph_store: GraphStore | None = None,
        impact_estimator: ImpactEstimator | None = None,
    ) -> None:
        self._graph = graph_store
        self._estimator = impact_estimator or ImpactEstimator()
        self._lock = threading.RLock()
        self._calibrations: dict[str, ModelCalibration] = {}
        self._custom_models: dict[str, dict[str, float]] = {}

    def set_type_model(self, entity_type: str, estimates: dict[str, float]) -> None:
        with self._lock:
            self._custom_models[entity_type] = dict(estimates)

    def estimate(
        self,
        artifact_type: str,
        artifact_name: str = "",
        dependency_tree: list[dict[str, Any]] | None = None,
    ) -> PerformanceEstimate:
        with self._lock:
            base = self._get_base_estimate(artifact_type)
            cal = self._calibrations.get(artifact_type)

            if cal and cal.count > 0:
                adj_cpu = self._adjust(base["cpu"], cal.cpu_error_pct)
                adj_memory = self._adjust(base["memory_mb"], cal.memory_error_pct)
                adj_disk = self._adjust(base["disk_mb"], cal.disk_error_pct)
                adj_network = self._adjust(base["network"], cal.network_error_pct)
            else:
                adj_cpu = base["cpu"]
                adj_memory = base["memory_mb"]
                adj_disk = base["disk_mb"]
                adj_network = base["network"]

            confidence = self._compute_confidence(artifact_type, cal)
            accuracy = 1.0 - (abs(cal.avg_error_pct) / 100.0) if cal and cal.count > 0 else 0.0

            return PerformanceEstimate(
                artifact_name=artifact_name,
                artifact_type=artifact_type,
                cpu=adj_cpu,
                memory_mb=adj_memory,
                disk_mb=adj_disk,
                network=adj_network,
                confidence=confidence,
                calibration_count=cal.count if cal else 0,
                calibration_accuracy=max(0.0, accuracy),
            )

    def calibrate(
        self,
        artifact_type: str,
        estimated: ResourceImpact,
        actual: ResourceImpact,
    ) -> CalibrationEntry:
        errors = _compute_errors(estimated, actual)
        entry = CalibrationEntry(
            artifact_type=artifact_type,
            estimated_cpu=estimated.cpu,
            actual_cpu=actual.cpu,
            estimated_memory_mb=estimated.memory_mb,
            actual_memory_mb=actual.memory_mb,
            estimated_disk_mb=estimated.disk_mb,
            actual_disk_mb=actual.disk_mb,
            estimated_network=estimated.network,
            actual_network=actual.network,
            error_pct=errors["avg"],
            timestamp=time.time(),
        )

        with self._lock:
            if artifact_type not in self._calibrations:
                self._calibrations[artifact_type] = ModelCalibration(type=artifact_type)
            cal = self._calibrations[artifact_type]
            n = cal.count + 1
            cal.cpu_error_pct = (cal.cpu_error_pct * cal.count + errors["cpu"]) / n
            cal.memory_error_pct = (cal.memory_error_pct * cal.count + errors["memory"]) / n
            cal.disk_error_pct = (cal.disk_error_pct * cal.count + errors["disk"]) / n
            cal.network_error_pct = (cal.network_error_pct * cal.count + errors["network"]) / n
            cal.avg_error_pct = (cal.avg_error_pct * cal.count + errors["avg"]) / n
            cal.count = n
            cal.last_calibrated = time.time()

        # Persist calibration to KG
        if self._graph:
            self._graph.create_entity(
                type="concept",
                name=f"calibration_{artifact_type}_{int(time.time())}",
                properties={
                    "artifact_type": artifact_type,
                    "estimated_cpu": str(estimated.cpu),
                    "actual_cpu": str(actual.cpu),
                    "estimated_memory_mb": str(estimated.memory_mb),
                    "actual_memory_mb": str(actual.memory_mb),
                    "estimated_disk_mb": str(estimated.disk_mb),
                    "actual_disk_mb": str(actual.disk_mb),
                    "estimated_network": str(estimated.network),
                    "actual_network": str(actual.network),
                    "error_pct": str(errors["avg"]),
                    "timestamp": str(entry.timestamp),
                },
            )

        return entry

    def load_calibrations_from_kg(self) -> int:
        if not self._graph:
            return 0
        entities = self._graph.get_entities_by_type("concept")
        type_entries: dict[str, list[dict[str, float]]] = {}
        for e in entities:
            if not e.name.startswith("calibration_"):
                continue
            props = e.properties
            atype = props.get("artifact_type", "")
            if not atype:
                continue
            if atype not in type_entries:
                type_entries[atype] = []
            import ast
            try:
                entry = {
                    "cpu": float(ast.literal_eval(props.get("estimated_cpu", "0"))),
                    "actual_cpu": float(ast.literal_eval(props.get("actual_cpu", "0"))),
                    "memory": float(ast.literal_eval(props.get("estimated_memory_mb", "0"))),
                    "actual_memory": float(ast.literal_eval(props.get("actual_memory_mb", "0"))),
                    "disk": float(ast.literal_eval(props.get("estimated_disk_mb", "0"))),
                    "actual_disk": float(ast.literal_eval(props.get("actual_disk_mb", "0"))),
                    "network": float(ast.literal_eval(props.get("estimated_network", "0"))),
                    "actual_network": float(ast.literal_eval(props.get("actual_network", "0"))),
                }
                type_entries[atype].append(entry)
            except (ValueError, SyntaxError):
                continue

        with self._lock:
            for atype, entries in type_entries.items():
                cal = ModelCalibration(type=atype, count=len(entries))
                cpu_errs = [self._error_pct(e["cpu"], e["actual_cpu"]) for e in entries]
                mem_errs = [self._error_pct(e["memory"], e["actual_memory"]) for e in entries]
                disk_errs = [self._error_pct(e["disk"], e["actual_disk"]) for e in entries]
                net_errs = [self._error_pct(e["network"], e["actual_network"]) for e in entries]
                cal.cpu_error_pct = sum(cpu_errs) / len(cpu_errs) if cpu_errs else 0
                cal.memory_error_pct = sum(mem_errs) / len(mem_errs) if mem_errs else 0
                cal.disk_error_pct = sum(disk_errs) / len(disk_errs) if disk_errs else 0
                cal.network_error_pct = sum(net_errs) / len(net_errs) if net_errs else 0
                cal.avg_error_pct = (cal.cpu_error_pct + cal.memory_error_pct
                                     + cal.disk_error_pct + cal.network_error_pct) / 4
                cal.last_calibrated = time.time()
                self._calibrations[atype] = cal

        return sum(len(v) for v in type_entries.values())

    def get_calibration(self, artifact_type: str) -> ModelCalibration | None:
        with self._lock:
            return self._calibrations.get(artifact_type)

    def list_calibrations(self) -> list[ModelCalibration]:
        with self._lock:
            return list(self._calibrations.values())

    def _get_base_estimate(self, entity_type: str) -> dict[str, float]:
        if entity_type in self._custom_models:
            return dict(self._custom_models[entity_type])
        return dict(_PERF_BY_TYPE.get(entity_type, _DEFAULT_PERF))

    def _compute_confidence(
        self, artifact_type: str, cal: ModelCalibration | None,
    ) -> float:
        if artifact_type in _PERF_BY_TYPE:
            base = 0.7
        else:
            base = 0.3
        if cal is None or cal.count == 0:
            return base
        accuracy_factor = max(0.0, 1.0 - abs(cal.avg_error_pct) / 100.0)
        data_factor = min(1.0, cal.count / 50.0)
        confidence = base + (accuracy_factor * 0.2) + (data_factor * 0.1)
        return min(_MAX_CONFIDENCE, max(_MIN_CONFIDENCE, confidence))

    @staticmethod
    def _error_pct(estimated: float, actual: float) -> float:
        if actual == 0:
            return 0.0
        return (estimated - actual) / actual * 100.0

    @staticmethod
    def _adjust(base: float, error_pct: float) -> float:
        if error_pct > 0:
            return base * 100.0 / (100.0 + error_pct)
        return base * (100.0 - error_pct) / 100.0

    def health(self) -> dict[str, Any]:
        with self._lock:
            return {
                "alive": True,
                "calibrated_types": len(self._calibrations),
                "total_calibrations": sum(c.count for c in self._calibrations.values()),
            }


def _compute_errors(estimated: ResourceImpact, actual: ResourceImpact) -> dict[str, float]:
    def err_pct(est: float, act: float) -> float:
        if act == 0:
            return 0.0
        return (est - act) / act * 100.0

    cpu_e = err_pct(estimated.cpu, actual.cpu)
    mem_e = err_pct(estimated.memory_mb, actual.memory_mb)
    disk_e = err_pct(estimated.disk_mb, actual.disk_mb)
    net_e = err_pct(estimated.network, actual.network)
    return {"cpu": cpu_e, "memory": mem_e, "disk": disk_e, "network": net_e, "avg": (cpu_e + mem_e + disk_e + net_e) / 4}
