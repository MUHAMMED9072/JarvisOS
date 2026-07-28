from __future__ import annotations

import pytest

from app.agents.base import Agent, AgentMetadata, AgentStatus, AgentCapability
from app.agents.types import SystemAgent, ToolAgent, DevelopmentAgent, DomainAgent, CompositeAgent
from app.agents.factory import AgentFactory


class TestAgentStatus:
    def test_enum_values(self):
        assert AgentStatus.ACTIVE.value == "active"
        assert AgentStatus.PAUSED.value == "paused"
        assert AgentStatus.RETIRED.value == "retired"


class TestAgentCapability:
    def test_create(self):
        cap = AgentCapability(name="code_review", description="Review code quality", quality_score=0.8)
        assert cap.name == "code_review"
        assert cap.quality_score == 0.8

    def test_to_dict(self):
        cap = AgentCapability(name="test", quality_score=0.5)
        d = cap.to_dict()
        assert d["name"] == "test"
        assert d["quality_score"] == 0.5


class TestAgentMetadata:
    def test_defaults(self):
        meta = AgentMetadata()
        assert meta.status == AgentStatus.DESIGN
        assert meta.capabilities == []

    def test_to_dict(self):
        meta = AgentMetadata(
            agent_id="a1", name="TestAgent", version="2.0",
            agent_type="tool", status=AgentStatus.ACTIVE,
            capabilities=[AgentCapability(name="cap1")],
        )
        d = meta.to_dict()
        assert d["agent_id"] == "a1"
        assert d["status"] == "active"
        assert len(d["capabilities"]) == 1

    def test_from_dict(self):
        d = {"agent_id": "a1", "name": "Test", "status": "active", "capabilities": []}
        meta = AgentMetadata.from_dict(d)
        assert meta.agent_id == "a1"
        assert meta.status == AgentStatus.ACTIVE

    def test_from_dict_with_capabilities(self):
        d = {
            "agent_id": "a1",
            "capabilities": [{"name": "c1", "description": "desc", "quality_score": 0.9}],
            "status": "paused",
        }
        meta = AgentMetadata.from_dict(d)
        assert len(meta.capabilities) == 1
        assert meta.capabilities[0].name == "c1"


class TestAgentBase:
    def test_abstract_cannot_instantiate(self):
        with pytest.raises(TypeError):
            Agent(AgentMetadata())  # type: ignore

    def test_agent_properties(self):
        agent = SystemAgent()
        assert agent.agent_type == "system"
        assert agent.status == AgentStatus.DESIGN

    def test_status_setter(self):
        agent = SystemAgent()
        agent.status = AgentStatus.ACTIVE
        assert agent.status == AgentStatus.ACTIVE

    def test_to_dict(self):
        agent = SystemAgent()
        d = agent.to_dict()
        assert d["agent_type"] == "system"


class TestConcreteTypes:
    def test_system_agent_execute(self):
        agent = SystemAgent()
        result = agent.execute({"cmd": "ping"})
        assert result["status"] == "ok"
        assert "cmd" in result["context_keys"]

    def test_tool_agent_execute(self):
        agent = ToolAgent(tool_name="docker")
        result = agent.execute({"action": "build"})
        assert result["tool"] == "docker"

    def test_development_agent_execute(self):
        agent = DevelopmentAgent(language="rust")
        result = agent.execute({"task": "compile"})
        assert result["language"] == "rust"

    def test_domain_agent_execute(self):
        agent = DomainAgent(domain="security")
        result = agent.execute({"query": "scan"})
        assert result["domain"] == "security"

    def test_composite_agent_execute(self):
        sub = [SystemAgent(), ToolAgent(tool_name="git")]
        composite = CompositeAgent(sub_agents=sub)
        result = composite.execute({"test": True})
        assert result["status"] == "ok"
        assert result["count"] == 2

    def test_lifecycle_hooks(self):
        calls: list[str] = []
        agent = SystemAgent()
        agent.on_init = lambda: calls.append("init")  # type: ignore
        agent.on_start = lambda: calls.append("start")  # type: ignore
        agent.on_init()
        agent.on_start()
        assert calls == ["init", "start"]


class TestAgentFactory:
    def test_create_system(self):
        agent = AgentFactory.create("system", name="sys1")
        assert isinstance(agent, SystemAgent)
        assert agent.agent_id is not None

    def test_create_tool(self):
        agent = AgentFactory.create("tool", name="docker_tool", tool_name="docker")
        assert isinstance(agent, ToolAgent)
        assert agent.tool_name == "docker"

    def test_create_development(self):
        agent = AgentFactory.create("development", name="dev1", language="go")
        assert isinstance(agent, DevelopmentAgent)
        assert agent.language == "go"

    def test_create_domain(self):
        agent = AgentFactory.create("domain", name="dom1", domain="ml")
        assert isinstance(agent, DomainAgent)
        assert agent.domain == "ml"

    def test_create_composite(self):
        agent = AgentFactory.create("composite", name="comp1")
        assert isinstance(agent, CompositeAgent)

    def test_create_unknown_type(self):
        with pytest.raises(ValueError, match="Unknown agent type"):
            AgentFactory.create("nonexistent")

    def test_list_types(self):
        types = AgentFactory.list_types()
        assert "system" in types
        assert "tool" in types
        assert "development" in types
        assert "domain" in types
        assert "composite" in types

    def test_can_create(self):
        assert AgentFactory.can_create("system") is True
        assert AgentFactory.can_create("nonexistent") is False

    def test_register_new_type(self):
        class TestAgent(Agent):
            def execute(self, context):
                return {"ok": True}

        AgentFactory.register_type("test_type", TestAgent)
        assert AgentFactory.can_create("test_type") is True
        agent = AgentFactory.create("test_type", name="test")
        assert isinstance(agent, TestAgent)
