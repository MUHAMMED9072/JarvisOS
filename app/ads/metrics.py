from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any

from app.knowledge_graph.store import GraphStore


@dataclass
class ArtifactMetrics:
    artifact_name: str = ""
    artifact_type: str = ""
    execution_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    avg_latency_ms: float = 0.0
    peak_memory_mb: float = 0.0
    quality_score: float = 1.0
    last_execution: float = 0.0
    created_at: float = field(default_factory=time.time)

    @property
    def success_rate(self) -> float:
        if self.execution_count == 0:
            return 1.0
        return self.success_count / self.execution_count

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_name": self.artifact_name,
            "artifact_type": self.artifact_type,
            "execution_count": self.execution_count,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "success_rate": self.success_rate,
            "avg_latency_ms": self.avg_latency_ms,
            "peak_memory_mb": self.peak_memory_mb,
            "quality_score": self.quality_score,
            "last_execution": self.last_execution,
            "created_at": self.created_at,
        }


@dataclass
class MetricsResult:
    success: bool = True
    error: str = ""
    metrics: ArtifactMetrics | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "error": self.error,
            "metrics": self.metrics.to_dict() if self.metrics else None,
        }


class MetricsCollector:
    """Collect and persist baseline and runtime metrics for artifacts."""

    def __init__(self, graph_store: GraphStore) -> None:
        self._store = graph_store
        self._lock = threading.RLock()
        self._cache: dict[str, ArtifactMetrics] = {}

    def initialize_baseline(
        self,
        artifact_name: str,
        artifact_type: str = "agent",
        benchmark_results: dict[str, Any] | None = None,
    ) -> MetricsResult:
        baseline = ArtifactMetrics(
            artifact_name=artifact_name,
            artifact_type=artifact_type,
        )

        if benchmark_results:
            baseline.avg_latency_ms = benchmark_results.get("avg_latency_ms", 0.0)
            baseline.peak_memory_mb = benchmark_results.get("peak_memory_mb", 0.0)
            exec_count = benchmark_results.get("execution_count", 1)
            baseline.execution_count = exec_count
            baseline.quality_score = self._compute_quality_score(benchmark_results)

        # Persist to KG
        self._store.create_entity(
            type="concept",
            name=f"metrics_{artifact_name}",
            properties={
                "artifact_name": artifact_name,
                "artifact_type": artifact_type,
                "data": str(baseline.to_dict()),
                "created_at": str(time.time()),
            },
        )

        with self._lock:
            self._cache[artifact_name] = baseline

        return MetricsResult(success=True, metrics=baseline)

    def record_execution(
        self,
        artifact_name: str,
        success: bool,
        latency_ms: float = 0.0,
        memory_mb: float = 0.0,
    ) -> MetricsResult:
        with self._lock:
            metrics = self._cache.get(artifact_name)
            if metrics is None:
                metrics = self._load_from_kg(artifact_name)
                if metrics is None:
                    return MetricsResult(
                        success=False,
                        error=f"No baseline metrics for '{artifact_name}'",
                    )

            metrics.execution_count += 1
            if success:
                metrics.success_count += 1
            else:
                metrics.failure_count += 1
            if latency_ms > 0:
                old_total = metrics.avg_latency_ms * (metrics.execution_count - 1)
                metrics.avg_latency_ms = (old_total + latency_ms) / metrics.execution_count
            metrics.peak_memory_mb = max(metrics.peak_memory_mb, memory_mb)
            metrics.last_execution = time.time()

            # Update KG entity
            self._upsert_kg_metrics(artifact_name, metrics)

        return MetricsResult(success=True, metrics=metrics)

    def get_metrics(self, artifact_name: str) -> ArtifactMetrics | None:
        with self._lock:
            if artifact_name in self._cache:
                return self._cache[artifact_name]
            return self._load_from_kg(artifact_name)

    _FIELDS = {"artifact_name", "artifact_type", "execution_count", "success_count",
                "failure_count", "avg_latency_ms", "peak_memory_mb", "quality_score",
                "last_execution", "created_at"}

    def list_metrics(self) -> list[ArtifactMetrics]:
        entities = self._store.get_entities_by_type("concept")
        result: list[ArtifactMetrics] = []
        for e in entities:
            if e.name.startswith("metrics_"):
                props = e.properties
                if "data" in props:
                    import ast
                    try:
                        raw = ast.literal_eval(props["data"])
                        filtered = {k: v for k, v in raw.items() if k in self._FIELDS}
                        result.append(ArtifactMetrics(**filtered))
                    except (ValueError, TypeError):
                        pass
        return result

    def _load_from_kg(self, artifact_name: str) -> ArtifactMetrics | None:
        entities = self._store.get_entity_by_name(f"metrics_{artifact_name}")
        if not entities:
            return None
        props = entities[0].properties
        import ast
        try:
            raw = ast.literal_eval(props.get("data", "{}"))
            filtered = {k: v for k, v in raw.items() if k in self._FIELDS}
            metrics = ArtifactMetrics(**filtered)
            with self._lock:
                self._cache[artifact_name] = metrics
            return metrics
        except (ValueError, SyntaxError, TypeError):
            return None

    def _upsert_kg_metrics(self, artifact_name: str, metrics: ArtifactMetrics) -> None:
        entities = self._store.get_entity_by_name(f"metrics_{artifact_name}")
        data_str = str(metrics.to_dict())
        if entities:
            self._store.update_entity(
                entity_id=entities[0].id,
                properties={"data": data_str, "updated_at": str(time.time())},
            )
        else:
            self._store.create_entity(
                type="concept",
                name=f"metrics_{artifact_name}",
                properties={
                    "artifact_name": artifact_name,
                    "artifact_type": metrics.artifact_type,
                    "data": data_str,
                    "created_at": str(time.time()),
                },
            )

    @staticmethod
    def _compute_quality_score(benchmark: dict[str, Any]) -> float:
        score = 1.0
        latency = benchmark.get("avg_latency_ms", 0)
        if latency > 1000:
            score -= 0.2
        elif latency > 500:
            score -= 0.1
        elif latency > 100:
            score -= 0.05
        memory = benchmark.get("peak_memory_mb", 0)
        if memory > 500:
            score -= 0.2
        elif memory > 200:
            score -= 0.1
        elif memory > 100:
            score -= 0.05
        return max(0.1, round(score, 2))

    def health(self) -> dict[str, Any]:
        return {"alive": True, "cached_artifacts": len(self._cache)}
