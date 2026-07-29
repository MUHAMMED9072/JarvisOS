from __future__ import annotations

import io
import json
import tarfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from app.agents.base import Agent, AgentCapability, AgentMetadata, AgentStatus
from app.agents.archival import ArchiveManager
from app.agents.factory import AgentFactory
from app.agents.registry import AgentRegistry
from app.agents.state_machine import can_transition


class RecoveryEvent:
    RECOVERED = "agent.recovery.recovered"
    DEPENDENCY_CHECK = "agent.recovery.dependency_check"
    COMPATIBILITY_CHECK = "agent.recovery.compatibility_check"
    ERROR = "agent.recovery.error"


@dataclass
class RecoveryResult:
    success: bool = False
    agent_id: str = ""
    agent_name: str = ""
    version: str = ""
    state_restored: bool = False
    dependencies_verified: bool = False
    compatible: bool = False
    warnings: list[str] = field(default_factory=list)
    error_message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "version": self.version,
            "state_restored": self.state_restored,
            "dependencies_verified": self.dependencies_verified,
            "compatible": self.compatible,
            "warnings": list(self.warnings),
            "error_message": self.error_message,
        }


@dataclass
class CompatibilityCheck:
    compatible: bool = True
    system_version: str = ""
    agent_version: str = ""
    issues: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "compatible": self.compatible,
            "system_version": self.system_version,
            "agent_version": self.agent_version,
            "issues": list(self.issues),
        }


class AgentRecovery:
    """Restores retired or archived agents back to active status.

    Supports recovery from:
      - Retirement state files (JSON in data/agent_state/)
      - Archive packages (tar.gz in data/agent_archives/)
    """

    def __init__(
        self,
        registry: AgentRegistry,
        archive_manager: ArchiveManager | None = None,
        state_dir: str = "",
        event_callback: Callable[[str, dict[str, Any]], None] | None = None,
        system_version: str = "1.0.0",
    ) -> None:
        self._registry = registry
        self._archive_mgr = archive_manager
        self._state_dir = Path(state_dir or "data/agent_state")
        self._event_callback = event_callback
        self._system_version = system_version
        self._lock = threading.RLock()

    def recover_from_state(self, agent_name: str) -> RecoveryResult:
        """Recover an agent from its retirement state file."""
        state_file = self._state_dir / f"{agent_name}.json"
        if not state_file.exists():
            return RecoveryResult(success=False, error_message=f"No state file found for '{agent_name}'")

        try:
            state = json.loads(state_file.read_text(encoding="utf-8"))
        except Exception as e:
            return RecoveryResult(success=False, error_message=f"Failed to read state: {e}")

        return self._recover_from_data(state)

    def recover_from_archive(self, archive_name_or_path: str) -> RecoveryResult:
        """Recover an agent from an archive package."""
        archive_path: Path | None = None

        if self._archive_mgr:
            archive_path = self._archive_mgr.get_archive_path(archive_name_or_path)

        if archive_path is None:
            candidate = Path(archive_name_or_path)
            if candidate.exists():
                archive_path = candidate

        if archive_path is None:
            return RecoveryResult(success=False, error_message=f"Archive not found: '{archive_name_or_path}'")

        try:
            with tarfile.open(archive_path, "r:gz") as tar:
                meta_member = tar.extractfile("metadata.json")
                if meta_member is None:
                    return RecoveryResult(success=False, error_message="Archive missing metadata.json")
                metadata = json.loads(meta_member.read().decode("utf-8"))
        except Exception as e:
            return RecoveryResult(success=False, error_message=f"Failed to read archive: {e}")

        return self._recover_from_data(metadata)

    def _recover_from_data(self, data: dict[str, Any]) -> RecoveryResult:
        agent_id = data.get("agent_id", "")
        agent_name = data.get("name", data.get("agent_name", "unknown"))
        version = data.get("version", "0.0.0")
        agent_type = data.get("agent_type", "system")

        compat = self._check_compatibility(version)
        warnings: list[str] = []
        if not compat.compatible:
            warnings.extend(compat.issues)

        deps = data.get("dependencies", [])
        deps_verified = self._verify_dependencies(deps)
        if deps and not deps_verified:
            warnings.append("Some dependencies may not be available")

        existing = self._registry.get(agent_id) if agent_id else None
        if existing:
            if not can_transition(existing.status, AgentStatus.ACTIVE):
                return RecoveryResult(
                    success=False,
                    error_message=f"Cannot recover agent from state '{existing.status.value}'",
                    warnings=warnings,
                )
            self._registry.update_status(agent_id, AgentStatus.ACTIVE)
        else:
            caps_data = data.get("capabilities", [])
            caps = [
                AgentCapability(name=c.get("name", ""), description=c.get("description", ""))
                if isinstance(c, dict) else AgentCapability(name=str(c))
                for c in caps_data
            ]
            meta = AgentMetadata(
                agent_id=agent_id,
                name=agent_name,
                version=version,
                description=data.get("description", ""),
                agent_type=agent_type,
                status=AgentStatus.ACTIVE,
                capabilities=caps,
                dependencies=deps,
                owner=data.get("owner", ""),
                tags=data.get("tags", []),
            )

            try:
                agent = AgentFactory.create(
                    agent_type=agent_type,
                    name=agent_name,
                    version=version,
                    description=data.get("description", ""),
                )
                self._registry.register(agent)
            except Exception as e:
                return RecoveryResult(
                    success=False,
                    error_message=f"Failed to recreate agent: {e}",
                    warnings=warnings,
                )

        self._publish(RecoveryEvent.RECOVERED, {
            "agent_id": agent_id,
            "name": agent_name,
            "version": version,
        })

        return RecoveryResult(
            success=True,
            agent_id=agent_id,
            agent_name=agent_name,
            version=version,
            state_restored=True,
            dependencies_verified=deps_verified,
            compatible=compat.compatible,
            warnings=warnings,
        )

    def _check_compatibility(self, agent_version: str) -> CompatibilityCheck:
        issues: list[str] = []
        try:
            agent_parts = [int(p) for p in agent_version.split(".")]
            system_parts = [int(p) for p in self._system_version.split(".")]
            if agent_parts[0] != system_parts[0]:
                issues.append(f"Major version mismatch: agent v{agent_version} vs system v{self._system_version}")
        except (ValueError, IndexError):
            issues.append(f"Cannot parse version: {agent_version}")

        return CompatibilityCheck(
            compatible=len(issues) == 0,
            system_version=self._system_version,
            agent_version=agent_version,
            issues=issues,
        )

    def _verify_dependencies(self, dependencies: list[str]) -> bool:
        if not dependencies:
            return True
        if self._registry is None:
            return True
        try:
            for dep in dependencies:
                self._registry.get(dep)
            return True
        except Exception:
            return False

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
            "system_version": self._system_version,
        }
