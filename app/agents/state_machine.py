from __future__ import annotations

import threading
from typing import Any

from app.agents.base import AgentStatus


class TransitionError(ValueError):
    """Raised when an illegal state transition is attempted."""

    def __init__(self, current: AgentStatus, target: AgentStatus) -> None:
        self.current = current
        self.target = target
        super().__init__(f"Illegal transition: {current.value} -> {target.value}")


# Valid transition map: current -> allowed targets
_TRANSITIONS: dict[AgentStatus, set[AgentStatus]] = {
    AgentStatus.DESIGN: {AgentStatus.BUILD, AgentStatus.ARCHIVED, AgentStatus.FAILED},
    AgentStatus.BUILD: {AgentStatus.SANDBOX, AgentStatus.DESIGN, AgentStatus.FAILED},
    AgentStatus.SANDBOX: {AgentStatus.REVIEW, AgentStatus.BUILD, AgentStatus.FAILED},
    AgentStatus.REVIEW: {AgentStatus.APPROVED, AgentStatus.BUILD, AgentStatus.FAILED},
    AgentStatus.APPROVED: {AgentStatus.INSTALLED, AgentStatus.DESIGN, AgentStatus.FAILED},
    AgentStatus.INSTALLED: {AgentStatus.ACTIVE, AgentStatus.ARCHIVED, AgentStatus.FAILED},
    AgentStatus.ACTIVE: {AgentStatus.PAUSED, AgentStatus.RETIRED, AgentStatus.FAILED},
    AgentStatus.PAUSED: {AgentStatus.ACTIVE, AgentStatus.RETIRED, AgentStatus.FAILED},
    AgentStatus.RETIRED: {AgentStatus.ARCHIVED, AgentStatus.ACTIVE, AgentStatus.FAILED},
    AgentStatus.ARCHIVED: set(),
    AgentStatus.FAILED: {AgentStatus.DESIGN, AgentStatus.ARCHIVED},
}

# Extended transitions
_EXTENDED: dict[str, tuple[AgentStatus, AgentStatus]] = {
    "upgrade": (AgentStatus.ACTIVE, AgentStatus.INSTALLED),
    "downgrade": (AgentStatus.ACTIVE, AgentStatus.INSTALLED),
    "clone": (AgentStatus.ACTIVE, AgentStatus.DESIGN),
    "fork": (AgentStatus.ACTIVE, AgentStatus.DESIGN),
    "merge": (AgentStatus.ACTIVE, AgentStatus.DESIGN),
}


def validate_transition(current: AgentStatus, target: AgentStatus) -> None:
    """Raise TransitionError if the transition is illegal."""
    allowed = _TRANSITIONS.get(current, set())
    if target not in allowed:
        raise TransitionError(current, target)


def allowed_transitions(status: AgentStatus) -> list[AgentStatus]:
    return sorted(_TRANSITIONS.get(status, set()), key=lambda s: s.value)


def can_transition(current: AgentStatus, target: AgentStatus) -> bool:
    return target in _TRANSITIONS.get(current, set())


class AgentStateMachine:
    """Thread-safe state machine for agent lifecycle management.

    Validates every transition against the transition map and
    provides hooks for lifecycle event publishing.
    """

    def __init__(self, initial: AgentStatus = AgentStatus.DESIGN) -> None:
        self._lock = threading.RLock()
        self._state = initial
        self._history: list[tuple[AgentStatus, AgentStatus, float]] = []

    @property
    def state(self) -> AgentStatus:
        with self._lock:
            return self._state

    def transition(self, target: AgentStatus) -> AgentStatus:
        import time
        with self._lock:
            validate_transition(self._state, target)
            old = self._state
            self._state = target
            self._history.append((old, target, time.time()))
            return old

    def extended_transition(self, operation: str) -> AgentStatus | None:
        import time
        mapping = _EXTENDED.get(operation)
        if mapping is None:
            return None
        current, target = mapping
        if self._state != current:
            raise TransitionError(self._state, target)
        old = self._state
        self._state = target
        self._history.append((old, target, time.time()))
        return old

    def history(self) -> list[tuple[str, str, float]]:
        with self._lock:
            return [(o.value, n.value, t) for o, n, t in self._history]

    def can_transition_to(self, target: AgentStatus) -> bool:
        return can_transition(self.state, target)

    def allowed_transitions(self) -> list[AgentStatus]:
        return allowed_transitions(self.state)

    def reset(self, status: AgentStatus = AgentStatus.DESIGN) -> None:
        with self._lock:
            self._state = status
            self._history.clear()

    def health(self) -> dict[str, Any]:
        return {
            "alive": True,
            "current_state": self._state.value,
            "history_length": len(self._history),
            "allowed_transitions": [s.value for s in self.allowed_transitions()],
        }
