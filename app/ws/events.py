from __future__ import annotations

import fnmatch
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel


# ------------------------------------------------------------------
# Replay buffer
# ------------------------------------------------------------------


class EventEnvelope(BaseModel):
    """Serialisable event payload sent from the bridge to WS clients."""

    event: str
    data: dict[str, Any] = {}
    event_id: str = ""
    timestamp: str = ""
    source: str = ""


class EventReplayBuffer:
    """Retains the most recent events so new subscribers can catch up.

    Thread-safe (single-threaded async usage expected).
    """

    def __init__(self, max_events_per_type: int = 50) -> None:
        self._max = max_events_per_type
        self._buffers: dict[str, deque[EventEnvelope]] = {}

    def push(self, envelope: EventEnvelope) -> None:
        buf = self._buffers.setdefault(envelope.event, deque(maxlen=self._max))
        buf.append(envelope)

    def replay(self, event_pattern: str) -> list[EventEnvelope]:
        """Return all buffered events matching *event_pattern* (fnmatch)."""
        result: list[EventEnvelope] = []
        for event_name, buf in self._buffers.items():
            if fnmatch.fnmatch(event_name, event_pattern):
                result.extend(buf)
        return result

    def clear(self, event: str | None = None) -> None:
        if event is None:
            self._buffers.clear()
        else:
            self._buffers.pop(event, None)

    def __len__(self) -> int:
        return sum(len(b) for b in self._buffers.values())


# ------------------------------------------------------------------
# Wildcard matching utility
# ------------------------------------------------------------------


def match_event(subscription: str, event_name: str) -> bool:
    """Return ``True`` if *event_name* matches *subscription* (fnmatch)."""
    return fnmatch.fnmatch(event_name, subscription)


def get_matching_subscriptions(
    subscriptions: set[str],
    event_name: str,
) -> list[str]:
    """Return all subscription patterns from *subscriptions* that match *event_name*."""
    return [s for s in subscriptions if match_event(s, event_name)]


# ------------------------------------------------------------------
# Envelope factory
# ------------------------------------------------------------------


def make_envelope(
    event: str,
    data: dict[str, Any] | None = None,
    source: str = "",
) -> EventEnvelope:
    """Build an ``EventEnvelope`` with a unique id and current timestamp."""
    return EventEnvelope(
        event=event,
        data=data or {},
        event_id=str(uuid.uuid4()),
        timestamp=datetime.now(timezone.utc).isoformat(),
        source=source,
    )
