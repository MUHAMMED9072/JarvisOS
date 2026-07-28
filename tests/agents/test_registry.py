from __future__ import annotations

import pytest

from app.agents.base import AgentStatus
from app.agents.registry import AgentRegistry, AgentRegistration
from app.agents.types import SystemAgent, ToolAgent
from app.knowledge_graph.store import GraphStore


@pytest.fixture
def registry():
    g = GraphStore()
    g.clear()
    return AgentRegistry(g)


class TestAgentRegistry:
    def test_register(self, registry):
        agent = SystemAgent()
        agent.metadata.agent_id = "sys1"
        reg = registry.register(agent)
        assert reg.agent_id == "sys1"
        assert reg.status == AgentStatus.DESIGN

    def test_get(self, registry):
        agent = SystemAgent()
        agent.metadata.agent_id = "sys2"
        registry.register(agent)
        fetched = registry.get("sys2")
        assert fetched is not None
        assert fetched.name == "system_agent"

    def test_get_nonexistent(self, registry):
        assert registry.get("nope") is None

    def test_list(self, registry):
        a1 = SystemAgent()
        a1.metadata.agent_id = "a1"
        a2 = ToolAgent(tool_name="git")
        a2.metadata.agent_id = "a2"
        registry.register(a1)
        registry.register(a2)
        assert len(registry.list()) == 2

    def test_list_by_status(self, registry):
        agent = SystemAgent()
        agent.metadata.agent_id = "s1"
        registry.register(agent)
        registry.update_status("s1", AgentStatus.ACTIVE)
        assert len(registry.list(status=AgentStatus.ACTIVE)) == 1
        assert len(registry.list(status=AgentStatus.DESIGN)) == 0

    def test_search(self, registry):
        agent = SystemAgent()
        agent.metadata.agent_id = "searchable"
        agent.metadata.name = "FindMeAgent"
        registry.register(agent)
        results = registry.search("FindMeAgent")
        assert len(results) >= 1

    def test_update_status(self, registry):
        agent = SystemAgent()
        agent.metadata.agent_id = "updatable"
        registry.register(agent)
        updated = registry.update_status("updatable", AgentStatus.ACTIVE)
        assert updated is not None
        assert updated.status == AgentStatus.ACTIVE

    def test_heartbeat(self, registry):
        agent = SystemAgent()
        agent.metadata.agent_id = "hb1"
        registry.register(agent)
        registry.heartbeat("hb1")
        reg = registry.get("hb1")
        assert reg is not None
        assert reg.last_heartbeat > 0

    def test_is_available(self, registry):
        agent = SystemAgent()
        agent.metadata.agent_id = "avail1"
        registry.register(agent)
        assert registry.is_available("avail1") is False  # DESIGN
        registry.update_status("avail1", AgentStatus.ACTIVE)
        assert registry.is_available("avail1") is True

    def test_is_available_nonexistent(self, registry):
        assert registry.is_available("nope") is False

    def test_task_count(self, registry):
        agent = SystemAgent()
        agent.metadata.agent_id = "tc1"
        registry.register(agent)
        registry.increment_task_count("tc1")
        reg = registry.get("tc1")
        assert reg is not None
        assert reg.active_task_count == 1
        registry.decrement_task_count("tc1")
        reg = registry.get("tc1")
        assert reg.active_task_count == 0

    def test_unregister(self, registry):
        agent = SystemAgent()
        agent.metadata.agent_id = "del1"
        registry.register(agent)
        assert registry.unregister("del1") is True
        assert registry.get("del1") is None

    def test_count(self, registry):
        assert registry.count() == 0
        agent = SystemAgent()
        agent.metadata.agent_id = "c1"
        registry.register(agent)
        assert registry.count() == 1

    def test_health(self, registry):
        h = registry.health()
        assert h["alive"] is True

    def test_registration_to_dict(self):
        r = AgentRegistration(
            agent_id="a1", name="Test", status=AgentStatus.ACTIVE,
            agent_type="system", active_task_count=2,
        )
        d = r.to_dict()
        assert d["agent_id"] == "a1"
        assert d["status"] == "active"
        assert d["active_task_count"] == 2
