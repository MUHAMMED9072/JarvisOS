from __future__ import annotations

import copy
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from app.agents.base import Agent, AgentCapability, AgentMetadata, AgentStatus
from app.agents.factory import AgentFactory
from app.agents.lifecycle import LifecycleManager
from app.agents.registry import AgentRegistry
from app.knowledge_graph.store import GraphStore


class CloningEvent:
    CLONED = "agent.cloning.cloned"
    FORKED = "agent.cloning.forked"
    ERROR = "agent.cloning.error"


@dataclass
class CloneResult:
    success: bool = False
    clone_id: str = ""
    clone_name: str = ""
    original_id: str = ""
    clone_type: str = "clone"
    error_message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "clone_id": self.clone_id,
            "clone_name": self.clone_name,
            "original_id": self.original_id,
            "clone_type": self.clone_type,
            "error_message": self.error_message,
        }


class AgentCloning:
    """Clone and fork agents for experimentation and customization.

    - Clone: deep copy of agent with new identity, separate memory and metrics
    - Fork: create divergent version, tracked in Knowledge Graph with parent relationship
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

    def clone_agent(
        self,
        agent: Agent,
        new_name: str = "",
        new_version: str = "1.0.0",
    ) -> CloneResult:
        """Deep-copy an agent with a new identity."""
        clone_id = uuid.uuid4().hex[:16]
        name = new_name or f"{agent.metadata.name}_clone"

        clone_meta = AgentMetadata(
            agent_id=clone_id,
            name=name,
            version=new_version,
            description=agent.metadata.description,
            agent_type=agent.agent_type,
            status=AgentStatus.DESIGN,
            capabilities=[copy.deepcopy(c) for c in agent.metadata.capabilities],
            dependencies=list(agent.metadata.dependencies),
            owner=agent.metadata.owner,
            tags=list(agent.metadata.tags) + ["clone"],
        )

        try:
            cloned = AgentFactory.create(
                agent_type=agent.agent_type,
                name=name,
                version=new_version,
                description=agent.metadata.description,
            )
            cloned.metadata = clone_meta

            registration = self._registry.register(cloned)

            if self._graph:
                try:
                    self._graph.create_relationship(
                        type="cloned_from",
                        source_id=clone_id,
                        target_id=agent.agent_id or agent.metadata.name,
                    )
                except Exception:
                    pass

            self._publish(CloningEvent.CLONED, {
                "clone_id": clone_id,
                "clone_name": name,
                "original_id": agent.agent_id or agent.metadata.name,
            })

            return CloneResult(
                success=True,
                clone_id=clone_id,
                clone_name=name,
                original_id=agent.agent_id or agent.metadata.name,
                clone_type="clone",
            )

        except Exception as e:
            return CloneResult(
                success=False,
                error_message=str(e),
                original_id=agent.agent_id or agent.metadata.name,
            )

    def fork_agent(
        self,
        agent: Agent,
        new_name: str = "",
        new_version: str = "1.1.0",
    ) -> CloneResult:
        """Create a divergent fork of an agent, tracked in KG."""
        fork_id = uuid.uuid4().hex[:16]
        name = new_name or f"{agent.metadata.name}_fork"

        fork_meta = AgentMetadata(
            agent_id=fork_id,
            name=name,
            version=new_version,
            description=agent.metadata.description,
            agent_type=agent.agent_type,
            status=AgentStatus.DESIGN,
            capabilities=[copy.deepcopy(c) for c in agent.metadata.capabilities],
            dependencies=list(agent.metadata.dependencies),
            owner=agent.metadata.owner,
            tags=list(agent.metadata.tags) + ["fork"],
        )

        try:
            forked = AgentFactory.create(
                agent_type=agent.agent_type,
                name=name,
                version=new_version,
                description=agent.metadata.description,
            )
            forked.metadata = fork_meta

            registration = self._registry.register(forked)

            if self._graph:
                try:
                    self._graph.create_relationship(
                        type="forked_from",
                        source_id=fork_id,
                        target_id=agent.agent_id or agent.metadata.name,
                    )
                except Exception:
                    pass

            self._publish(CloningEvent.FORKED, {
                "fork_id": fork_id,
                "fork_name": name,
                "original_id": agent.agent_id or agent.metadata.name,
            })

            return CloneResult(
                success=True,
                clone_id=fork_id,
                clone_name=name,
                original_id=agent.agent_id or agent.metadata.name,
                clone_type="fork",
            )

        except Exception as e:
            return CloneResult(
                success=False,
                error_message=str(e),
                original_id=agent.agent_id or agent.metadata.name,
            )

    def _publish(self, event: str, data: dict[str, Any]) -> None:
        if self._event_callback:
            try:
                self._event_callback(event, data)
            except Exception:
                pass

    def health(self) -> dict[str, Any]:
        return {"alive": True}
