from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from app.knowledge_graph.store import GraphStore


@dataclass
class AgentRecord:
    agent_id: str = ""
    name: str = ""
    status: str = "active"
    capabilities: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "status": self.status,
            "capabilities": list(self.capabilities),
            "dependencies": list(self.dependencies),
            "metadata": dict(self.metadata),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class AgentRegistry:
    """Agent Registry query interface over the Knowledge Graph.

    Stores agents as entities of type 'agent' in the KG, with
    capability and dependency relationships.  Provides high-level
    queries for listing, searching, and filtering agents.
    """

    def __init__(self, graph_store: GraphStore) -> None:
        self._store = graph_store

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def register_agent(
        self,
        name: str,
        agent_id: str | None = None,
        status: str = "active",
        capabilities: list[str] | None = None,
        dependencies: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AgentRecord:
        entity = self._store.create_entity(
            type="agent",
            name=name,
            properties={
                "status": status,
                **(metadata or {}),
            },
            id=agent_id,
        )

        # Link capabilities
        for cap in (capabilities or []):
            cap_entities = self._store.get_entity_by_name(cap)
            if cap_entities:
                self._store.create_relationship(
                    type="uses",
                    source_id=entity.id,
                    target_id=cap_entities[0].id,
                )

        # Link dependencies
        for dep in (dependencies or []):
            dep_entities = self._store.get_entity_by_name(dep)
            if dep_entities:
                self._store.create_relationship(
                    type="depends_on",
                    source_id=entity.id,
                    target_id=dep_entities[0].id,
                )

        return self._to_record(entity)

    def get_agent(self, agent_id: str) -> AgentRecord | None:
        entity = self._store.get_entity(agent_id)
        if entity is None or entity.type != "agent":
            return None
        return self._to_record(entity)

    def update_agent(
        self,
        agent_id: str,
        status: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AgentRecord | None:
        props: dict[str, Any] = {}
        if status is not None:
            props["status"] = status
        if metadata:
            props.update(metadata)
        entity = self._store.update_entity(agent_id, properties=props)
        if entity is None:
            return None
        return self._to_record(entity)

    def delete_agent(self, agent_id: str) -> bool:
        return self._store.delete_entity(agent_id)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def list_agents(self, status: str | None = None) -> list[AgentRecord]:
        entities = self._store.get_entities_by_type("agent")
        records = [self._to_record(e) for e in entities]
        if status:
            records = [r for r in records if r.status == status]
        return records

    def search_agents(self, query: str) -> list[AgentRecord]:
        entities = self._store.search(query)
        return [
            self._to_record(e) for e in entities
            if e.type == "agent"
        ]

    def get_agents_by_capability(self, capability_name: str) -> list[AgentRecord]:
        cap_entities = self._store.get_entity_by_name(capability_name)
        if not cap_entities:
            return []
        cap = cap_entities[0]
        results: list[AgentRecord] = []
        for rel in self._store.get_incoming_relationships(cap.id):
            if rel["type"] == "uses":
                agent = self._store.get_entity(rel["source_id"])
                if agent and agent.type == "agent":
                    results.append(self._to_record(agent))
        return results

    def get_agent_dependencies(self, agent_id: str) -> list[AgentRecord]:
        deps: list[AgentRecord] = []
        for rel in self._store.get_outgoing_relationships(agent_id):
            if rel["type"] in ("depends_on", "uses"):
                dep = self._store.get_entity(rel["target_id"])
                if dep:
                    deps.append(self._to_record(dep))
        return deps

    def get_agent_count(self) -> int:
        return len(self._store.get_entities_by_type("agent"))

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _to_record(self, entity: Any) -> AgentRecord:
        capabilities: list[str] = []
        dependencies: list[str] = []
        for rel in self._store.get_outgoing_relationships(entity.id):
            target = self._store.get_entity(rel["target_id"])
            if target is None:
                continue
            if rel["type"] == "uses":
                capabilities.append(target.name)
            elif rel["type"] == "depends_on":
                dependencies.append(target.name)

        return AgentRecord(
            agent_id=entity.id,
            name=entity.name,
            status=entity.properties.get("status", "active"),
            capabilities=capabilities,
            dependencies=dependencies,
            metadata={
                k: v for k, v in entity.properties.items()
                if k not in ("status",)
            },
        )
