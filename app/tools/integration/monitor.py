from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TraceSpan:
    name: str = ""
    start_time: float = 0.0
    end_time: float = 0.0
    status: str = "ok"
    details: str = ""

    @property
    def duration_ms(self) -> float:
        return (self.end_time - self.start_time) * 1000

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": round(self.duration_ms, 3),
            "status": self.status,
            "details": self.details,
        }


@dataclass
class ToolExecutionTrace:
    trace_id: str = ""
    tool_name: str = ""
    tool_version: str = ""
    action: str = ""
    spans: list[TraceSpan] = field(default_factory=list)
    total_duration_ms: float = 0.0
    success: bool = False
    error_message: str = ""
    started_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "tool_name": self.tool_name,
            "tool_version": self.tool_version,
            "action": self.action,
            "spans": [s.to_dict() for s in self.spans],
            "total_duration_ms": round(self.total_duration_ms, 3),
            "success": self.success,
            "error_message": self.error_message,
            "started_at": self.started_at,
        }


class ToolMonitor:
    """Thread-safe execution metrics, health monitoring, and tracing.

    Maintains:
      - Per-tool execution counters and latencies
      - Trace history (circular buffer, max 1000 entries)
      - Health check endpoints
      - Real-time metric snapshots
    """

    def __init__(self, max_traces: int = 1000) -> None:
        self._lock = threading.RLock()
        self._max_traces = max_traces
        self._traces: list[ToolExecutionTrace] = []
        self._tool_metrics: dict[str, dict[str, Any]] = {}
        self._trace_id_counter: int = 0

    def begin_trace(self, tool_name: str, tool_version: str, action: str) -> str:
        tid = uuid.uuid4().hex[:16]
        trace = ToolExecutionTrace(
            trace_id=tid,
            tool_name=tool_name,
            tool_version=tool_version,
            action=action,
            started_at=time.time(),
        )
        with self._lock:
            self._traces.append(trace)
            if len(self._traces) > self._max_traces:
                self._traces.pop(0)
            key = f"{tool_name}:{action}"
            if key not in self._tool_metrics:
                self._tool_metrics[key] = {"count": 0, "total_ms": 0.0, "errors": 0}
        return tid

    def end_trace(self, trace_id: str, success: bool, error_message: str = "") -> None:
        with self._lock:
            for trace in self._traces:
                if trace.trace_id == trace_id:
                    trace.success = success
                    trace.error_message = error_message
                    trace.total_duration_ms = (time.time() - trace.started_at) * 1000
                    key = f"{trace.tool_name}:{trace.action}"
                    if key in self._tool_metrics:
                        self._tool_metrics[key]["count"] += 1
                        self._tool_metrics[key]["total_ms"] += trace.total_duration_ms
                        if not success:
                            self._tool_metrics[key]["errors"] += 1
                    break

    def add_span(self, trace_id: str, span: TraceSpan) -> bool:
        with self._lock:
            for trace in self._traces:
                if trace.trace_id == trace_id:
                    trace.spans.append(span)
                    return True
            return False

    def get_traces(
        self,
        tool_name: str | None = None,
        limit: int = 50,
    ) -> list[ToolExecutionTrace]:
        with self._lock:
            results = list(self._traces)
            if tool_name:
                results = [t for t in results if t.tool_name == tool_name]
            return results[-limit:]

    def get_metrics(self) -> dict[str, Any]:
        with self._lock:
            snapshot: dict[str, Any] = {}
            for key, m in self._tool_metrics.items():
                avg_ms = round(m["total_ms"] / m["count"], 2) if m["count"] > 0 else 0.0
                snapshot[key] = {
                    "count": m["count"],
                    "avg_ms": avg_ms,
                    "errors": m["errors"],
                    "error_rate": round(m["errors"] / m["count"], 4) if m["count"] > 0 else 0.0,
                }
            return snapshot

    def health(self) -> dict[str, Any]:
        metrics = self.get_metrics()
        return {
            "alive": True,
            "traces_recorded": len(self._traces),
            "tool_actions_tracked": len(metrics),
            "metrics": metrics,
        }
