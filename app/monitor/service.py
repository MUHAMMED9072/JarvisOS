from __future__ import annotations

import asyncio
import threading
import time
from datetime import datetime, timezone
from typing import Any

import psutil

from app.core.logger import JarvisLogger


class SystemMonitorService:
    """Periodically collects system metrics and publishes them via EventBus.

    Thread-safe async service with configurable update interval and
    threshold-based warning generation.  Metrics flow through the
    EventBus and are forwarded to subscribed WebSocket clients by
    the existing EventStreamBridge.
    """

    def __init__(
        self,
        registry: Any,
        event_bus: Any,
        interval: float = 5.0,
    ) -> None:
        self._registry = registry
        self._event_bus = event_bus
        self._interval = interval
        self._task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()
        self._start_time: float = time.monotonic()
        self._logger = JarvisLogger

        self._thresholds: dict[str, float] = {
            "cpu_percent": 90.0,
            "ram_percent": 90.0,
            "disk_percent": 95.0,
        }

        self._prev_net: Any | None = None
        self._prev_net_time: float = 0.0
        self._prev_disk: Any | None = None
        self._prev_disk_time: float = 0.0

        self._thread_count = 0
        self._thread_count_time = 0.0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the periodic monitoring loop."""
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._run())
        self._logger.info("SystemMonitor started (interval=%ds)", self._interval)

    async def stop(self) -> None:
        """Stop the periodic monitoring loop."""
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
            self._logger.info("SystemMonitor stopped")

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    async def set_interval(self, interval: float) -> None:
        async with self._lock:
            self._interval = interval

    async def get_interval(self) -> float:
        async with self._lock:
            return self._interval

    async def set_threshold(self, name: str, value: float) -> None:
        async with self._lock:
            self._thresholds[name] = value

    async def get_thresholds(self) -> dict[str, float]:
        async with self._lock:
            return dict(self._thresholds)

    # ------------------------------------------------------------------
    # Snapshot
    # ------------------------------------------------------------------

    async def snapshot(self) -> dict[str, Any]:
        async with self._lock:
            return self._collect()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _run(self) -> None:
        while True:
            try:
                data = self._collect()

                self._event_bus.publish("system.metrics", data=data)

                warnings = self._check_thresholds(data)
                for warning in warnings:
                    self._event_bus.publish("system.warning", data=warning)

                health = self._health(data)
                self._event_bus.publish("system.health", data=health)

            except asyncio.CancelledError:
                break
            except Exception as exc:
                self._logger.exception("SystemMonitor error: %s", exc)

            interval = await self.get_interval()
            await asyncio.sleep(interval)

    def _collect(self) -> dict[str, Any]:
        now = time.monotonic()
        uptime = now - self._start_time

        cpu_percent = psutil.cpu_percent(interval=0)
        cpu_percent_per_cpu = psutil.cpu_percent(interval=0, percpu=True)
        cpu_freq = psutil.cpu_freq()
        cpu_count_logical = psutil.cpu_count()
        cpu_count_physical = psutil.cpu_count(logical=False)

        ram = psutil.virtual_memory()
        swap = psutil.swap_memory()

        disk = psutil.disk_usage("/")

        disk_io = psutil.disk_io_counters()
        dt_disk = now - self._prev_disk_time if self._prev_disk_time > 0 else 0
        if dt_disk > 0 and self._prev_disk is not None:
            disk_read_mb_s = (
                (disk_io.read_bytes - self._prev_disk.read_bytes)
                / dt_disk / 1_048_576
            )
            disk_write_mb_s = (
                (disk_io.write_bytes - self._prev_disk.write_bytes)
                / dt_disk / 1_048_576
            )
        else:
            disk_read_mb_s = 0.0
            disk_write_mb_s = 0.0
        self._prev_disk = disk_io
        self._prev_disk_time = now

        net = psutil.net_io_counters()
        dt_net = now - self._prev_net_time if self._prev_net_time > 0 else 0
        if dt_net > 0 and self._prev_net is not None:
            net_recv_kb_s = (
                (net.bytes_recv - self._prev_net.bytes_recv)
                / dt_net / 1024
            )
            net_sent_kb_s = (
                (net.bytes_sent - self._prev_net.bytes_sent)
                / dt_net / 1024
            )
        else:
            net_recv_kb_s = 0.0
            net_sent_kb_s = 0.0
        self._prev_net = net
        self._prev_net_time = now

        process_count = len(psutil.pids())

        if now - self._thread_count_time > 10.0:
            self._thread_count = _count_system_threads()
            self._thread_count_time = now

        python_proc = psutil.Process()
        python_memory = python_proc.memory_info().rss

        result: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "uptime_seconds": uptime,
            "cpu": {
                "percent": cpu_percent,
                "percent_per_cpu": cpu_percent_per_cpu,
                "frequency_mhz": cpu_freq.current if cpu_freq else 0,
                "count_logical": cpu_count_logical,
                "count_physical": cpu_count_physical or cpu_count_logical,
            },
            "ram": {
                "total_bytes": ram.total,
                "available_bytes": ram.available,
                "used_bytes": ram.used,
                "percent": ram.percent,
            },
            "swap": {
                "total_bytes": swap.total,
                "used_bytes": swap.used,
                "percent": swap.percent,
            },
            "disk": {
                "total_bytes": disk.total,
                "used_bytes": disk.used,
                "free_bytes": disk.free,
                "percent": disk.percent,
            },
            "disk_io": {
                "read_mb_s": round(disk_read_mb_s, 2),
                "write_mb_s": round(disk_write_mb_s, 2),
            },
            "network": {
                "recv_kb_s": round(net_recv_kb_s, 2),
                "sent_kb_s": round(net_sent_kb_s, 2),
            },
            "processes": {
                "count": process_count,
                "threads": self._thread_count,
            },
            "python": {
                "memory_bytes": python_memory,
                "memory_mb": round(python_memory / 1_048_576, 2),
            },
        }

        result["ai"] = self._collect_ai_metrics()
        result["services"] = self._collect_service_counts()

        return result

    def _collect_ai_metrics(self) -> dict[str, Any]:
        metrics: dict[str, Any] = {
            "requests": 0,
            "streams": 0,
            "planning": 0,
            "reasoning": 0,
        }
        mc = self._registry.get_optional("metrics_collector")
        if mc is not None:
            try:
                snap = mc.snapshot()
                metrics["requests"] = snap.get("requests", {}).get("count", 0)
                metrics["streams"] = snap.get("streaming", {}).get("count", 0)
                metrics["planning"] = snap.get("planning", {}).get("count", 0)
                metrics["reasoning"] = snap.get("reasoning", {}).get("count", 0)
            except Exception:
                pass
        return metrics

    def _collect_service_counts(self) -> dict[str, Any]:
        counts: dict[str, Any] = {
            "plugins": 0,
            "skills": 0,
            "voice": "unknown",
            "memory_entries": 0,
        }
        pm = self._registry.get_optional("plugin_manager")
        if pm is not None:
            try:
                plugins = pm.list_plugins() if hasattr(pm, "list_plugins") else []
                counts["plugins"] = len(plugins)
            except Exception:
                pass
        sm = self._registry.get_optional("skill_manager")
        if sm is not None:
            try:
                skills = sm.list_skills() if hasattr(sm, "list_skills") else []
                counts["skills"] = len(skills)
            except Exception:
                pass
        vm = self._registry.get_optional("voice_manager")
        if vm is not None:
            try:
                counts["voice"] = (
                    "active" if getattr(vm, "is_running", False) else "inactive"
                )
            except Exception:
                pass
        mem = self._registry.get_optional("memory")
        if mem is not None:
            try:
                entries = len(mem.search("")) if hasattr(mem, "search") else 0
                counts["memory_entries"] = entries
            except Exception:
                pass
        return counts

    def _check_thresholds(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        warnings: list[dict[str, Any]] = []
        cpu = data.get("cpu", {}).get("percent", 0)
        cpu_thresh = self._thresholds.get("cpu_percent", 90)
        if cpu > cpu_thresh:
            warnings.append({
                "type": "high_cpu",
                "severity": "warning",
                "message": f"CPU usage at {cpu}% exceeds threshold {cpu_thresh}%",
                "value": cpu,
                "threshold": cpu_thresh,
            })
        ram = data.get("ram", {}).get("percent", 0)
        ram_thresh = self._thresholds.get("ram_percent", 90)
        if ram > ram_thresh:
            warnings.append({
                "type": "high_ram",
                "severity": "warning",
                "message": f"RAM usage at {ram}% exceeds threshold {ram_thresh}%",
                "value": ram,
                "threshold": ram_thresh,
            })
        disk = data.get("disk", {}).get("percent", 0)
        disk_thresh = self._thresholds.get("disk_percent", 95)
        if disk > disk_thresh:
            warnings.append({
                "type": "low_disk",
                "severity": "warning",
                "message": f"Disk usage at {disk}% exceeds threshold {disk_thresh}%",
                "value": disk,
                "threshold": disk_thresh,
            })
        return warnings

    def _health(self, data: dict[str, Any]) -> dict[str, Any]:
        cpu = data.get("cpu", {}).get("percent", 0)
        ram = data.get("ram", {}).get("percent", 0)
        disk = data.get("disk", {}).get("percent", 0)
        cpu_thresh = self._thresholds.get("cpu_percent", 90)
        ram_thresh = self._thresholds.get("ram_percent", 90)
        disk_thresh = self._thresholds.get("disk_percent", 95)
        status = "healthy"
        issues: list[str] = []
        if cpu > cpu_thresh:
            status = "degraded"
            issues.append(f"CPU at {cpu}%")
        if ram > ram_thresh:
            status = "degraded"
            issues.append(f"RAM at {ram}%")
        if disk > disk_thresh:
            status = "degraded"
            issues.append(f"Disk at {disk}%")
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": status,
            "issues": issues,
            "uptime_seconds": data.get("uptime_seconds", 0),
        }


def _count_system_threads() -> int:
    count = 0
    for proc in psutil.process_iter(["threads"]):
        try:
            info = proc.info
            if info and info["threads"]:
                count += info["threads"]
        except Exception:
            pass
    return count
