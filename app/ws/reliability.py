from __future__ import annotations

import asyncio
import gzip
import json
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Callable

from app.core.logger import JarvisLogger


# ------------------------------------------------------------------
# Connection Statistics
# ------------------------------------------------------------------


@dataclass
class ConnectionStats:
    bytes_sent: int = 0
    bytes_received: int = 0
    messages_sent: int = 0
    messages_received: int = 0
    retries: int = 0
    reconnect_count: int = 0
    dropped_messages: int = 0
    queue_overflow_count: int = 0
    latency_min: float = 0.0
    latency_max: float = 0.0
    latency_avg: float = 0.0
    latency_samples: list[float] = field(default_factory=list)
    connected_at: float = 0.0

    def record_latency(self, seconds: float) -> None:
        self.latency_samples.append(seconds)
        if len(self.latency_samples) > 100:
            self.latency_samples = self.latency_samples[-100:]
        if self.latency_min == 0.0 or seconds < self.latency_min:
            self.latency_min = seconds
        if seconds > self.latency_max:
            self.latency_max = seconds
        self.latency_avg = sum(self.latency_samples) / len(self.latency_samples)

    def reset_latency(self) -> None:
        self.latency_min = 0.0
        self.latency_max = 0.0
        self.latency_avg = 0.0
        self.latency_samples.clear()

    def to_dict(self) -> dict[str, Any]:
        return {
            "bytes_sent": self.bytes_sent,
            "bytes_received": self.bytes_received,
            "messages_sent": self.messages_sent,
            "messages_received": self.messages_received,
            "retries": self.retries,
            "reconnect_count": self.reconnect_count,
            "dropped_messages": self.dropped_messages,
            "queue_overflow_count": self.queue_overflow_count,
            "latency_min": round(self.latency_min, 3),
            "latency_max": round(self.latency_max, 3),
            "latency_avg": round(self.latency_avg, 3),
        }


# ------------------------------------------------------------------
# Retry Queue - tracks unacknowledged messages
# ------------------------------------------------------------------


class RetryEntry:
    __slots__ = ("message_id", "message", "sent_at", "retry_count", "expires_at")

    def __init__(
        self,
        message_id: str,
        message: dict[str, Any],
        sent_at: float,
        max_retries: int = 3,
        retry_interval: float = 5.0,
    ) -> None:
        self.message_id = message_id
        self.message = message
        self.sent_at = sent_at
        self.retry_count = 0
        self.expires_at = sent_at + (max_retries + 1) * retry_interval + 5.0

    @property
    def is_expired(self) -> bool:
        return time.monotonic() > self.expires_at


class RetryQueue:
    """Tracks outbound messages awaiting client acknowledgement."""

    def __init__(
        self,
        client_id: str,
        max_retries: int = 3,
        retry_interval: float = 5.0,
        ack_timeout: float = 30.0,
        send_fn: Callable[[dict[str, Any]], bool] | None = None,
    ) -> None:
        self._client_id = client_id
        self._max_retries = max_retries
        self._retry_interval = retry_interval
        self._ack_timeout = ack_timeout
        self._entries: dict[str, RetryEntry] = {}
        self._lock = asyncio.Lock()
        self._send_fn = send_fn
        self._retry_task: asyncio.Task[None] | None = None

    async def add(self, message_id: str, message: dict[str, Any]) -> None:
        async with self._lock:
            self._entries[message_id] = RetryEntry(
                message_id=message_id,
                message=message,
                sent_at=time.monotonic(),
                max_retries=self._max_retries,
                retry_interval=self._retry_interval,
            )

    async def ack(self, message_id: str) -> RetryEntry | None:
        async with self._lock:
            return self._entries.pop(message_id, None)

    async def get(self, message_id: str) -> RetryEntry | None:
        async with self._lock:
            return self._entries.get(message_id)

    async def pending_count(self) -> int:
        async with self._lock:
            return len(self._entries)

    async def get_all_pending(self) -> list[RetryEntry]:
        async with self._lock:
            return list(self._entries.values())

    async def get_all_pending_dicts(self) -> list[dict[str, Any]]:
        async with self._lock:
            return [e.message for e in self._entries.values()]

    async def clear(self) -> list[dict[str, Any]]:
        async with self._lock:
            messages = [e.message for e in self._entries.values()]
            self._entries.clear()
            return messages

    def set_send_fn(self, send_fn: Callable[[dict[str, Any]], bool]) -> None:
        self._send_fn = send_fn

    async def start_retry_loop(self) -> None:
        if self._retry_task is not None and not self._retry_task.done():
            return

        async def _loop() -> None:
            while True:
                await asyncio.sleep(self._retry_interval)
                if self._send_fn is None:
                    continue
                to_retry: list[RetryEntry] = []
                expired: list[str] = []
                async with self._lock:
                    now = time.monotonic()
                    for mid, entry in list(self._entries.items()):
                        if entry.is_expired:
                            expired.append(mid)
                        elif entry.retry_count < self._max_retries:
                            if now - entry.sent_at >= self._retry_interval:
                                to_retry.append(entry)
                for mid in expired:
                    self._entries.pop(mid, None)
                for entry in to_retry:
                    entry.retry_count += 1
                    entry.sent_at = time.monotonic()
                    try:
                        result = self._send_fn(entry.message)
                        if asyncio.iscoroutine(result):
                            await result
                    except Exception:
                        pass

        self._retry_task = asyncio.create_task(_loop())

    async def stop_retry_loop(self) -> None:
        if self._retry_task is not None and not self._retry_task.done():
            self._retry_task.cancel()
            try:
                await self._retry_task
            except asyncio.CancelledError:
                pass
            self._retry_task = None


# ------------------------------------------------------------------
# Offline Queue - buffers messages for disconnected clients
# ------------------------------------------------------------------


class OfflineQueue:
    """Buffers messages for a disconnected client, drained on reconnect."""

    def __init__(
        self,
        maxsize: int = 100,
        overflow_strategy: str = "drop_oldest",
    ) -> None:
        self._maxsize = maxsize
        self._overflow_strategy = overflow_strategy
        self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=maxsize)
        self._overflow_count: int = 0

    async def put(self, message: dict[str, Any]) -> bool:
        """Add a message to the offline queue.
        Returns True if the message was queued, False if it was dropped.
        """
        try:
            self._queue.put_nowait(message)
            return True
        except asyncio.QueueFull:
            self._overflow_count += 1
            if self._overflow_strategy == "drop_oldest":
                try:
                    self._queue.get_nowait()
                    self._queue.put_nowait(message)
                except asyncio.QueueEmpty:
                    pass
            return False

    async def drain(self) -> list[dict[str, Any]]:
        """Return all queued messages and clear the queue."""
        messages: list[dict[str, Any]] = []
        while True:
            try:
                messages.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        return messages

    @property
    def qsize(self) -> int:
        return self._queue.qsize()

    @property
    def overflow_count(self) -> int:
        return self._overflow_count

    async def clear(self) -> None:
        while True:
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break


# ------------------------------------------------------------------
# Compression utilities
# ------------------------------------------------------------------


def compress_payload(payload: dict[str, Any], min_size: int = 4096) -> tuple[bytes | None, int]:
    """Gzip compress a dict payload if it exceeds *min_size* bytes.
    Returns ``(compressed_bytes | None, original_size)``.
    """
    raw = json.dumps(payload).encode("utf-8")
    if len(raw) < min_size:
        return None, len(raw)
    compressed = gzip.compress(raw)
    return compressed, len(raw)


def decompress_payload(data: bytes) -> dict[str, Any]:
    """Decompress gzip-compressed JSON bytes into a dict."""
    raw = gzip.decompress(data)
    return json.loads(raw.decode("utf-8"))
