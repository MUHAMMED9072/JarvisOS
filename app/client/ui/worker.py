from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any, Callable, Coroutine, Optional

logger = logging.getLogger("jarvis.client.ui.worker")


class AsyncWorker:
    def __init__(self) -> None:
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="async-worker")
        self._thread.start()

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def stop(self) -> None:
        self._running = False
        if self._loop and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._loop.stop)

    def run(self, coro: Coroutine[Any, Any, Any], callback: Optional[Callable] = None) -> None:
        if not self._loop or not self._running:
            logger.warning("AsyncWorker not running, cannot schedule coroutine")
            return

        future = asyncio.run_coroutine_threadsafe(self._run_and_callback(coro, callback), self._loop)
        return future

    async def _run_and_callback(
        self,
        coro: Coroutine[Any, Any, Any],
        callback: Optional[Callable] = None,
    ) -> Any:
        try:
            result = await coro
            if callback:
                callback(result)
            return result
        except Exception as exc:
            logger.error("Async task failed: %s", exc)
            if callback:
                callback(None, error=str(exc))
            return None

    @property
    def running(self) -> bool:
        return self._running

    @property
    def loop(self) -> Optional[asyncio.AbstractEventLoop]:
        return self._loop
