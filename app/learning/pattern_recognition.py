from __future__ import annotations

import collections
import math
import statistics
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from app.agents.metrics import AgentMetrics
from app.knowledge_graph.store import GraphStore


@dataclass
class ExecutionRecord:
    agent_id: str = ""
    task_type: str = ""
    success: bool = False
    latency: float = 0.0
    cpu_usage: float = 0.0
    memory_usage: float = 0.0
    token_count: int = 0
    error_message: str = ""
    timestamp: float = 0.0
    task_tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "task_type": self.task_type,
            "success": self.success,
            "latency": round(self.latency, 4),
            "cpu_usage": round(self.cpu_usage, 4),
            "memory_usage": round(self.memory_usage, 4),
            "token_count": self.token_count,
            "error_message": self.error_message,
            "timestamp": self.timestamp,
            "task_tags": list(self.task_tags),
        }


@dataclass
class Pattern:
    pattern_id: str = ""
    name: str = ""
    pattern_type: str = "success"
    task_type: str = ""
    confidence: float = 0.0
    sample_count: int = 0
    avg_latency: float = 0.0
    success_rate: float = 0.0
    common_tags: list[str] = field(default_factory=list)
    common_errors: list[str] = field(default_factory=list)
    typical_agents: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pattern_id": self.pattern_id,
            "name": self.name,
            "pattern_type": self.pattern_type,
            "task_type": self.task_type,
            "confidence": round(self.confidence, 4),
            "sample_count": self.sample_count,
            "avg_latency": round(self.avg_latency, 4),
            "success_rate": round(self.success_rate, 4),
            "common_tags": list(self.common_tags),
            "common_errors": list(self.common_errors),
            "typical_agents": list(self.typical_agents),
        }


@dataclass
class PatternCatalog:
    success_patterns: list[Pattern] = field(default_factory=list)
    failure_patterns: list[Pattern] = field(default_factory=list)
    last_updated: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "success_patterns": [p.to_dict() for p in self.success_patterns],
            "failure_patterns": [p.to_dict() for p in self.failure_patterns],
            "last_updated": self.last_updated,
        }


@dataclass
class PatternRecommendation:
    task_type: str = ""
    recommended_patterns: list[Pattern] = field(default_factory=list)
    predicted_success_rate: float = 0.0
    suggested_agents: list[str] = field(default_factory=list)
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_type": self.task_type,
            "recommended_patterns": [p.to_dict() for p in self.recommended_patterns],
            "predicted_success_rate": round(self.predicted_success_rate, 4),
            "suggested_agents": list(self.suggested_agents),
            "confidence": round(self.confidence, 4),
        }


class PatternRecognizer:
    """Cross-agent pattern recognition system.

    Collects execution data from all agents, identifies recurring
    task types, common failure modes, and optimal strategies.
    """

    MIN_PATTERN_SAMPLES = 3
    MIN_CONFIDENCE = 0.3

    def __init__(
        self,
        metrics: AgentMetrics | None = None,
        graph_store: GraphStore | None = None,
    ) -> None:
        self._metrics = metrics
        self._graph = graph_store
        self._lock = threading.RLock()
        self._records: list[ExecutionRecord] = []
        self._catalog = PatternCatalog()
        self._max_records = 10000

    def record_execution(self, record: ExecutionRecord) -> None:
        with self._lock:
            self._records.append(record)
            if len(self._records) > self._max_records:
                self._records = self._records[-self._max_records:]

        if self._graph:
            try:
                self._graph.create_entity(
                    type="execution_record",
                    name=f"exec_{record.agent_id}_{int(record.timestamp)}",
                    properties=record.to_dict(),
                )
            except Exception:
                pass

    def record_from_metrics(
        self,
        agent_id: str,
        success: bool,
        latency: float,
        task_type: str = "unknown",
        cpu: float = 0.0,
        memory: float = 0.0,
        tokens: int = 0,
        error: str = "",
        tags: list[str] | None = None,
    ) -> None:
        record = ExecutionRecord(
            agent_id=agent_id,
            task_type=task_type,
            success=success,
            latency=latency,
            cpu_usage=cpu,
            memory_usage=memory,
            token_count=tokens,
            error_message=error,
            timestamp=time.time(),
            task_tags=tags or [],
        )
        self.record_execution(record)

    def analyze(self) -> PatternCatalog:
        with self._lock:
            if not self._records:
                return self._catalog

            records = list(self._records)

        task_groups: dict[str, list[ExecutionRecord]] = {}
        for rec in records:
            tt = rec.task_type or "unknown"
            if tt not in task_groups:
                task_groups[tt] = []
            task_groups[tt].append(rec)

        success_patterns: list[Pattern] = []
        failure_patterns: list[Pattern] = []

        for task_type, group in task_groups.items():
            if len(group) < self.MIN_PATTERN_SAMPLES:
                continue

            total = len(group)
            successes = [r for r in group if r.success]
            failures = [r for r in group if not r.success]
            success_count = len(successes)
            failure_count = len(failures)
            success_rate = success_count / total if total > 0 else 0.0

            latencies = [r.latency for r in group]
            avg_lat = statistics.mean(latencies) if latencies else 0.0

            tag_counter: collections.Counter = collections.Counter()
            agent_counter: collections.Counter = collections.Counter()
            error_counter: collections.Counter = collections.Counter()
            for rec in group:
                for t in rec.task_tags:
                    tag_counter[t] += 1
                agent_counter[rec.agent_id] += 1
                if rec.error_message:
                    error_counter[rec.error_message[:100]] += 1

            # Determine if this is a success or failure pattern
            if success_rate >= 0.7 and success_count >= self.MIN_PATTERN_SAMPLES:
                pattern = Pattern(
                    pattern_id=f"success_{task_type}_{int(time.time())}",
                    name=f"Successful {task_type}",
                    pattern_type="success",
                    task_type=task_type,
                    confidence=success_rate,
                    sample_count=total,
                    avg_latency=avg_lat,
                    success_rate=success_rate,
                    common_tags=[t for t, _ in tag_counter.most_common(5)],
                    typical_agents=[a for a, _ in agent_counter.most_common(5)],
                )
                success_patterns.append(pattern)

            if failure_count >= self.MIN_PATTERN_SAMPLES and failure_count / total >= 0.2:
                pattern = Pattern(
                    pattern_id=f"failure_{task_type}_{int(time.time())}",
                    name=f"Failed {task_type}",
                    pattern_type="failure",
                    task_type=task_type,
                    confidence=failure_count / total,
                    sample_count=total,
                    avg_latency=avg_lat,
                    success_rate=success_rate,
                    common_tags=[t for t, _ in tag_counter.most_common(5)],
                    common_errors=[e for e, _ in error_counter.most_common(5)],
                    typical_agents=[a for a, _ in agent_counter.most_common(5)],
                )
                failure_patterns.append(pattern)

        catalog = PatternCatalog(
            success_patterns=success_patterns,
            failure_patterns=failure_patterns,
            last_updated=time.time(),
        )

        with self._lock:
            self._catalog = catalog

        return catalog

    def recommend(self, task_type: str, tags: list[str] | None = None) -> PatternRecommendation:
        catalog = self.analyze()
        tags_set = set(tags or [])

        matching: list[Pattern] = []
        for p in catalog.success_patterns + catalog.failure_patterns:
            if p.task_type == task_type:
                score = 0.0
                if tags_set and p.common_tags:
                    common = len(tags_set & set(p.common_tags))
                    score = common / max(len(tags_set), 1)
                if score >= 0.3 or not tags_set:
                    matching.append(p)

        matching.sort(key=lambda p: p.confidence, reverse=True)

        success_patterns = [p for p in matching if p.pattern_type == "success"]
        predicted_success_rate = success_patterns[0].success_rate if success_patterns else 0.5

        suggested_agents: list[str] = []
        for p in matching[:3]:
            for a in p.typical_agents:
                if a not in suggested_agents:
                    suggested_agents.append(a)

        confidence = predicted_success_rate if success_patterns else 0.3

        return PatternRecommendation(
            task_type=task_type,
            recommended_patterns=matching[:5],
            predicted_success_rate=predicted_success_rate,
            suggested_agents=suggested_agents[:5],
            confidence=confidence,
        )

    def get_patterns_by_type(self, pattern_type: str) -> list[Pattern]:
        catalog = self.analyze()
        if pattern_type == "success":
            return list(catalog.success_patterns)
        if pattern_type == "failure":
            return list(catalog.failure_patterns)
        return catalog.success_patterns + catalog.failure_patterns

    def get_statistics(self) -> dict[str, Any]:
        with self._lock:
            total = len(self._records)
            successes = sum(1 for r in self._records if r.success)
            task_types = len(set(r.task_type for r in self._records))
        return {
            "total_records": total,
            "success_count": successes,
            "failure_count": total - successes,
            "success_rate": round(successes / total, 4) if total > 0 else 0.0,
            "task_types": task_types,
            "patterns_identified": len(self._catalog.success_patterns) + len(self._catalog.failure_patterns),
        }

    def health(self) -> dict[str, Any]:
        stats = self.get_statistics()
        return {
            "alive": True,
            "records_collected": stats["total_records"],
            "patterns_identified": stats["patterns_identified"],
            "task_types_seen": stats["task_types"],
        }
