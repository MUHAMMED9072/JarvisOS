from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from app.core.event_bus import EventBus
from app.core.logger import JarvisLogger


class EmergencyMode(Enum):
    NORMAL = "normal"
    SAFE_MODE = "safe_mode"
    LOCKDOWN = "lockdown"
    EMERGENCY_SHUTDOWN = "emergency_shutdown"


class ComponentCriticality(Enum):
    SYSTEM = "system"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    BACKGROUND = "background"


@dataclass
class PreservedAgentState:
    agent_id: str
    state_data: dict[str, Any]
    criticality: ComponentCriticality
    preserved_at: float = field(default_factory=time.time)
    restored: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "state_data": dict(self.state_data),
            "criticality": self.criticality.value,
            "preserved_at": self.preserved_at,
            "restored": self.restored,
        }


@dataclass
class EmergencyEvent:
    mode: EmergencyMode
    timestamp: float = field(default_factory=time.time)
    reason: str = ""
    triggered_by: str = ""
    affected_components: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "timestamp": self.timestamp,
            "reason": self.reason,
            "triggered_by": self.triggered_by,
            "affected_components": list(self.affected_components),
        }


class EmergencyHandler:
    """Manages emergency operations: shutdown, safe mode, resource lockdown.

    Features:
      - Emergency shutdown: graceful kill of non-critical agents, state preservation
      - Safe mode: disable non-essential agents, keep kernel + EC running
      - Resource lockdown: prevent new task creation during crisis
      - Recovery: restore agents from preserved state
      - Authorization: only authorized agents/humans can trigger emergency ops

    Thread-safe.
    """

    def __init__(
        self,
        event_bus: EventBus | None = None,
        authorized_triggers: set[str] | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._authorized_triggers = authorized_triggers or {"admin", "system"}
        self._lock = threading.RLock()
        self._mode: EmergencyMode = EmergencyMode.NORMAL
        self._preserved_states: dict[str, PreservedAgentState] = {}
        self._components: dict[str, ComponentCriticality] = {}
        self._shutdown_hooks: dict[str, Callable[[], None]] = {}
        self._startup_hooks: dict[str, Callable[[], None]] = {}
        self._event_history: list[EmergencyEvent] = []
        self._lockdown_active = False
        self._entered_at: float = 0.0

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def mode(self) -> EmergencyMode:
        return self._mode

    @property
    def in_emergency(self) -> bool:
        return self._mode != EmergencyMode.NORMAL

    @property
    def lockdown(self) -> bool:
        return self._lockdown_active

    # ------------------------------------------------------------------
    # Component registration
    # ------------------------------------------------------------------

    def register_component(
        self,
        component_id: str,
        criticality: ComponentCriticality = ComponentCriticality.MEDIUM,
        shutdown_hook: Callable[[], None] | None = None,
        startup_hook: Callable[[], None] | None = None,
    ) -> None:
        with self._lock:
            self._components[component_id] = criticality
            if shutdown_hook:
                self._shutdown_hooks[component_id] = shutdown_hook
            if startup_hook:
                self._startup_hooks[component_id] = startup_hook

    def unregister_component(self, component_id: str) -> bool:
        with self._lock:
            self._components.pop(component_id, None)
            self._shutdown_hooks.pop(component_id, None)
            self._startup_hooks.pop(component_id, None)
            return True

    def get_criticality(self, component_id: str) -> ComponentCriticality:
        with self._lock:
            return self._components.get(component_id, ComponentCriticality.MEDIUM)

    # ------------------------------------------------------------------
    # Authorization
    # ------------------------------------------------------------------

    def authorize(self, caller_id: str) -> bool:
        return caller_id in self._authorized_triggers

    def add_authorized_trigger(self, caller_id: str) -> None:
        with self._lock:
            self._authorized_triggers.add(caller_id)

    def remove_authorized_trigger(self, caller_id: str) -> bool:
        with self._lock:
            if caller_id in self._authorized_triggers:
                self._authorized_triggers.discard(caller_id)
                return True
            return False

    # ------------------------------------------------------------------
    # Emergency operations
    # ------------------------------------------------------------------

    def trigger_emergency_shutdown(
        self, reason: str = "", triggered_by: str = "system"
    ) -> EmergencyEvent:
        if not self.authorize(triggered_by):
            raise PermissionError(f"'{triggered_by}' is not authorized to trigger emergency shutdown")

        with self._lock:
            old_mode = self._mode
            self._mode = EmergencyMode.EMERGENCY_SHUTDOWN
            self._entered_at = time.time()
            self._lockdown_active = True

            affected = self._get_shutdown_targets()
            self._preserve_states(affected)
            self._shutdown_components(affected)

            ev = EmergencyEvent(
                mode=EmergencyMode.EMERGENCY_SHUTDOWN,
                reason=reason,
                triggered_by=triggered_by,
                affected_components=affected,
            )
            self._event_history.append(ev)

        self._publish("ec.emergency_shutdown", event_data=ev.to_dict(), old_mode=old_mode.value)
        return ev

    def trigger_safe_mode(
        self, reason: str = "", triggered_by: str = "system"
    ) -> EmergencyEvent:
        if not self.authorize(triggered_by):
            raise PermissionError(f"'{triggered_by}' is not authorized to trigger safe mode")

        with self._lock:
            old_mode = self._mode
            self._mode = EmergencyMode.SAFE_MODE
            self._entered_at = time.time()

            non_essential = self._get_non_essential()
            self._preserve_states(non_essential)
            self._shutdown_components(non_essential)

            ev = EmergencyEvent(
                mode=EmergencyMode.SAFE_MODE,
                reason=reason,
                triggered_by=triggered_by,
                affected_components=non_essential,
            )
            self._event_history.append(ev)

        self._publish("ec.safe_mode", event_data=ev.to_dict(), old_mode=old_mode.value)
        return ev

    def trigger_resource_lockdown(
        self, reason: str = "", triggered_by: str = "system"
    ) -> EmergencyEvent:
        if not self.authorize(triggered_by):
            raise PermissionError(f"'{triggered_by}' is not authorized to trigger resource lockdown")

        with self._lock:
            old_mode = self._mode
            self._mode = EmergencyMode.LOCKDOWN
            self._lockdown_active = True
            self._entered_at = time.time()

            ev = EmergencyEvent(
                mode=EmergencyMode.LOCKDOWN,
                reason=reason,
                triggered_by=triggered_by,
            )
            self._event_history.append(ev)

        self._publish("ec.resource_lockdown", event_data=ev.to_dict(), old_mode=old_mode.value)
        return ev

    def can_accept_new_tasks(self) -> bool:
        with self._lock:
            return not self._lockdown_active

    def recover(self, triggered_by: str = "system") -> EmergencyEvent:
        if not self.authorize(triggered_by):
            raise PermissionError(f"'{triggered_by}' is not authorized to trigger recovery")

        with self._lock:
            old_mode = self._mode
            self._mode = EmergencyMode.NORMAL
            self._lockdown_active = False
            restored: list[str] = []

            for agent_id, state in list(self._preserved_states.items()):
                if not state.restored:
                    hook = self._startup_hooks.get(agent_id)
                    if hook:
                        try:
                            hook()
                            state.restored = True
                            restored.append(agent_id)
                        except Exception as exc:
                            JarvisLogger.exception(f"Failed to restore '{agent_id}': {exc}")

            ev = EmergencyEvent(
                mode=EmergencyMode.NORMAL,
                reason=f"Recovered from {old_mode.value}",
                triggered_by=triggered_by,
                affected_components=restored,
            )
            self._event_history.append(ev)

        self._publish("ec.recovered", event_data=ev.to_dict(), old_mode=old_mode.value)
        return ev

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _get_shutdown_targets(self) -> list[str]:
        return [
            cid for cid, crit in self._components.items()
            if crit != ComponentCriticality.SYSTEM
        ]

    def _get_non_essential(self) -> list[str]:
        essential = {ComponentCriticality.SYSTEM, ComponentCriticality.HIGH}
        return [
            cid for cid, crit in self._components.items()
            if crit not in essential
        ]

    def _preserve_states(self, component_ids: list[str]) -> None:
        for cid in component_ids:
            self._preserved_states[cid] = PreservedAgentState(
                agent_id=cid,
                state_data={"component_id": cid, "preserved": True},
                criticality=self._components.get(cid, ComponentCriticality.MEDIUM),
            )

    def _shutdown_components(self, component_ids: list[str]) -> None:
        for cid in component_ids:
            hook = self._shutdown_hooks.get(cid)
            if hook:
                try:
                    hook()
                except Exception as exc:
                    JarvisLogger.exception(f"Emergency shutdown hook failed for '{cid}': {exc}")

    def get_preserved_state(self, agent_id: str) -> PreservedAgentState | None:
        with self._lock:
            return self._preserved_states.get(agent_id)

    def get_all_preserved_states(self) -> list[PreservedAgentState]:
        with self._lock:
            return list(self._preserved_states.values())

    def get_event_history(self) -> list[EmergencyEvent]:
        with self._lock:
            return list(self._event_history)

    def _publish(self, event: str, **data: Any) -> None:
        if self._event_bus:
            try:
                self._event_bus.publish(event, **data)
            except Exception:
                JarvisLogger.exception("EmergencyHandler: event publish failed")

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    def health(self) -> dict[str, Any]:
        with self._lock:
            return {
                "mode": self._mode.value,
                "in_emergency": self.in_emergency,
                "lockdown": self._lockdown_active,
                "components_registered": len(self._components),
                "states_preserved": len(self._preserved_states),
                "event_history_count": len(self._event_history),
            }
