from __future__ import annotations

import math
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from app.agents.communication.message import Message, MessageType
from app.agents.communication.bus import MessageBus
from app.knowledge_graph.store import GraphStore


@dataclass
class MetricSnapshot:
    agent_id: str = ""
    execution_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    latencies: list[float] = field(default_factory=list)
    cpu_usage: float = 0.0
    memory_usage: float = 0.0
    token_count: int = 0
    timestamp: float = field(default_factory=time.time)

    @property
    def success_rate(self) -> float:
        total = self.execution_count
        if total == 0:
            return 1.0
        return self.success_count / total

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "execution_count": self.execution_count,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "success_rate": self.success_rate,
            "latency_p50": self.percentile(50),
            "latency_p95": self.percentile(95),
            "latency_p99": self.percentile(99),
            "cpu_usage": self.cpu_usage,
            "memory_usage": self.memory_usage,
            "token_count": self.token_count,
            "timestamp": self.timestamp,
        }

    def percentile(self, p: float) -> float:
        if not self.latencies:
            return 0.0
        sorted_lat = sorted(self.latencies)
        k = (p / 100.0) * (len(sorted_lat) - 1)
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return sorted_lat[int(k)]
        return sorted_lat[f] * (c - k) + sorted_lat[c] * (k - f)


class AgentMetrics:
    """Per-agent metrics collection, aggregation, and querying.

    Thread-safe.  Publishes to MessageBus for real-time monitoring
    and persists to Knowledge Graph for historical analysis.
    """

    WINDOWS = {
        "5min": 300,
        "1hr": 3600,
        "1day": 86400,
        "30day": 2592000,
    }

    def __init__(
        self,
        graph_store: GraphStore | None = None,
        bus: MessageBus | None = None,
    ) -> None:
        self._lock = threading.RLock()
        self._snapshots: dict[str, dict[str, MetricSnapshot]] = defaultdict(
            lambda: {w: MetricSnapshot() for w in self.WINDOWS}
        )
        self._graph_store = graph_store
        self._bus = bus

    # ── Recording ────────────────────────────────────────────────────

    def record_execution(
        self,
        agent_id: str,
        success: bool,
        latency: float,
        cpu_usage: float = 0.0,
        memory_usage: float = 0.0,
        token_count: int = 0,
    ) -> None:
        now = time.time()
        with self._lock:
            for window_name, window_sec in self.WINDOWS.items():
                snap = self._snapshots[agent_id][window_name]
                if now - snap.timestamp > window_sec or snap.agent_id != agent_id:
                    snap = MetricSnapshot(agent_id=agent_id, timestamp=now)
                    self._snapshots[agent_id][window_name] = snap
                snap.execution_count += 1
                if success:
                    snap.success_count += 1
                else:
                    snap.failure_count += 1
                snap.latencies.append(latency)
                snap.cpu_usage = cpu_usage
                snap.memory_usage = memory_usage
                snap.token_count = token_count

        # Publish to bus for real-time monitoring
        if self._bus:
            metrics_data = self.get_snapshot(agent_id)
            if metrics_data:
                msg = Message(
                    sender=agent_id,
                    msg_type=MessageType.METRICS,
                    body={"sender": agent_id, "metrics": metrics_data},
                    ttl_seconds=5.0,
                )
                self._bus.publish(msg, topic="metrics")

        # Persist to Knowledge Graph
        if self._graph_store:
            summary = self.get_snapshot(agent_id)
            if summary:
                self._graph_store.create_entity(
                    type="agent_metrics",
                    name=f"metrics_{agent_id}_{int(now)}",
                    properties={
                        "agent_id": agent_id,
                        "timestamp": str(now),
                        "data": str(summary),
                    },
                )

    # ── Querying ─────────────────────────────────────────────────────

    def get_snapshot(self, agent_id: str, window: str = "5min") -> dict[str, Any] | None:
        with self._lock:
            if agent_id not in self._snapshots:
                return None
            if window not in self._snapshots[agent_id]:
                return None
            snap = self._snapshots[agent_id][window]
            now = time.time()
            window_sec = self.WINDOWS.get(window, 300)
            if now - snap.timestamp > window_sec:
                snap = MetricSnapshot(agent_id=agent_id, timestamp=now)
                self._snapshots[agent_id][window] = snap
            return snap.to_dict()

    def query(self, agent_id: str) -> dict[str, Any] | None:
        return self.get_snapshot(agent_id)

    def query_all(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                snap.to_dict()
                for agent_snaps in self._snapshots.values()
                for wname, snap in agent_snaps.items()
                if wname == "5min"
            ]

    def query_by_type(self, agent_id: str, metric_type: str) -> float:
        snap = self.get_snapshot(agent_id)
        if snap is None:
            return 0.0
        return float(snap.get(metric_type, 0.0))

    def query_time_range(self, agent_id: str, start: float, end: float) -> list[dict[str, Any]]:
        """Query historical metrics from KG within time range."""
        if not self._graph_store:
            return []
        entities = self._graph_store.get_entities_by_type("agent_metrics")
        results = []
        for entity in entities:
            props = entity.properties
            if props.get("agent_id") != agent_id:
                continue
            ts = float(props.get("timestamp", 0))
            if start <= ts <= end:
                import ast
                try:
                    data = ast.literal_eval(props.get("data", "{}"))
                    results.append(data)
                except (ValueError, SyntaxError):
                    pass
        results.sort(key=lambda x: x.get("timestamp", 0))
        return results

    # ── Diagnostics ──────────────────────────────────────────────────

    def health(self) -> dict[str, Any]:
        with self._lock:
            return {
                "alive": True,
                "tracked_agents": len(self._snapshots),
            }
