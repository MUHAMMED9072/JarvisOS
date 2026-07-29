from __future__ import annotations

import json
import shutil
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from app.agents.base import Agent, AgentStatus
from app.agents.registry import AgentRegistry


class RetirementEvent:
    RETIRED = "agent.retirement.retired"
    DEPENDENCY_CHECK = "agent.retirement.dependency_check"
    STATE_SAVED = "agent.retirement.state_saved"
    ERROR = "agent.retirement.error"


@dataclass
class RetirementResult:
    success: bool = False
    agent_id: str = ""
    agent_name: str = ""
    dependencies_found: list[str] = field(default_factory=list)
    state_preserved: bool = False
    error_message: str = ""
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "dependencies_found": list(self.dependencies_found),
            "state_preserved": self.state_preserved,
            "error_message": self.error_message,
            "warnings": list(self.warnings),
        }


class AgentRetirement:
    """Gracefully retires agents with dependency checking and state preservation."""

    def __init__(
        self,
        registry: AgentRegistry,
        state_dir: str = "",
        event_callback: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> None:
        self._registry = registry
        self._state_dir = Path(state_dir or "data/agent_state")
        self._state_dir.mkdir(parents=True, exist_ok=True)
        self._event_callback = event_callback
        self._lock = threading.RLock()

    def retire_agent(self, agent: Agent) -> RetirementResult:
        agent_id = agent.agent_id or agent.metadata.name
        agent_name = agent.metadata.name

        deps = self._check_dependents(agent_id)
        warnings: list[str] = []
        if deps:
            warnings.append(f"Agent has {len(deps)} dependents that may be affected")

        if agent.status == AgentStatus.ACTIVE:
            agent.on_stop()

        state_saved = self._preserve_state(agent)

        agent.status = AgentStatus.RETIRED

        try:
            registration = self._registry.get(agent_id)
            if registration:
                self._registry.update_status(agent_id, AgentStatus.RETIRED)
        except Exception as e:
            warnings.append(f"Registry update warning: {e}")

        self._publish(RetirementEvent.RETIRED, {
            "agent_id": agent_id,
            "name": agent_name,
            "dependencies": deps,
            "state_preserved": state_saved,
        })

        return RetirementResult(
            success=True,
            agent_id=agent_id,
            agent_name=agent_name,
            dependencies_found=deps,
            state_preserved=state_saved,
            warnings=warnings,
        )

    def _check_dependents(self, agent_id: str) -> list[str]:
        dependents: list[str] = []
        try:
            for reg in self._registry.list():
                if reg.metadata.get("dependencies") and agent_id in reg.metadata["dependencies"]:
                    dependents.append(reg.agent_id)
        except Exception:
            pass
        return dependents

    def _preserve_state(self, agent: Agent) -> bool:
        try:
            state = {
                "agent_id": agent.agent_id,
                "name": agent.metadata.name,
                "version": agent.metadata.version,
                "agent_type": agent.agent_type,
                "status": agent.status.value,
                "capabilities": [c.to_dict() for c in agent.metadata.capabilities],
                "retired_at": time.time(),
            }
            state_file = self._state_dir / f"{agent.agent_id or agent.metadata.name}.json"
            state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")
            self._publish(RetirementEvent.STATE_SAVED, {"path": str(state_file)})
            return True
        except Exception:
            return False

    def list_retired(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for f in sorted(self._state_dir.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                results.append(data)
            except Exception:
                pass
        return results

    def _publish(self, event: str, data: dict[str, Any]) -> None:
        if self._event_callback:
            try:
                self._event_callback(event, data)
            except Exception:
                pass

    def health(self) -> dict[str, Any]:
        return {
            "alive": True,
            "state_dir": str(self._state_dir),
            "retired_count": len(self.list_retired()),
        }
