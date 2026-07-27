from __future__ import annotations

import fnmatch
import threading
from typing import Any, Callable


class EventDispatcher:
    """Client-side event system with wildcard support and thread safety.

    Supports ``subscribe()``, ``unsubscribe()``, and ``publish()``.
    Wildcard patterns (fnmatch) are supported in subscriptions.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._listeners: dict[str, list[Callable[..., None]]] = {}

    def subscribe(self, event: str, callback: Callable[..., None]) -> None:
        if not callable(callback):
            raise ValueError("callback must be callable")
        with self._lock:
            self._listeners.setdefault(event, []).append(callback)

    def unsubscribe(self, event: str, callback: Callable[..., None]) -> bool:
        with self._lock:
            handlers = self._listeners.get(event)
            if handlers is None:
                return False
            try:
                handlers.remove(callback)
                if not handlers:
                    del self._listeners[event]
                return True
            except ValueError:
                return False

    def publish(self, event: str, **data: Any) -> None:
        with self._lock:
            for pattern, handlers in list(self._listeners.items()):
                if fnmatch.fnmatch(event, pattern):
                    for handler in handlers:
                        try:
                            handler(event, **data)
                        except Exception:
                            pass

    def clear(self) -> None:
        with self._lock:
            self._listeners.clear()

    @property
    def listener_count(self) -> int:
        with self._lock:
            return sum(len(h) for h in self._listeners.values())

    @property
    def event_count(self) -> int:
        with self._lock:
            return len(self._listeners)
