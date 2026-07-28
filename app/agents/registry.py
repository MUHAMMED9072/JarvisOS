from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from app.agents.base import Agent, AgentMetadata, AgentStatus
from app.knowledge_graph.store import GraphStore


@dataclass
class AgentRegistration:
    agent_id: str = ""
    name: str = ""
    status: AgentStatus = AgentStatus.DESIGN
    agent_type: str = "system"
    active_task_count: int = 0
    last_heartbeat: float = 0.0
    registered_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "status": self.status.value,
            "agent_type": self.agent_type,
            "active_task_count": self.active_task_count,
            "last_heartbeat": self.last_heartbeat,
            "registered_at": self.registered_at,
            "metadata": dict(self.metadata),
        }


class AgentRegistry:
    """KG-backed registry for agent lookup, status, and assignment.

    Builds on P4-03's AgentRegistry (KG integration) but uses the
    P5 agent model (Agent base class, AgentStatus enum).
    """

    def __init__(self, graph_store: GraphStore) -> None:
        self._store = graph_store

    def register(self, agent: Agent) -> AgentRegistration:
        entity = self._store.create_entity(
            type="agent",
            name=agent.metadata.name,
            properties={
                "agent_id": agent.agent_id,
                "status": agent.status.value,
                "agent_type": agent.agent_type,
                "version": agent.metadata.version,
            },
            id=agent.agent_id,
        )
        return self._entity_to_registration(entity)

    def get(self, agent_id: str) -> AgentRegistration | None:
        entity = self._store.get_entity(agent_id)
        if entity is None or entity.type != "agent":
            return None
        return self._entity_to_registration(entity)

    def list(self, status: AgentStatus | None = None) -> list[AgentRegistration]:
        entities = self._store.get_entities_by_type("agent")
        results = [self._entity_to_registration(e) for e in entities]
        if status:
            results = [r for r in results if r.status == status]
        return results

    def search(self, query: str) -> list[AgentRegistration]:
        return [
            self._entity_to_registration(e)
            for e in self._store.search(query)
            if e.type == "agent"
        ]

    def update_status(self, agent_id: str, status: AgentStatus) -> AgentRegistration | None:
        entity = self._store.update_entity(agent_id, properties={"status": status.value})
        if entity is None:
            return None
        return self._entity_to_registration(entity)

    def heartbeat(self, agent_id: str) -> None:
        self._store.update_entity(agent_id, properties={
            "last_heartbeat": str(time.time()),
        })

    def is_available(self, agent_id: str) -> bool:
        reg = self.get(agent_id)
        if reg is None:
            return False
        return reg.status == AgentStatus.ACTIVE

    def increment_task_count(self, agent_id: str) -> None:
        reg = self.get(agent_id)
        if reg:
            self._store.update_entity(agent_id, properties={
                "active_task_count": str(reg.active_task_count + 1),
            })

    def decrement_task_count(self, agent_id: str) -> None:
        reg = self.get(agent_id)
        if reg:
            count = max(0, reg.active_task_count - 1)
            self._store.update_entity(agent_id, properties={
                "active_task_count": str(count),
            })

    def unregister(self, agent_id: str) -> bool:
        return self._store.delete_entity(agent_id)

    def count(self) -> int:
        return len(self._store.get_entities_by_type("agent"))

    def _entity_to_registration(self, entity: Any) -> AgentRegistration:
        props = entity.properties
        return AgentRegistration(
            agent_id=entity.id,
            name=entity.name,
            status=AgentStatus(props.get("status", "design")),
            agent_type=props.get("agent_type", "system"),
            active_task_count=int(props.get("active_task_count", 0)),
            last_heartbeat=float(props.get("last_heartbeat", 0.0)),
            registered_at=float(props.get("registered_at", time.time())),
        )

    def health(self) -> dict[str, Any]:
        return {
            "alive": True,
            "registered_agents": self.count(),
        }
