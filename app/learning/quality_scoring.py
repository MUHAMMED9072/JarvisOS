from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from app.knowledge_graph.capability_registry import CapabilityRegistry
from app.knowledge_graph.store import GraphStore


@dataclass
class QualityScoreEntry:
    capability_name: str = ""
    provider_id: str = ""
    provider_name: str = ""
    score: float = 0.5
    success_rate: float = 1.0
    avg_latency: float = 0.0
    resource_efficiency: float = 1.0
    sample_count: int = 0
    last_updated: float = 0.0
    trend: str = "stable"

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability_name": self.capability_name,
            "provider_id": self.provider_id,
            "provider_name": self.provider_name,
            "score": round(self.score, 4),
            "success_rate": round(self.success_rate, 4),
            "avg_latency": round(self.avg_latency, 4),
            "resource_efficiency": round(self.resource_efficiency, 4),
            "sample_count": self.sample_count,
            "last_updated": self.last_updated,
            "trend": self.trend,
        }


@dataclass
class QualityAlert:
    alert_id: str = ""
    capability_name: str = ""
    provider_name: str = ""
    previous_score: float = 0.0
    current_score: float = 0.0
    threshold: float = 0.0
    message: str = ""
    timestamp: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "alert_id": self.alert_id,
            "capability_name": self.capability_name,
            "provider_name": self.provider_name,
            "previous_score": round(self.previous_score, 4),
            "current_score": round(self.current_score, 4),
            "threshold": self.threshold,
            "message": self.message,
            "timestamp": self.timestamp,
        }


class CapabilityQualityScorer:
    """Continuously updates capability quality scores based on real-world performance.

    Score factors:
      - Success rate (weight: 0.5)
      - Latency efficiency (weight: 0.2)
      - Resource efficiency (weight: 0.2)
      - Sample count confidence (weight: 0.1)

    Score decay: older data weighted less than newer data.
    """

    SUCCESS_WEIGHT = 0.5
    LATENCY_WEIGHT = 0.2
    RESOURCE_WEIGHT = 0.2
    CONFIDENCE_WEIGHT = 0.1

    ALERT_THRESHOLD_DROP = 0.2

    def __init__(
        self,
        capability_registry: CapabilityRegistry | None = None,
        alert_callback: Callable[[QualityAlert], None] | None = None,
    ) -> None:
        self._cap_reg = capability_registry
        self._alert_callback = alert_callback
        self._lock = threading.RLock()
        self._entries: dict[str, QualityScoreEntry] = {}
        self._alerts: list[QualityAlert] = []
        self._max_alerts = 100
        self._decay_factor = 0.95

    def update_score(
        self,
        capability_name: str,
        provider_id: str,
        provider_name: str,
        success: bool,
        latency: float = 0.0,
        cpu_usage: float = 0.0,
        memory_usage: float = 0.0,
    ) -> QualityScoreEntry:
        key = f"{capability_name}:{provider_id}"

        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                entry = QualityScoreEntry(
                    capability_name=capability_name,
                    provider_id=provider_id,
                    provider_name=provider_name,
                    last_updated=time.time(),
                )
                self._entries[key] = entry

            prev_score = entry.score

            # Apply decay to historical values
            entry.success_rate = entry.success_rate * self._decay_factor + (1.0 if success else 0.0) * (1 - self._decay_factor)
            entry.avg_latency = entry.avg_latency * self._decay_factor + latency * (1 - self._decay_factor) if entry.sample_count > 0 else latency
            entry.sample_count += 1

            # Resource efficiency: lower is better, normalized to 0-1
            resource_usage = (cpu_usage * 0.5 + memory_usage * 0.5)
            resource_efficiency = max(0.0, 1.0 - resource_usage)
            entry.resource_efficiency = entry.resource_efficiency * self._decay_factor + resource_efficiency * (1 - self._decay_factor)

            # Compute combined score
            confidence_factor = min(1.0, entry.sample_count / 50)
            entry.score = (
                entry.success_rate * self.SUCCESS_WEIGHT +
                (1.0 - min(1.0, entry.avg_latency / 10.0)) * self.LATENCY_WEIGHT +
                entry.resource_efficiency * self.RESOURCE_WEIGHT +
                confidence_factor * self.CONFIDENCE_WEIGHT
            )
            entry.score = max(0.0, min(1.0, entry.score))
            entry.last_updated = time.time()

            # Determine trend
            diff = entry.score - prev_score
            if diff > 0.02:
                entry.trend = "improving"
            elif diff < -0.02:
                entry.trend = "declining"
            else:
                entry.trend = "stable"

            # Check for alert
            if prev_score > 0 and (prev_score - entry.score) >= self.ALERT_THRESHOLD_DROP:
                alert = QualityAlert(
                    alert_id=f"alert_{capability_name}_{provider_id}_{int(time.time())}",
                    capability_name=capability_name,
                    provider_name=provider_name,
                    previous_score=prev_score,
                    current_score=entry.score,
                    threshold=self.ALERT_THRESHOLD_DROP,
                    message=f"Quality score for '{provider_name}' capability '{capability_name}' "
                            f"dropped from {prev_score:.2f} to {entry.score:.2f}",
                    timestamp=time.time(),
                )
                self._alerts.append(alert)
                if len(self._alerts) > self._max_alerts:
                    self._alerts = self._alerts[-self._max_alerts:]
                if self._alert_callback:
                    try:
                        self._alert_callback(alert)
                    except Exception:
                        pass

            # Sync to CapabilityRegistry
            if self._cap_reg:
                try:
                    self._cap_reg.update_quality_score(provider_id, entry.score)
                except Exception:
                    pass

            return entry

    def get_score(self, capability_name: str, provider_id: str) -> QualityScoreEntry | None:
        key = f"{capability_name}:{provider_id}"
        with self._lock:
            return self._entries.get(key)

    def get_scores_for_capability(self, capability_name: str) -> list[QualityScoreEntry]:
        with self._lock:
            return [
                e for e in self._entries.values()
                if e.capability_name == capability_name
            ]

    def get_scores_for_provider(self, provider_id: str) -> list[QualityScoreEntry]:
        with self._lock:
            return [
                e for e in self._entries.values()
                if e.provider_id == provider_id
            ]

    def get_alerts(self, limit: int = 20) -> list[QualityAlert]:
        with self._lock:
            return list(self._alerts[-limit:])

    def set_decay_factor(self, factor: float) -> None:
        with self._lock:
            self._decay_factor = max(0.5, min(0.999, factor))

    def get_statistics(self) -> dict[str, Any]:
        with self._lock:
            scores = [e.score for e in self._entries.values()]
            avg_score = sum(scores) / len(scores) if scores else 0.0
            return {
                "total_entries": len(self._entries),
                "avg_score": round(avg_score, 4),
                "active_alerts": len(self._alerts),
                "decay_factor": self._decay_factor,
            }

    def health(self) -> dict[str, Any]:
        stats = self.get_statistics()
        return {
            "alive": True,
            "entries_tracked": stats["total_entries"],
            "avg_quality_score": stats["avg_score"],
            "active_alerts": stats["active_alerts"],
        }
