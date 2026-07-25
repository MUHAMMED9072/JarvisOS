from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from typing import Any

from app.core.logger import JarvisLogger


class EventBus:
    """Simple publish/subscribe event bus."""

    def __init__(self) -> None:
        self._listeners: dict[str, list[Callable[..., Any]]] = defaultdict(list)

    def subscribe(self, event: str, callback: Callable[..., Any]) -> None:
        """Register a callback for an event."""
        self._listeners[event].append(callback)

    def unsubscribe(self, event: str, callback: Callable[..., Any]) -> None:
        """Remove a callback from an event."""
        if event in self._listeners and callback in self._listeners[event]:
            self._listeners[event].remove(callback)

    def publish(self, event: str, *args: Any, **kwargs: Any) -> None:
        """Publish an event to all subscribers.

        Subscriber exceptions are caught and logged so that one
        failing subscriber never prevents remaining subscribers
        from receiving the event.  Subscriber execution order is
        preserved.
        """
        for callback in self._listeners.get(event, []):
            try:
                callback(*args, **kwargs)
            except Exception:
                JarvisLogger.exception(
                    "EventBus: subscriber '%s' failed for event '%s'",
                    getattr(callback, "__name__", str(callback)),
                    event,
                )
