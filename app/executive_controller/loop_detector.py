from __future__ import annotations

import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.executive_controller.incident import Incident, IncidentSeverity, IncidentStore


class LoopSeverity(Enum):
    NONE = "none"
    SUSPECTED = "suspected"
    CONFIRMED = "confirmed"
    TERMINATED = "terminated"


@dataclass
class ExecutionRecord:
    timestamp: float = 0.0
    duration: float = 0.0
    success: bool = True
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "duration": self.duration,
            "success": self.success,
            "error": self.error,
        }


@dataclass
class LoopReport:
    component_id: str
    severity: LoopSeverity = LoopSeverity.NONE
    execution_count: int = 0
    recent_durations: list[float] = field(default_factory=list)
    consecutive_failures: int = 0
    same_output_count: int = 0
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "component_id": self.component_id,
            "severity": self.severity.value,
            "execution_count": self.execution_count,
            "recent_durations": list(self.recent_durations[-10:]),
            "consecutive_failures": self.consecutive_failures,
            "same_output_count": self.same_output_count,
            "reason": self.reason,
        }


class LoopDetector:
    """Monitors agent execution patterns to detect infinite loops,
    runaway processes, and recursive delegation.

    Detection heuristics:
      1. Rapid repeated executions with similar duration
      2. High consecutive failure rate
      3. Repeated identical output (no progress)
      4. Execution frequency exceeding thresholds

    Thread-safe.
    """

    def __init__(
        self,
        incident_store: IncidentStore | None = None,
        max_executions_per_minute: int = 60,
        max_consecutive_failures: int = 5,
        max_same_output: int = 10,
        max_duration_seconds: float = 300.0,
    ) -> None:
        self._incident_store = incident_store or IncidentStore()
        self._max_per_minute = max_executions_per_minute
        self._max_consecutive_failures = max_consecutive_failures
        self._max_same_output = max_same_output
        self._max_duration = max_duration_seconds

        self._lock = threading.RLock()
        self._records: dict[str, list[ExecutionRecord]] = defaultdict(list)
        self._outputs: dict[str, list[str]] = defaultdict(list)
        self._terminated: dict[str, bool] = {}
        self._check_count: int = 0

    def record_execution(
        self,
        component_id: str,
        duration: float,
        success: bool = True,
        error: str | None = None,
        output_hash: str | None = None,
    ) -> None:
        with self._lock:
            self._records[component_id].append(ExecutionRecord(
                timestamp=time.time(),
                duration=duration,
                success=success,
                error=error,
            ))
            if output_hash is not None:
                self._outputs[component_id].append(output_hash)
            self._check_count += 1

    def check(self, component_id: str) -> LoopReport:
        with self._lock:
            report = LoopReport(component_id=component_id)
            records = self._records.get(component_id, [])
            if not records:
                return report

            now = time.time()
            recent = [r for r in records if now - r.timestamp < 60]

            report.execution_count = len(records)

            durations = [r.duration for r in recent if r.duration > 0]
            report.recent_durations = durations

            failures = [r for r in recent if not r.success]
            report.consecutive_failures = len(failures)

            outputs = self._outputs.get(component_id, [])
            recent_outputs = [o for o in outputs if len(outputs) - len(recent) <= len(outputs)]
            if recent_outputs:
                report.same_output_count = self._count_consecutive_identical(recent_outputs)

            reasons: list[str] = []

            # Heuristic 1: frequency check
            if len(recent) > self._max_per_minute:
                reasons.append(
                    f"Execution frequency {len(recent)}/min exceeds limit {self._max_per_minute}"
                )

            # Heuristic 2: consecutive failures
            if len(failures) >= self._max_consecutive_failures:
                reasons.append(
                    f"Consecutive failures ({len(failures)}) >= threshold {self._max_consecutive_failures}"
                )

            # Heuristic 3: identical output
            if report.same_output_count >= self._max_same_output:
                reasons.append(
                    f"Identical output ({report.same_output_count}) >= threshold {self._max_same_output}"
                )

            # Heuristic 4: long running
            if durations and max(durations) > self._max_duration:
                reasons.append(
                    f"Execution duration {max(durations):.1f}s exceeds limit {self._max_duration}s"
                )

            if not reasons:
                return report

            report.reason = "; ".join(reasons)

            if len(recent) > self._max_per_minute * 2:
                report.severity = LoopSeverity.TERMINATED
            elif reasons:
                report.severity = LoopSeverity.CONFIRMED

            if report.severity in (LoopSeverity.CONFIRMED, LoopSeverity.TERMINATED):
                incident = Incident(
                    component_id=component_id,
                    severity=IncidentSeverity.WARNING,
                    title="Infinite loop detected",
                    description=report.reason,
                    evidence=[report.to_dict()],
                )
                self._incident_store.record(incident)

            return report

    def is_terminated(self, component_id: str) -> bool:
        with self._lock:
            return self._terminated.get(component_id, False)

    def mark_terminated(self, component_id: str) -> None:
        with self._lock:
            self._terminated[component_id] = True
            incident = Incident(
                component_id=component_id,
                severity=IncidentSeverity.ERROR,
                title="Process force-terminated",
                description=f"Component '{component_id}' was force-terminated by loop detector",
            )
            self._incident_store.record(incident)

    def clear(self, component_id: str) -> None:
        with self._lock:
            self._records.pop(component_id, None)
            self._outputs.pop(component_id, None)
            self._terminated.pop(component_id, None)

    def get_stats(self) -> dict[str, Any]:
        with self._lock:
            total_records = sum(len(r) for r in self._records.values())
            return {
                "components_tracked": len(self._records),
                "total_executions_recorded": total_records,
                "terminated_count": sum(1 for v in self._terminated.values() if v),
                "check_count": self._check_count,
            }

    @staticmethod
    def _count_consecutive_identical(items: list[str]) -> int:
        if not items:
            return 0
        count = 1
        for i in range(len(items) - 2, -1, -1):
            if items[i] == items[-1]:
                count += 1
            else:
                break
        return count
