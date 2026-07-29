from __future__ import annotations

import tempfile

from app.agents.cloning import AgentCloning, CloneResult
from app.agents.base import Agent, AgentCapability, AgentMetadata, AgentStatus
from app.agents.registry import AgentRegistry
from app.knowledge_graph.store import GraphStore


class _OriginalAgent(Agent):
    def __init__(self) -> None:
        meta = AgentMetadata(
            agent_id="original_001", name="original_agent", version="1.0.0",
            agent_type="domain", status=AgentStatus.ACTIVE,
            capabilities=[AgentCapability(name="speak", description="Speaks")],
            tags=["test"],
        )
        super().__init__(meta)

    def execute(self, context: dict) -> dict:
        return {"status": "ok", "from": self.metadata.name}


def _make_store() -> GraphStore:
    return GraphStore(filename=tempfile.mktemp(suffix=".json"))


class TestAgentCloning:
    def test_clone_agent(self) -> None:
        store = _make_store()
        reg = AgentRegistry(store)
        original = _OriginalAgent()
        reg.register(original)

        cloner = AgentCloning(reg, graph_store=store)
        result = cloner.clone_agent(original, new_name="clone_v1")
        assert result.success
        assert result.clone_type == "clone"
        assert result.clone_name == "clone_v1"

    def test_clone_has_different_id(self) -> None:
        store = _make_store()
        reg = AgentRegistry(store)
        original = _OriginalAgent()
        reg.register(original)

        cloner = AgentCloning(reg, graph_store=store)
        result = cloner.clone_agent(original)
        assert result.clone_id != original.agent_id

    def test_clone_registered_in_kg(self) -> None:
        store = _make_store()
        reg = AgentRegistry(store)
        original = _OriginalAgent()
        reg.register(original)

        cloner = AgentCloning(reg, graph_store=store)
        result = cloner.clone_agent(original)
        assert result.success
        cloned_reg = reg.get(result.clone_id)
        assert cloned_reg is not None
        assert cloned_reg.status == AgentStatus.DESIGN

    def test_fork_agent(self) -> None:
        store = _make_store()
        reg = AgentRegistry(store)
        original = _OriginalAgent()
        reg.register(original)

        cloner = AgentCloning(reg, graph_store=store)
        result = cloner.fork_agent(original, new_name="fork_v2")
        assert result.success
        assert result.clone_type == "fork"
        assert result.clone_name == "fork_v2"

    def test_fork_creates_different_id(self) -> None:
        store = _make_store()
        reg = AgentRegistry(store)
        original = _OriginalAgent()
        reg.register(original)

        cloner = AgentCloning(reg, graph_store=store)
        result = cloner.fork_agent(original)
        assert result.clone_id != original.agent_id

    def test_clone_default_name(self) -> None:
        store = _make_store()
        reg = AgentRegistry(store)
        original = _OriginalAgent()

        cloner = AgentCloning(reg)
        result = cloner.clone_agent(original)
        assert result.success
        assert "_clone" in result.clone_name

    def test_fork_default_name(self) -> None:
        store = _make_store()
        reg = AgentRegistry(store)
        original = _OriginalAgent()

        cloner = AgentCloning(reg)
        result = cloner.fork_agent(original)
        assert result.success
        assert "_fork" in result.clone_name

    def test_result_to_dict(self) -> None:
        r = CloneResult(success=True, clone_id="c1", clone_name="test_clone", original_id="o1", clone_type="clone")
        d = r.to_dict()
        assert d["success"]
        assert d["clone_name"] == "test_clone"

    def test_health(self) -> None:
        store = _make_store()
        reg = AgentRegistry(store)
        cloner = AgentCloning(reg)
        h = cloner.health()
        assert h["alive"]
