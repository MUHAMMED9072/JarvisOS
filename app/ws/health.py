from __future__ import annotations

import asyncio
import time
from typing import Any

from app.core.logger import JarvisLogger


class WebSocketHealthMonitor:
    """Continuously evaluates WebSocket subsystem health.

    Status levels:
    - ``healthy`` — all checks pass
    - ``degraded`` — some checks failing, service still functional
    - ``unhealthy`` — critical failures, service impaired
    """

    def __init__(
        self,
        ws_manager: Any,
        metrics_service: Any,
        event_bus: Any = None,
        interval: float = 30.0,
    ) -> None:
        self._ws = ws_manager
        self._metrics = metrics_service
        self._event_bus = event_bus
        self._interval = interval
        self._last_status: str = "healthy"
        self._task: asyncio.Task[None] | None = None

    async def evaluate(self) -> dict[str, Any]:
        """Evaluate current health and return a structured report."""
        metrics = await self._metrics.snapshot()

        checks: dict[str, dict[str, Any]] = {}
        failures: list[str] = []
        warnings: list[str] = []

        # --- Connection failures ---
        auth_fail_rate = 0
        if metrics["total_connections"] > 0:
            auth_fail_rate = metrics["total_auth_failures"] / metrics["total_connections"]
        checks["auth_failures"] = {
            "rate": round(auth_fail_rate, 4),
            "count": metrics["total_auth_failures"],
            "status": "pass" if auth_fail_rate < 0.5 else "fail",
        }
        if auth_fail_rate >= 0.5:
            failures.append("high_auth_failure_rate")

        # --- Heartbeat failures ---
        hb_failures = metrics["heartbeat_failures"]
        checks["heartbeat"] = {
            "count": hb_failures,
            "status": "pass" if hb_failures < 100 else ("warn" if hb_failures < 500 else "fail"),
        }
        if hb_failures >= 500:
            failures.append("high_heartbeat_failures")
        elif hb_failures >= 100:
            warnings.append("elevated_heartbeat_failures")

        # --- Retry rate ---
        retry_rate = 0
        if metrics["messages_sent"] > 0:
            retry_rate = metrics["retries"] / metrics["messages_sent"]
        checks["retry_rate"] = {
            "rate": round(retry_rate, 4),
            "count": metrics["retries"],
            "status": "pass" if retry_rate < 0.1 else ("warn" if retry_rate < 0.3 else "fail"),
        }
        if retry_rate >= 0.3:
            failures.append("high_retry_rate")
        elif retry_rate >= 0.1:
            warnings.append("elevated_retry_rate")

        # --- Queue saturation ---
        q_overflows = metrics["queue_overflows"]
        checks["queue_saturation"] = {
            "overflows": q_overflows,
            "status": "pass" if q_overflows < 50 else ("warn" if q_overflows < 200 else "fail"),
        }
        if q_overflows >= 200:
            failures.append("queue_saturation")
        elif q_overflows >= 50:
            warnings.append("elevated_queue_overflows")

        # --- Latency ---
        avg_latency_ms = metrics["average_latency_ms"]
        checks["latency"] = {
            "average_ms": avg_latency_ms,
            "status": "pass" if avg_latency_ms < 500 else ("warn" if avg_latency_ms < 2000 else "fail"),
        }
        if avg_latency_ms >= 2000:
            failures.append("high_latency")
        elif avg_latency_ms >= 500:
            warnings.append("elevated_latency")

        # --- Dropped messages ---
        dropped = metrics["failed_deliveries"]
        checks["dropped_messages"] = {
            "count": dropped,
            "status": "pass" if dropped < 10 else ("warn" if dropped < 50 else "fail"),
        }
        if dropped >= 50:
            failures.append("high_dropped_messages")
        elif dropped >= 10:
            warnings.append("elevated_dropped_messages")

        # --- Overall status ---
        if failures:
            status = "unhealthy"
        elif warnings:
            status = "degraded"
        else:
            status = "healthy"

        report = {
            "status": status,
            "previous_status": self._last_status,
            "checks": checks,
            "failures": failures,
            "warnings": warnings,
            "timestamp": time.time(),
        }

        # Publish on status change
        if status != self._last_status and self._event_bus is not None:
            try:
                self._event_bus.publish("ws.health.changed", **report)
            except Exception:
                pass

        self._last_status = status
        return report

    async def start(self) -> None:
        """Start periodic health evaluation."""
        if self._task is not None and not self._task.done():
            return

        async def _loop() -> None:
            while True:
                await asyncio.sleep(self._interval)
                try:
                    await self.evaluate()
                except Exception:
                    pass

        self._task = asyncio.create_task(_loop())

    async def stop(self) -> None:
        if self._task is not None and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
