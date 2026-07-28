from __future__ import annotations

import pytest

from app.knowledge_graph.integrations.agent_registry import AgentRegistry, AgentRecord
from app.knowledge_graph.store import GraphStore


@pytest.fixture
def registry():
    g = GraphStore()
    g.clear()
    return AgentRegistry(g)


@pytest.fixture
def populated_registry(registry):
    agent_a = registry.register_agent(
        name="AgentA", agent_id="a1", status="active",
        capabilities=["python", "data_analysis"],
        dependencies=["tool_x"],
        metadata={"version": "1.0"},
    )
    agent_b = registry.register_agent(
        name="AgentB", agent_id="a2", status="paused",
        capabilities=["python"],
        metadata={"version": "2.0"},
    )
    registry.register_agent(
        name="AgentC", agent_id="a3", status="active",
        capabilities=["networking"],
    )
    return registry


class TestAgentRegistry:
    def test_register_and_get(self, registry):
        record = registry.register_agent(name="TestAgent", agent_id="t1")
        assert record.agent_id == "t1"
        assert record.name == "TestAgent"
        assert record.status == "active"

        fetched = registry.get_agent("t1")
        assert fetched is not None
        assert fetched.name == "TestAgent"

    def test_get_nonexistent(self, registry):
        assert registry.get_agent("nope") is None

    def test_list_agents(self, populated_registry):
        agents = populated_registry.list_agents()
        assert len(agents) == 3

    def test_list_agents_by_status(self, populated_registry):
        active = populated_registry.list_agents(status="active")
        assert len(active) == 2
        paused = populated_registry.list_agents(status="paused")
        assert len(paused) == 1

    def test_search_agents(self, populated_registry):
        results = populated_registry.search_agents("AgentA")
        assert len(results) >= 1
        assert results[0].name == "AgentA"

    def test_get_agents_by_capability(self, populated_registry):
        # Create capability entities first
        g = populated_registry._store
        g.create_entity(type="capability", name="python", id="cap_python")
        g.create_entity(type="capability", name="data_analysis", id="cap_da")
        g.create_entity(type="capability", name="networking", id="cap_net")
        # Register agents that reference these capabilities
        populated_registry.register_agent(
            name="NewAgent", agent_id="n1",
            capabilities=["python", "data_analysis"],
        )
        agents = populated_registry.get_agents_by_capability("python")
        assert len(agents) >= 1

    def test_get_agent_dependencies(self, registry):
        g = registry._store
        g.create_entity(type="tool", name="tool_x", id="tool_x")
        reg = registry.register_agent(
            name="DepAgent", agent_id="d1",
            dependencies=["tool_x"],
        )
        deps = registry.get_agent_dependencies("d1")
        assert len(deps) >= 1

    def test_update_agent_status(self, populated_registry):
        updated = populated_registry.update_agent("a1", status="retired")
        assert updated is not None
        assert updated.status == "retired"

    def test_update_agent_metadata(self, populated_registry):
        updated = populated_registry.update_agent("a1", metadata={"color": "blue"})
        assert updated is not None
        assert updated.metadata.get("color") == "blue"

    def test_delete_agent(self, populated_registry):
        assert populated_registry.delete_agent("a1") is True
        assert populated_registry.get_agent("a1") is None

    def test_get_agent_count(self, populated_registry):
        assert populated_registry.get_agent_count() == 3
        populated_registry.delete_agent("a1")
        assert populated_registry.get_agent_count() == 2

    def test_record_to_dict(self):
        r = AgentRecord(
            agent_id="a1", name="Test", status="active",
            capabilities=["py"], dependencies=["db"],
        )
        d = r.to_dict()
        assert d["agent_id"] == "a1"
        assert d["capabilities"] == ["py"]
        assert d["status"] == "active"
