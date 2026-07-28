from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class StageMetrics:
    stage_name: str = ""
    start_time: float = 0.0
    end_time: float = 0.0
    success: bool = True
    error: str = ""

    @property
    def duration_ms(self) -> float:
        return (self.end_time - self.start_time) * 1000.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage_name": self.stage_name,
            "duration_ms": self.duration_ms,
            "success": self.success,
            "error": self.error,
        }


@dataclass
class SessionContext:
    session_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    goal: str = ""
    goal_type: str = "general"
    session_data: dict[str, Any] = field(default_factory=dict)
    stage_metrics: list[StageMetrics] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    def record_stage(self, name: str, success: bool = True, error: str = "") -> StageMetrics:
        now = time.time()
        metrics = StageMetrics(
            stage_name=name,
            start_time=now,
            end_time=now,
            success=success,
            error=error,
        )
        if self.stage_metrics:
            prev = self.stage_metrics[-1]
            metrics.start_time = prev.end_time
        self.stage_metrics.append(metrics)
        return metrics

    def complete_stage(self, metrics: StageMetrics) -> None:
        metrics.end_time = time.time()

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "goal": self.goal,
            "goal_type": self.goal_type,
            "session_data": dict(self.session_data),
            "stage_metrics": [m.to_dict() for m in self.stage_metrics],
            "created_at": self.created_at,
        }
