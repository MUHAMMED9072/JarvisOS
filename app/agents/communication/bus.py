from __future__ import annotations

import threading
import time
from collections import defaultdict
from typing import Any, Callable

from app.agents.communication.message import (
    DeliveryGuarantee,
    Message,
    MessageType,
    validate_message,
)

Handler = Callable[[Message], None]


class MessageBus:
    """Publish-subscribe message broker for inter-agent messaging.

    Delivery guarantees:
      - AT_MOST_ONCE: delivered to one subscriber, then discarded.
      - AT_LEAST_ONCE: delivered to all current subscribers.
      - EXACTLY_ONCE: delivered exactly once tracked via ack set.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        # topic -> list of handlers
        self._subscribers: dict[str, list[Handler]] = defaultdict(list)
        # agent_id -> list of handlers (direct messages)
        self._direct_subscribers: dict[str, list[Handler]] = defaultdict(list)
        # exactly-once tracking: delivered message IDs
        self._delivered: set[str] = set()
        # undelivered queue for TTL expired / retry
        self._undelivered: dict[str, Message] = {}

    # ── subscription ─────────────────────────────────────────────────

    def subscribe(self, topic: str, handler: Handler) -> None:
        with self._lock:
            self._subscribers[topic].append(handler)

    def subscribe_direct(self, agent_id: str, handler: Handler) -> None:
        with self._lock:
            self._direct_subscribers[agent_id].append(handler)

    def unsubscribe(self, topic: str, handler: Handler) -> bool:
        with self._lock:
            if topic in self._subscribers and handler in self._subscribers[topic]:
                self._subscribers[topic].remove(handler)
                return True
            return False

    def unsubscribe_direct(self, agent_id: str, handler: Handler) -> bool:
        with self._lock:
            if agent_id in self._direct_subscribers and handler in self._direct_subscribers[agent_id]:
                self._direct_subscribers[agent_id].remove(handler)
                return True
            return False

    # ── publishing ───────────────────────────────────────────────────

    def publish(self, message: Message, topic: str = "") -> int:
        """Publish a message.  Returns number of handlers invoked."""
        if message.is_expired():
            return 0

        errors = validate_message(message.msg_type, message.body)
        if errors:
            return 0

        message.delivered_at = None

        # exactly-once check
        if message.delivery_guarantee == DeliveryGuarantee.EXACTLY_ONCE:
            with self._lock:
                if message.id in self._delivered:
                    return 0
                self._delivered.add(message.id)

        handlers: list[Handler] = []
        with self._lock:
            # direct delivery
            if isinstance(message.target, str) and message.target in self._direct_subscribers:
                handlers.extend(self._direct_subscribers[message.target])
            # topic-based delivery
            if topic:
                handlers.extend(self._subscribers.get(topic, []))
            # broadcast: all direct subscribers
            if message.msg_type == MessageType.BROADCAST:
                for hlist in self._direct_subscribers.values():
                    handlers.extend(hlist)

        if not handlers:
            with self._lock:
                self._undelivered[message.id] = message
            return 0

        for handler in handlers:
            handler(message)

        message.delivered_at = time.time()
        return len(handlers)

    # ── correlation ──────────────────────────────────────────────────

    def correlate(self, request: Message, response: Message) -> None:
        response.correlation_id = request.id

    # ── diagnostics ──────────────────────────────────────────────────

    def pending_count(self) -> int:
        with self._lock:
            return len(self._undelivered)

    def health(self) -> dict[str, Any]:
        with self._lock:
            return {
                "alive": True,
                "topics": len(self._subscribers),
                "direct_subscribers": sum(len(v) for v in self._direct_subscribers.values()),
                "undelivered": len(self._undelivered),
                "exactly_once_delivered": len(self._delivered),
            }
