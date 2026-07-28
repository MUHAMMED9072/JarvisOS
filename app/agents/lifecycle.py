from __future__ import annotations

import threading
import time
from typing import Any, Callable

from app.agents.base import Agent, AgentStatus
from app.agents.state_machine import AgentStateMachine, TransitionError, can_transition


class LifecycleEvent:
    CREATED = "agent.lifecycle.created"
    TRANSITIONED = "agent.lifecycle.transitioned"
    STALLED = "agent.lifecycle.stalled"
    TIMEOUT = "agent.lifecycle.timeout"


class LifecycleManager:
    """Manages an agent's full lifecycle with state persistence,
    transition validation, timeout enforcement, and event publishing.

    Thread-safe.
    """

    def __init__(
        self,
        agent: Agent,
        event_callback: Callable[[str, dict[str, Any]], None] | None = None,
        timeout_seconds: float = 300.0,
    ) -> None:
        self._agent = agent
        self._machine = AgentStateMachine(initial=agent.status)
        self._event_callback = event_callback
        self._timeout_seconds = timeout_seconds
        self._lock = threading.RLock()
        self._last_transition_time: float = time.time()
        self._stalled_callbacks: list[Callable[[Agent], None]] = []

    @property
    def agent(self) -> Agent:
        return self._agent

    @property
    def state(self) -> AgentStatus:
        return self._machine.state

    def on_stalled(self, callback: Callable[[Agent], None]) -> None:
        with self._lock:
            self._stalled_callbacks.append(callback)

    def transition(self, target: AgentStatus) -> AgentStatus:
        try:
            old = self._machine.transition(target)
            self._agent.status = target
            self._last_transition_time = time.time()
            self._publish(LifecycleEvent.TRANSITIONED, {
                "agent_id": self._agent.agent_id,
                "from": old.value,
                "to": target.value,
            })
            return old
        except TransitionError:
            raise

    def extended(self, operation: str) -> AgentStatus | None:
        result = self._machine.extended_transition(operation)
        if result is not None:
            self._agent.status = self._machine.state
            self._last_transition_time = time.time()
        return result

    def allowed_transitions(self) -> list[AgentStatus]:
        return self._machine.allowed_transitions()

    def can_transition_to(self, target: AgentStatus) -> bool:
        return self._machine.can_transition_to(target)

    def check_timeout(self) -> bool:
        """Check if the current state has timed out.

        Returns True if timed out and the agent was moved to FAILED.
        """
        if self.state == AgentStatus.ACTIVE:
            return False
        elapsed = time.time() - self._last_transition_time
        if elapsed > self._timeout_seconds:
            self._publish(LifecycleEvent.TIMEOUT, {
                "agent_id": self._agent.agent_id,
                "state": self.state.value,
                "elapsed_seconds": elapsed,
            })
            self.transition(AgentStatus.FAILED)
            return True
        return False

    def check_stalled(self) -> bool:
        """Fire stalled callbacks if the agent has been in DESIGN for
        an extended period."""
        if self.state == AgentStatus.DESIGN:
            elapsed = time.time() - self._last_transition_time
            if elapsed > self._timeout_seconds * 2:
                self._publish(LifecycleEvent.STALLED, {
                    "agent_id": self._agent.agent_id,
                    "elapsed_seconds": elapsed,
                })
                with self._lock:
                    for cb in self._stalled_callbacks:
                        cb(self._agent)
                return True
        return False

    def get_state_summary(self) -> dict[str, Any]:
        return {
            "agent_id": self._agent.agent_id,
            "current_state": self.state.value,
            "timeout_seconds": self._timeout_seconds,
            "last_transition_elapsed": time.time() - self._last_transition_time,
            "allowed_transitions": [s.value for s in self.allowed_transitions()],
        }

    def _publish(self, event: str, data: dict[str, Any]) -> None:
        if self._event_callback:
            self._event_callback(event, data)

    def health(self) -> dict[str, Any]:
        return {
            "alive": True,
            "agent_id": self._agent.agent_id,
            "state": self.state.value,
            "timeout_seconds": self._timeout_seconds,
        }
