from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any

import psutil


@dataclass
class ResourceUsage:
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    memory_rss: int = 0
    disk_read_bytes: int = 0
    disk_write_bytes: int = 0
    network_sent_bytes: int = 0
    network_recv_bytes: int = 0
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "cpu_percent": self.cpu_percent,
            "memory_percent": self.memory_percent,
            "memory_rss_bytes": self.memory_rss,
            "disk_read_bytes": self.disk_read_bytes,
            "disk_write_bytes": self.disk_write_bytes,
            "network_sent_bytes": self.network_sent_bytes,
            "network_recv_bytes": self.network_recv_bytes,
            "timestamp": self.timestamp,
        }


@dataclass
class ResourceQuota:
    cpu_percent_max: float = 100.0
    memory_mb_max: float = 1024.0
    disk_mb_max: float = 10240.0


class ResourceManager:
    """Tracks resource usage per component and enforces quotas.

    Uses psutil to collect system-level and per-process metrics.
    Components can be individually tracked with optional resource quotas.

    Thread-safe.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._tracked: dict[str, int | None] = {}
        self._quotas: dict[str, ResourceQuota] = {}
        self._snapshots: dict[str, ResourceUsage] = {}

    def track(self, component_id: str, pid: int | None = None) -> None:
        with self._lock:
            self._tracked[component_id] = pid

    def untrack(self, component_id: str) -> bool:
        with self._lock:
            self._quotas.pop(component_id, None)
            self._snapshots.pop(component_id, None)
            if component_id in self._tracked:
                del self._tracked[component_id]
                return True
            return False

    def is_tracked(self, component_id: str) -> bool:
        with self._lock:
            return component_id in self._tracked

    def set_quota(self, component_id: str, quota: ResourceQuota) -> None:
        with self._lock:
            self._quotas[component_id] = quota

    def get_quota(self, component_id: str) -> ResourceQuota | None:
        with self._lock:
            return self._quotas.get(component_id)

    def remove_quota(self, component_id: str) -> bool:
        with self._lock:
            if component_id in self._quotas:
                del self._quotas[component_id]
                return True
            return False

    def get_usage(self, component_id: str) -> ResourceUsage:
        pid = self._tracked.get(component_id)
        return self._sample(pid)

    def get_all_usage(self) -> dict[str, ResourceUsage]:
        with self._lock:
            return {cid: self._sample(pid) for cid, pid in self._tracked.items()}

    def get_system_usage(self) -> ResourceUsage:
        return self._sample(None)

    def check_quota(self, component_id: str) -> list[str]:
        violations: list[str] = []
        usage = self.get_usage(component_id)
        quota = self.get_quota(component_id)
        if quota is None:
            return violations
        if usage.cpu_percent > quota.cpu_percent_max:
            violations.append(f"CPU {usage.cpu_percent:.1f}% > {quota.cpu_percent_max:.0f}%")
        usage_mb = usage.memory_rss / (1024 * 1024)
        if usage_mb > quota.memory_mb_max:
            violations.append(f"Memory {usage_mb:.1f}MB > {quota.memory_mb_max:.0f}MB")
        return violations

    def get_tracked_components(self) -> list[str]:
        with self._lock:
            return list(self._tracked.keys())

    def _sample(self, pid: int | None) -> ResourceUsage:
        try:
            if pid is not None:
                proc = psutil.Process(pid)
                cpu = proc.cpu_percent(interval=0)
                mem = proc.memory_info().rss
                mem_pct = proc.memory_percent()
                io = proc.io_counters() if hasattr(proc, "io_counters") else None
                net = psutil.net_io_counters()
                return ResourceUsage(
                    cpu_percent=cpu,
                    memory_percent=mem_pct,
                    memory_rss=mem,
                    disk_read_bytes=io.read_bytes if io else 0,
                    disk_write_bytes=io.write_bytes if io else 0,
                    network_sent_bytes=net.bytes_sent,
                    network_recv_bytes=net.bytes_recv,
                )
        except (psutil.NoSuchProcess, psutil.AccessDenied, AttributeError):
            pass
        return ResourceUsage()

    def to_dict(self) -> dict[str, Any]:
        with self._lock:
            return {
                "tracked": list(self._tracked.keys()),
                "quotas": {
                    cid: {"cpu_percent_max": q.cpu_percent_max, "memory_mb_max": q.memory_mb_max, "disk_mb_max": q.disk_mb_max}
                    for cid, q in self._quotas.items()
                },
                "system_usage": self.get_system_usage().to_dict(),
            }
