from __future__ import annotations

import enum
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from app.agents.communication.message import Message, MessageType
from app.agents.communication.bus import MessageBus
from app.knowledge_graph.store import GraphStore


class HealthStatus(enum.Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class HealthRecord:
    agent_id: str = ""
    status: HealthStatus = HealthStatus.UNKNOWN
    last_heartbeat: float = 0.0
    last_liveness: float = 0.0
    liveness_ok: bool = True
    ready: bool = True
    consecutive_failures: int = 0
    recovery_attempts: int = 0
    max_recovery_attempts: int = 3
    heartbeat_interval: float = 30.0
    liveness_timeout: float = 60.0
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "status": self.status.value,
            "last_heartbeat": self.last_heartbeat,
            "last_liveness": self.last_liveness,
            "liveness_ok": self.liveness_ok,
            "ready": self.ready,
            "consecutive_failures": self.consecutive_failures,
            "recovery_attempts": self.recovery_attempts,
            "max_recovery_attempts": self.max_recovery_attempts,
            "heartbeat_interval": self.heartbeat_interval,
            "liveness_timeout": self.liveness_timeout,
            "timestamp": self.timestamp,
        }


class AgentHealthMonitor:
    """Per-agent health monitoring with heartbeats, probes, and auto-recovery.

    Thread-safe.
    """

    def __init__(
        self,
        graph_store: GraphStore | None = None,
        bus: MessageBus | None = None,
        on_escalate: Callable[[str, str], None] | None = None,
    ) -> None:
        self._lock = threading.RLock()
        self._records: dict[str, HealthRecord] = {}
        self._graph_store = graph_store
        self._bus = bus
        self._on_escalate = on_escalate

    # ── Registration ─────────────────────────────────────────────────

    def register(
        self,
        agent_id: str,
        heartbeat_interval: float = 30.0,
        liveness_timeout: float = 60.0,
        max_recovery_attempts: int = 3,
    ) -> HealthRecord:
        with self._lock:
            record = HealthRecord(
                agent_id=agent_id,
                heartbeat_interval=heartbeat_interval,
                liveness_timeout=liveness_timeout,
                max_recovery_attempts=max_recovery_attempts,
            )
            self._records[agent_id] = record
            self._persist_history(agent_id, record)
            return record

    def unregister(self, agent_id: str) -> bool:
        with self._lock:
            return self._records.pop(agent_id, None) is not None

    # ── Heartbeat ────────────────────────────────────────────────────

    def heartbeat(self, agent_id: str) -> HealthRecord | None:
        with self._lock:
            record = self._records.get(agent_id)
            if record is None:
                return None
            record.last_heartbeat = time.time()
            record.consecutive_failures = 0
            if record.status == HealthStatus.UNHEALTHY:
                record.status = HealthStatus.DEGRADED
            elif record.status == HealthStatus.UNKNOWN:
                record.status = HealthStatus.HEALTHY
            self._update_status(agent_id, record)
            return record

    # ── Liveness probe ───────────────────────────────────────────────

    def liveness_probe(self, agent_id: str) -> bool:
        """Check if agent is alive based on last heartbeat."""
        with self._lock:
            record = self._records.get(agent_id)
            if record is None:
                return False
            now = time.time()
            elapsed = now - record.last_heartbeat
            alive = elapsed < record.liveness_timeout
            record.last_liveness = now
            record.liveness_ok = alive
            if not alive:
                record.consecutive_failures += 1
                record.status = HealthStatus.UNHEALTHY
            elif record.consecutive_failures > 0 and alive:
                record.consecutive_failures = 0
                record.status = HealthStatus.HEALTHY
            self._update_status(agent_id, record)
            return alive

    # ── Readiness probe ──────────────────────────────────────────────

    def readiness_probe(self, agent_id: str) -> bool:
        """Check if agent is ready to accept work."""
        with self._lock:
            record = self._records.get(agent_id)
            if record is None:
                return False
            return record.ready and record.liveness_ok

    def set_ready(self, agent_id: str, ready: bool) -> None:
        with self._lock:
            record = self._records.get(agent_id)
            if record:
                record.ready = ready

    # ── Auto-recovery ────────────────────────────────────────────────

    def attempt_recovery(self, agent_id: str) -> bool:
        with self._lock:
            record = self._records.get(agent_id)
            if record is None:
                return False
            if record.recovery_attempts >= record.max_recovery_attempts:
                record.status = HealthStatus.UNHEALTHY
                self._update_status(agent_id, record)
                self._escalate(agent_id, "max_recovery_attempts_reached")
                return False
            record.recovery_attempts += 1
            record.last_heartbeat = time.time()
            record.liveness_ok = True
            record.ready = True
            record.status = HealthStatus.DEGRADED
            self._update_status(agent_id, record)
            return True

    # ── Querying ─────────────────────────────────────────────────────

    def get_health(self, agent_id: str) -> HealthRecord | None:
        with self._lock:
            return self._records.get(agent_id)

    def list_unhealthy(self) -> list[HealthRecord]:
        with self._lock:
            return [
                r for r in self._records.values()
                if r.status in (HealthStatus.UNHEALTHY, HealthStatus.DEGRADED)
            ]

    # ── Internal ─────────────────────────────────────────────────────

    def _update_status(self, agent_id: str, record: HealthRecord) -> None:
        record.timestamp = time.time()
        self._persist_history(agent_id, record)
        if self._bus:
            msg = Message(
                sender=agent_id,
                msg_type=MessageType.HEALTH,
                body={
                    "sender": agent_id,
                    "status": record.status.value,
                    "metrics": record.to_dict(),
                },
            )
            self._bus.publish(msg, topic="health")

    def _persist_history(self, agent_id: str, record: HealthRecord) -> None:
        if not self._graph_store:
            return
        self._graph_store.create_entity(
            type="agent_metrics",
            name=f"health_{agent_id}_{int(record.timestamp)}",
            properties={
                "agent_id": agent_id,
                "type": "health_check",
                "status": record.status.value,
                "timestamp": str(record.timestamp),
                "data": str(record.to_dict()),
            },
        )

    def _escalate(self, agent_id: str, reason: str) -> None:
        if self._on_escalate:
            self._on_escalate(agent_id, reason)
        if self._bus:
            msg = Message(
                sender="health_monitor",
                msg_type=MessageType.ESCALATE,
                target="executive_controller",
                body={
                    "sender": "health_monitor",
                    "target": "executive_controller",
                    "issue": f"Agent {agent_id} unrecoverable",
                    "details": reason,
                },
            )
            self._bus.publish(msg, topic="escalation")

    def health(self) -> dict[str, Any]:
        with self._lock:
            return {
                "alive": True,
                "monitored_agents": len(self._records),
                "unhealthy": len(self.list_unhealthy()),
            }
