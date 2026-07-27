from __future__ import annotations

import asyncio
import time
from typing import Any

from app.core.logger import JarvisLogger


class WebsocketMetricsService:
    """Central metrics collection for the WebSocket subsystem.

    Accumulates counters across all connections and provides snapshot()
    and reset() for observability.
    """

    def __init__(
        self,
        ws_manager: Any,
        event_bus: Any = None,
    ) -> None:
        self._ws = ws_manager
        self._event_bus = event_bus
        self._lock = asyncio.Lock()

        self._total_connections = 0
        self._total_disconnections = 0
        self._total_reconnects = 0
        self._total_auth_success = 0
        self._total_auth_failures = 0
        self._total_bytes_sent = 0
        self._total_bytes_received = 0
        self._total_messages_sent = 0
        self._total_messages_received = 0
        self._total_retries = 0
        self._total_acks = 0
        self._total_failed_deliveries = 0
        self._total_heartbeat_failures = 0
        self._total_queue_overflows = 0
        self._total_compressed_bytes = 0
        self._total_uncompressed_bytes = 0
        self._total_command_executions = 0
        self._total_ai_streams = 0
        self._total_file_transfers = 0
        self._latency_samples: list[float] = []

    # ------------------------------------------------------------------
    # Record methods called from manager hooks / EventBus subscribers
    # ------------------------------------------------------------------

    def record_connect(self, is_authenticated: bool = False) -> None:
        self._total_connections += 1

    def record_disconnect(self) -> None:
        self._total_disconnections += 1

    def record_reconnect(self) -> None:
        self._total_reconnects += 1

    def record_auth_success(self) -> None:
        self._total_auth_success += 1

    def record_auth_failure(self) -> None:
        self._total_auth_failures += 1

    def record_bytes_sent(self, count: int) -> None:
        self._total_bytes_sent += count

    def record_bytes_received(self, count: int) -> None:
        self._total_bytes_received += count

    def record_message_sent(self) -> None:
        self._total_messages_sent += 1

    def record_message_received(self) -> None:
        self._total_messages_received += 1

    def record_retry(self) -> None:
        self._total_retries += 1

    def record_ack(self) -> None:
        self._total_acks += 1

    def record_failed_delivery(self) -> None:
        self._total_failed_deliveries += 1

    def record_heartbeat_failure(self) -> None:
        self._total_heartbeat_failures += 1

    def record_queue_overflow(self) -> None:
        self._total_queue_overflows += 1

    def record_compressed(self, original: int, compressed: int) -> None:
        self._total_uncompressed_bytes += original
        self._total_compressed_bytes += compressed

    def record_latency(self, seconds: float) -> None:
        self._latency_samples.append(seconds)
        if len(self._latency_samples) > 1000:
            self._latency_samples = self._latency_samples[-1000:]

    def record_command_execution(self) -> None:
        self._total_command_executions += 1

    def record_ai_stream(self) -> None:
        self._total_ai_streams += 1

    def record_file_transfer(self) -> None:
        self._total_file_transfers += 1

    # ------------------------------------------------------------------
    # Snapshot & reset
    # ------------------------------------------------------------------

    async def snapshot(self) -> dict[str, Any]:
        """Return a snapshot of all current metrics."""
        async with self._lock:
            active = await self._ws.get_active_count()
            connected = await self._ws.get_connected_ids()
            authenticated = 0
            anonymous = 0
            for cid in connected:
                info = self._ws.get_connection(cid)
                if info and info.metadata:
                    if info.metadata.get("is_authenticated", False):
                        authenticated += 1
                    else:
                        anonymous += 1

            avg_latency = 0.0
            if self._latency_samples:
                avg_latency = sum(self._latency_samples) / len(self._latency_samples)

            compression_ratio = 0.0
            if self._total_uncompressed_bytes > 0:
                ratio = self._total_compressed_bytes / self._total_uncompressed_bytes
                compression_ratio = round((1 - ratio) * 100, 1)

            return {
                "active_connections": active,
                "authenticated_connections": authenticated,
                "anonymous_connections": anonymous,
                "total_connections": self._total_connections,
                "total_disconnections": self._total_disconnections,
                "total_reconnects": self._total_reconnects,
                "total_auth_success": self._total_auth_success,
                "total_auth_failures": self._total_auth_failures,
                "bytes_sent": self._total_bytes_sent,
                "bytes_received": self._total_bytes_received,
                "messages_sent": self._total_messages_sent,
                "messages_received": self._total_messages_received,
                "retries": self._total_retries,
                "acknowledgements": self._total_acks,
                "failed_deliveries": self._total_failed_deliveries,
                "average_latency_ms": round(avg_latency * 1000, 2),
                "heartbeat_failures": self._total_heartbeat_failures,
                "queue_overflows": self._total_queue_overflows,
                "compression_ratio_percent": compression_ratio,
                "command_executions": self._total_command_executions,
                "ai_streams": self._total_ai_streams,
                "file_transfers": self._total_file_transfers,
                "timestamp": time.time(),
            }

    async def reset(self) -> None:
        """Reset all accumulated counters (active latches unaffected)."""
        async with self._lock:
            self._total_connections = 0
            self._total_disconnections = 0
            self._total_reconnects = 0
            self._total_auth_success = 0
            self._total_auth_failures = 0
            self._total_bytes_sent = 0
            self._total_bytes_received = 0
            self._total_messages_sent = 0
            self._total_messages_received = 0
            self._total_retries = 0
            self._total_acks = 0
            self._total_failed_deliveries = 0
            self._total_heartbeat_failures = 0
            self._total_queue_overflows = 0
            self._total_compressed_bytes = 0
            self._total_uncompressed_bytes = 0
            self._total_command_executions = 0
            self._total_ai_streams = 0
            self._total_file_transfers = 0
            self._latency_samples.clear()

    async def publish(self) -> None:
        """Publish current metrics to EventBus."""
        if self._event_bus is None:
            return
        try:
            snap = await self.snapshot()
            self._event_bus.publish("ws.metrics.updated", **snap)
        except Exception:
            pass
