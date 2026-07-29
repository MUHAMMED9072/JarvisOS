from __future__ import annotations

import copy
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from app.agents.base import Agent, AgentCapability, AgentMetadata, AgentStatus
from app.agents.factory import AgentFactory
from app.agents.registry import AgentRegistry
from app.knowledge_graph.store import GraphStore


class MergingEvent:
    MERGED = "agent.merging.merged"
    CONFLICT = "agent.merging.conflict"
    RESOLVED = "agent.merging.resolved"
    ROLLED_BACK = "agent.merging.rolled_back"
    ERROR = "agent.merging.error"


@dataclass
class CapabilityConflict:
    capability_name: str = ""
    source_a_value: str = ""
    source_b_value: str = ""
    severity: str = "info"
    resolution: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability_name": self.capability_name,
            "source_a_value": self.source_a_value,
            "source_b_value": self.source_b_value,
            "severity": self.severity,
            "resolution": self.resolution,
        }


@dataclass
class MergeAnalysis:
    agent_a_name: str = ""
    agent_b_name: str = ""
    capabilities_a: list[str] = field(default_factory=list)
    capabilities_b: list[str] = field(default_factory=list)
    common_capabilities: list[str] = field(default_factory=list)
    union_capabilities: list[str] = field(default_factory=list)
    conflicts: list[CapabilityConflict] = field(default_factory=list)
    synergies: list[str] = field(default_factory=list)
    mergeable: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_a": self.agent_a_name,
            "agent_b": self.agent_b_name,
            "capabilities_a": list(self.capabilities_a),
            "capabilities_b": list(self.capabilities_b),
            "common_capabilities": list(self.common_capabilities),
            "union_capabilities": list(self.union_capabilities),
            "conflicts": [c.to_dict() for c in self.conflicts],
            "synergies": list(self.synergies),
            "mergeable": self.mergeable,
        }


@dataclass
class MergeResult:
    success: bool = False
    merged_agent_id: str = ""
    merged_agent_name: str = ""
    analysis: MergeAnalysis | None = None
    warnings: list[str] = field(default_factory=list)
    error_message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "merged_agent_id": self.merged_agent_id,
            "merged_agent_name": self.merged_agent_name,
            "analysis": self.analysis.to_dict() if self.analysis else None,
            "warnings": list(self.warnings),
            "error_message": self.error_message,
        }


class AgentMerging:
    """Merge two agents into one, combining their capabilities.

    Process:
      1. Analyze both agents for capability overlap and conflicts
      2. Auto-resolve non-critical conflicts
      3. Create merged agent with capability union
      4. Support rollback to pre-merge state
    """

    def __init__(
        self,
        registry: AgentRegistry,
        graph_store: GraphStore | None = None,
        event_callback: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> None:
        self._registry = registry
        self._graph = graph_store
        self._event_callback = event_callback
        self._lock = threading.RLock()
        self._merge_history: dict[str, list[dict[str, Any]]] = {}

    def analyze(self, agent_a: Agent, agent_b: Agent) -> MergeAnalysis:
        """Analyze two agents and produce a merge analysis."""
        caps_a = {c.name: c.description for c in agent_a.metadata.capabilities}
        caps_b = {c.name: c.description for c in agent_b.metadata.capabilities}

        names_a = set(caps_a.keys())
        names_b = set(caps_b.keys())

        common = names_a & names_b
        union = names_a | names_b
        only_a = names_a - names_b
        only_b = names_b - names_a

        conflicts: list[CapabilityConflict] = []
        for cap_name in common:
            if caps_a[cap_name] != caps_b[cap_name]:
                conflicts.append(CapabilityConflict(
                    capability_name=cap_name,
                    source_a_value=caps_a[cap_name],
                    source_b_value=caps_b[cap_name],
                    severity="info",
                ))

        synergies: list[str] = []
        if only_a:
            synergies.append(f"Agent A provides unique capabilities: {', '.join(sorted(only_a))}")
        if only_b:
            synergies.append(f"Agent B provides unique capabilities: {', '.join(sorted(only_b))}")
        if not conflicts:
            synergies.append("No capability conflicts detected — clean merge possible")

        return MergeAnalysis(
            agent_a_name=agent_a.metadata.name,
            agent_b_name=agent_b.metadata.name,
            capabilities_a=sorted(names_a),
            capabilities_b=sorted(names_b),
            common_capabilities=sorted(common),
            union_capabilities=sorted(union),
            conflicts=conflicts,
            synergies=synergies,
            mergeable=len(conflicts) == 0 or all(c.severity in ("info", "low") for c in conflicts),
        )

    def merge(
        self,
        agent_a: Agent,
        agent_b: Agent,
        merged_name: str = "",
        merged_version: str = "1.0.0",
        auto_resolve: bool = True,
    ) -> MergeResult:
        """Merge two agents into one."""
        analysis = self.analyze(agent_a, agent_b)
        warnings: list[str] = []

        if not analysis.mergeable:
            return MergeResult(
                success=False,
                analysis=analysis,
                error_message="Merge conflicts too severe for auto-resolution",
            )

        merged_id = uuid.uuid4().hex[:16]
        name = merged_name or f"{agent_a.metadata.name}_{agent_b.metadata.name}_merged"

        merged_caps: dict[str, AgentCapability] = {}
        for c in agent_a.metadata.capabilities:
            merged_caps[c.name] = copy.deepcopy(c)
        for c in agent_b.metadata.capabilities:
            if c.name in merged_caps:
                if auto_resolve:
                    # Auto-resolve: prefer Agent A's version by default
                    resolved = CapabilityConflict(
                        capability_name=c.name,
                        severity="resolved",
                        resolution=f"Kept version from '{agent_a.metadata.name}'",
                    )
                    self._publish(MergingEvent.RESOLVED, resolved.to_dict())
                else:
                    merged_caps[c.name] = copy.deepcopy(c)
            else:
                merged_caps[c.name] = copy.deepcopy(c)

        merged_tags = list(set(agent_a.metadata.tags + agent_b.metadata.tags + ["merged"]))

        merged_meta = AgentMetadata(
            agent_id=merged_id,
            name=name,
            version=merged_version,
            description=f"Merged agent: {agent_a.metadata.name} + {agent_b.metadata.name}",
            agent_type=agent_a.agent_type,
            status=AgentStatus.DESIGN,
            capabilities=list(merged_caps.values()),
            dependencies=list(set(agent_a.metadata.dependencies + agent_b.metadata.dependencies)),
            owner=agent_a.metadata.owner or agent_b.metadata.owner,
            tags=merged_tags,
        )

        try:
            merged = AgentFactory.create(
                agent_type=agent_a.agent_type,
                name=name,
                version=merged_version,
                description=merged_meta.description,
            )
            merged.metadata = merged_meta

            self._registry.register(merged)

            if self._graph:
                try:
                    self._graph.create_relationship(
                        type="merged_from",
                        source_id=merged_id,
                        target_id=agent_a.agent_id or agent_a.metadata.name,
                    )
                    self._graph.create_relationship(
                        type="merged_from",
                        source_id=merged_id,
                        target_id=agent_b.agent_id or agent_b.metadata.name,
                    )
                except Exception:
                    pass

            history_entry = {
                "timestamp": time.time(),
                "merged_agent_id": merged_id,
                "agent_a_id": agent_a.agent_id or agent_a.metadata.name,
                "agent_b_id": agent_b.agent_id or agent_b.metadata.name,
                "analysis": analysis.to_dict(),
            }
            with self._lock:
                if merged_id not in self._merge_history:
                    self._merge_history[merged_id] = []
                self._merge_history[merged_id].append(history_entry)

            self._publish(MergingEvent.MERGED, {
                "merged_id": merged_id,
                "merged_name": name,
                "source_a": agent_a.metadata.name,
                "source_b": agent_b.metadata.name,
            })

            return MergeResult(
                success=True,
                merged_agent_id=merged_id,
                merged_agent_name=name,
                analysis=analysis,
                warnings=warnings,
            )

        except Exception as e:
            return MergeResult(
                success=False,
                analysis=analysis,
                error_message=f"Merge failed: {e}",
                warnings=warnings,
            )

    def rollback(self, merged_agent_id: str) -> bool:
        """Rollback a merge by removing the merged agent from the registry."""
        history = self._merge_history.get(merged_agent_id, [])
        if not history or self._registry is None:
            return False

        try:
            deleted = self._registry.unregister(merged_agent_id)
            if deleted:
                with self._lock:
                    del self._merge_history[merged_agent_id]
                self._publish(MergingEvent.ROLLED_BACK, {
                    "merged_agent_id": merged_agent_id,
                })
            return deleted
        except Exception:
            return False

    def get_merge_history(self, merged_agent_id: str) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._merge_history.get(merged_agent_id, []))

    def _publish(self, event: str, data: dict[str, Any]) -> None:
        if self._event_callback:
            try:
                self._event_callback(event, data)
            except Exception:
                pass

    def health(self) -> dict[str, Any]:
        return {
            "alive": True,
            "merges_performed": sum(len(v) for v in self._merge_history.values()),
        }
