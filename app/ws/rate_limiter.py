from __future__ import annotations

import asyncio
import time


class RateLimiter:
    def __init__(self, max_messages: int = 120, window_seconds: int = 60):
        self._max_messages = max_messages
        self._window_seconds = window_seconds
        self._clients: dict[str, list[float]] = {}
        self._lock = asyncio.Lock()

    async def check(self, client_id: str) -> bool:
        now = time.monotonic()
        cutoff = now - self._window_seconds
        async with self._lock:
            timestamps = self._clients.get(client_id, [])
            timestamps = [t for t in timestamps if t > cutoff]
            self._clients[client_id] = timestamps
            if len(timestamps) >= self._max_messages:
                return False
            timestamps.append(now)
        return True

    async def record(self, client_id: str) -> None:
        now = time.monotonic()
        async with self._lock:
            self._clients.setdefault(client_id, []).append(now)

    async def get_count(self, client_id: str) -> int:
        now = time.monotonic()
        cutoff = now - self._window_seconds
        async with self._lock:
            timestamps = self._clients.get(client_id, [])
            return sum(1 for t in timestamps if t > cutoff)

    async def reset(self, client_id: str) -> None:
        async with self._lock:
            self._clients.pop(client_id, None)

    async def reset_all(self) -> None:
        async with self._lock:
            self._clients.clear()
