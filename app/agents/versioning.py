from __future__ import annotations

import copy
import difflib
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from app.knowledge_graph.store import GraphStore


@dataclass
class Version:
    agent_id: str = ""
    major: int = 1
    minor: int = 0
    patch: int = 0
    snapshot: dict[str, Any] = field(default_factory=dict)
    changelog: str = ""
    compatible_system_versions: list[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)

    @property
    def semver(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "semver": self.semver,
            "major": self.major,
            "minor": self.minor,
            "patch": self.patch,
            "snapshot": copy.deepcopy(self.snapshot),
            "changelog": self.changelog,
            "compatible_system_versions": list(self.compatible_system_versions),
            "timestamp": self.timestamp,
        }


class AgentVersionManager:
    """Per-agent semantic versioning, changelog, diff, and rollback.

    Thread-safe. Versions stored in Knowledge Graph.
    """

    def __init__(self, graph_store: GraphStore | None = None) -> None:
        self._lock = threading.RLock()
        self._versions: dict[str, list[Version]] = {}
        self._current: dict[str, int] = {}  # agent_id -> index in _versions
        self._graph_store = graph_store

    # ── Version creation ─────────────────────────────────────────────

    def create_version(
        self,
        agent_id: str,
        snapshot: dict[str, Any] | None = None,
        changelog: str = "",
        compatible_versions: list[str] | None = None,
        bump: str = "minor",
    ) -> Version:
        with self._lock:
            if agent_id not in self._versions:
                self._versions[agent_id] = []
                ver = Version(
                    agent_id=agent_id,
                    major=1,
                    minor=0,
                    patch=0,
                    snapshot=snapshot or {},
                    changelog=changelog or "Initial version",
                    compatible_system_versions=compatible_versions or [],
                )
            else:
                current = self._versions[agent_id][self._current[agent_id]]
                major, minor, patch = current.major, current.minor, current.patch
                if bump == "major":
                    major += 1
                    minor = 0
                    patch = 0
                elif bump == "minor":
                    minor += 1
                    patch = 0
                elif bump == "patch":
                    patch += 1
                else:
                    minor += 1
                    patch = 0
                ver = Version(
                    agent_id=agent_id,
                    major=major,
                    minor=minor,
                    patch=patch,
                    snapshot=snapshot or current.snapshot,
                    changelog=changelog or f"Version {major}.{minor}.{patch}",
                    compatible_system_versions=compatible_versions or current.compatible_system_versions,
                )
            self._versions[agent_id].append(ver)
            self._current[agent_id] = len(self._versions[agent_id]) - 1
            self._persist(ver)
            return ver

    # ── Querying ─────────────────────────────────────────────────────

    def get_current(self, agent_id: str) -> Version | None:
        with self._lock:
            if agent_id not in self._current:
                return None
            idx = self._current[agent_id]
            if idx < len(self._versions.get(agent_id, [])):
                return self._versions[agent_id][idx]
            return None

    def get_version(self, agent_id: str, semver: str) -> Version | None:
        with self._lock:
            versions = self._versions.get(agent_id, [])
            for v in versions:
                if v.semver == semver:
                    return v
            return None

    def list_versions(self, agent_id: str) -> list[Version]:
        with self._lock:
            return list(self._versions.get(agent_id, []))

    # ── Diff ─────────────────────────────────────────────────────────

    def diff(
        self, agent_id: str, semver_a: str, semver_b: str,
    ) -> dict[str, Any]:
        ver_a = self.get_version(agent_id, semver_a)
        ver_b = self.get_version(agent_id, semver_b)
        if ver_a is None or ver_b is None:
            return {"error": "version not found"}

        snap_a = ver_a.snapshot
        snap_b = ver_b.snapshot
        added = {k: snap_b[k] for k in snap_b if k not in snap_a}
        removed = {k: snap_a[k] for k in snap_a if k not in snap_b}
        changed = {}
        for k in snap_a:
            if k in snap_b and snap_a[k] != snap_b[k]:
                changed[k] = {"from": snap_a[k], "to": snap_b[k]}

        # Text diff of string representation
        text_a = str(snap_a)
        text_b = str(snap_b)
        lines_a = text_a.splitlines()
        lines_b = text_b.splitlines()
        text_diff = list(
            difflib.unified_diff(lines_a, lines_b, lineterm="")
        )

        return {
            "agent_id": agent_id,
            "from": semver_a,
            "to": semver_b,
            "added": added,
            "removed": removed,
            "changed": changed,
            "text_diff": text_diff,
        }

    # ── Rollback ─────────────────────────────────────────────────────

    def rollback(self, agent_id: str, target_semver: str) -> Version | None:
        with self._lock:
            target = self.get_version(agent_id, target_semver)
            if target is None:
                return None
            versions = self._versions[agent_id]
            idx = next(i for i, v in enumerate(versions) if v.semver == target_semver)
            self._current[agent_id] = idx
            changelog = f"Rolled back to {target_semver}"
            ver = Version(
                agent_id=agent_id,
                major=target.major,
                minor=target.minor,
                patch=target.patch,
                snapshot=copy.deepcopy(target.snapshot),
                changelog=changelog,
                compatible_system_versions=list(target.compatible_system_versions),
            )
            versions.append(ver)
            self._current[agent_id] = len(versions) - 1
            self._persist(ver)
            return ver

    # ── Compatibility ────────────────────────────────────────────────

    def set_compatibility(
        self, agent_id: str, semver: str, system_versions: list[str],
    ) -> bool:
        ver = self.get_version(agent_id, semver)
        if ver is None:
            return False
        ver.compatible_system_versions = system_versions
        return True

    def is_compatible(self, agent_id: str, system_version: str) -> bool:
        current = self.get_current(agent_id)
        if current is None:
            return False
        return system_version in current.compatible_system_versions

    # ── Internal ─────────────────────────────────────────────────────

    def _persist(self, version: Version) -> None:
        if not self._graph_store:
            return
        self._graph_store.create_entity(
            type="version",
            name=f"version_{version.agent_id}_{version.semver}_{int(version.timestamp)}",
            properties={
                "agent_id": version.agent_id,
                "semver": version.semver,
                "changelog": version.changelog,
                "timestamp": str(version.timestamp),
                "data": str(version.to_dict()),
            },
        )

    def health(self) -> dict[str, Any]:
        with self._lock:
            return {
                "alive": True,
                "tracked_agents": len(self._versions),
                "total_versions": sum(len(v) for v in self._versions.values()),
            }
