from __future__ import annotations

import fnmatch
import threading
from collections import defaultdict
from collections.abc import Callable
from typing import Any

from app.core.logger import JarvisLogger


class EventBus:
    """Thread-safe publish/subscribe event bus.

    Supports wildcard patterns (fnmatch) via ``subscribe_wildcard()``.
    All public methods are protected by a reentrant lock for thread safety.

    For example, ``subscribe_wildcard("ai.*", callback)`` matches any
    event that starts with ``"ai."`` and passes the actual event name
    as the first positional argument to the callback.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._listeners: dict[str, list[Callable[..., Any]]] = defaultdict(list)

    def subscribe(self, event: str, callback: Callable[..., Any]) -> None:
        """Register a callback for an exact event name."""
        with self._lock:
            self._listeners[event].append(callback)

    def subscribe_wildcard(self, pattern: str, callback: Callable[..., Any]) -> None:
        """Register a callback for an fnmatch wildcard pattern.

        The callback receives ``(actual_event_name, *args, **kwargs)``.
        """
        with self._lock:
            self._listeners[pattern].append(callback)

    def unsubscribe(self, event: str, callback: Callable[..., Any]) -> None:
        """Remove a callback from an event or pattern."""
        with self._lock:
            if event in self._listeners and callback in self._listeners[event]:
                self._listeners[event].remove(callback)

    def publish(self, event: str, *args: Any, **kwargs: Any) -> None:
        """Publish an event to all subscribers.

        Both exact-match and fnmatch wildcard subscribers are notified.
        Wildcard callbacks receive ``(event, *args, **kwargs)`` so they
        know which actual event fired.

        Subscriber exceptions are caught and logged so that one
        failing subscriber never prevents remaining subscribers
        from receiving the event.
        """
        with self._lock:
            patterns = list(self._listeners.items())
        for pattern, callbacks in patterns:
            if pattern == event:
                for callback in list(callbacks):
                    try:
                        callback(*args, **kwargs)
                    except Exception:
                        JarvisLogger.exception(
                            "EventBus: subscriber '%s' failed for event '%s'",
                            getattr(callback, "__name__", str(callback)),
                            event,
                        )
            elif fnmatch.fnmatch(event, pattern):
                for callback in list(callbacks):
                    try:
                        callback(event, *args, **kwargs)
                    except Exception:
                        JarvisLogger.exception(
                            "EventBus: subscriber '%s' failed for event '%s'",
                            getattr(callback, "__name__", str(callback)),
                            event,
                        )

    @property
    def listener_count(self) -> int:
        """Return the total number of registered listeners."""
        with self._lock:
            return sum(len(cbs) for cbs in self._listeners.values())

    @property
    def pattern_count(self) -> int:
        """Return the number of distinct event patterns."""
        with self._lock:
            return len(self._listeners)

    def clear(self) -> None:
        """Remove all listeners."""
        with self._lock:
            self._listeners.clear()
