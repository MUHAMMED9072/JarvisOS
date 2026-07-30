from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any


ADS_STAGES = [
    "requirements_analysis",
    "capability_analysis",
    "gap_detection",
    "architecture_design",
    "content_generation",
    "test_generation",
    "sandbox_execution",
    "simulation",
    "benchmark",
    "security_review",
    "performance_review",
    "governance_check",
    "approval",
    "installation",
    "registration",
    "versioning",
    "metrics",
    "learning",
]


@dataclass
class ADSBottleneck:
    stage_name: str = ""
    metric: str = ""
    current_value: float = 0.0
    suggested_value: float = 0.0
    impact: str = ""
    description: str = ""
    suggestion: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage_name": self.stage_name,
            "metric": self.metric,
            "current_value": self.current_value,
            "suggested_value": self.suggested_value,
            "impact": self.impact,
            "description": self.description,
            "suggestion": self.suggestion,
        }


class ADSEvolutionScanner:
    """Scans the ADS pipeline for bottlenecks and improvement opportunities.

    Analyzes pipeline execution metrics, stage durations,
    failure rates, and identifies optimization targets.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._execution_metrics: dict[str, dict[str, float]] = {}

    def record_execution(
        self,
        stage: str,
        duration_ms: float,
        success: bool,
    ) -> None:
        with self._lock:
            if stage not in self._execution_metrics:
                self._execution_metrics[stage] = {
                    "total": 0, "successes": 0, "total_duration": 0.0, "max_duration": 0.0,
                }
            m = self._execution_metrics[stage]
            m["total"] += 1
            if success:
                m["successes"] += 1
            m["total_duration"] += duration_ms
            m["max_duration"] = max(m["max_duration"], duration_ms)

    def scan_bottlenecks(self) -> list[ADSBottleneck]:
        bottlenecks: list[ADSBottleneck] = []

        with self._lock:
            metrics = dict(self._execution_metrics)

        for stage in ADS_STAGES:
            m = metrics.get(stage)
            if m is None or m["total"] < 3:
                continue

            avg_duration = m["total_duration"] / m["total"]
            success_rate = m["successes"] / m["total"]

            if avg_duration > 5000:
                bottlenecks.append(ADSBottleneck(
                    stage_name=stage,
                    metric="avg_duration_ms",
                    current_value=avg_duration,
                    suggested_value=avg_duration * 0.5,
                    impact="high",
                    description=f"Stage '{stage}' avg duration {avg_duration:.0f}ms exceeds 5000ms threshold",
                    suggestion="Consider parallelizing work within this stage or optimizing the slowest operations",
                ))

            if success_rate < 0.8:
                bottlenecks.append(ADSBottleneck(
                    stage_name=stage,
                    metric="success_rate",
                    current_value=success_rate,
                    suggested_value=min(success_rate + 0.15, 1.0),
                    impact="high",
                    description=f"Stage '{stage}' success rate {success_rate:.0%} below 80% threshold",
                    suggestion="Investigate common failure modes and add retry logic",
                ))

            max_dur = m.get("max_duration", 0)
            if max_dur > 30000:
                bottlenecks.append(ADSBottleneck(
                    stage_name=stage,
                    metric="max_duration_ms",
                    current_value=max_dur,
                    suggested_value=max_dur * 0.5,
                    impact="medium",
                    description=f"Stage '{stage}' max execution time {max_dur:.0f}ms exceeds 30s",
                    suggestion="Add timeout handling or split into smaller sub-stages",
                ))
        return bottlenecks

    def get_stage_statistics(self) -> dict[str, dict[str, float]]:
        with self._lock:
            stats: dict[str, dict[str, float]] = {}
            for stage, m in self._execution_metrics.items():
                avg_dur = m["total_duration"] / max(m["total"], 1)
                success_rate = m["successes"] / max(m["total"], 1)
                stats[stage] = {
                    "total_executions": m["total"],
                    "success_rate": round(success_rate, 4),
                    "avg_duration_ms": round(avg_dur, 2),
                    "max_duration_ms": round(m["max_duration"], 2),
                }
            return stats

    def get_statistics(self) -> dict[str, Any]:
        bottlenecks = self.scan_bottlenecks()
        stage_stats = self.get_stage_statistics()
        return {
            "total_executions": sum(
                s["total_executions"] for s in stage_stats.values()
            ),
            "stages_with_data": len(stage_stats),
            "bottlenecks_found": len(bottlenecks),
            "by_severity": {
                "high": sum(1 for b in bottlenecks if b.impact == "high"),
                "medium": sum(1 for b in bottlenecks if b.impact == "medium"),
                "low": sum(1 for b in bottlenecks if b.impact == "low"),
            },
        }

    def health(self) -> dict[str, Any]:
        stats = self.get_statistics()
        return {
            "alive": True,
            "stages_tracked": len(ADS_STAGES),
            "bottlenecks_found": stats["bottlenecks_found"],
        }
