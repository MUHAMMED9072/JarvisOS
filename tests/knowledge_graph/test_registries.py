from __future__ import annotations

import pytest

from app.knowledge_graph.integrations.tool_registry import ToolRegistry, ToolRecord
from app.knowledge_graph.integrations.skill_registry import SkillRegistry, SkillRecord
from app.knowledge_graph.integrations.plugin_registry import PluginRegistry, PluginRecord
from app.knowledge_graph.integrations.api_registry import ApiRegistry, ApiRecord
from app.knowledge_graph.integrations.model_registry import ModelRegistry, ModelRecord
from app.knowledge_graph.store import GraphStore


@pytest.fixture
def graph():
    g = GraphStore()
    g.clear()
    return g


class TestToolRegistry:
    def test_register_and_get(self, graph):
        r = ToolRegistry(graph)
        rec = r.register("docker", "20.10")
        assert rec.name == "docker"
        assert rec.version == "20.10"
        fetched = r.get(rec.tool_id)
        assert fetched is not None
        assert fetched.name == "docker"

    def test_list(self, graph):
        r = ToolRegistry(graph)
        r.register("a", "1")
        r.register("b", "2")
        assert len(r.list()) == 2

    def test_search(self, graph):
        r = ToolRegistry(graph)
        r.register("my-tool", "1")
        results = r.search("my-tool")
        assert len(results) == 1

    def test_delete(self, graph):
        r = ToolRegistry(graph)
        rec = r.register("temp", "1")
        assert r.delete(rec.tool_id) is True
        assert r.get(rec.tool_id) is None

    def test_record_to_dict(self):
        rec = ToolRecord(tool_id="t1", name="test", version="1.0", capabilities=["cap1"])
        d = rec.to_dict()
        assert d["tool_id"] == "t1"
        assert d["capabilities"] == ["cap1"]


class TestSkillRegistry:
    def test_register_and_get(self, graph):
        r = SkillRegistry(graph)
        rec = r.register("translate", "2.0", intents=["translate_text"])
        fetched = r.get(rec.skill_id)
        assert fetched is not None
        assert fetched.name == "translate"

    def test_list(self, graph):
        r = SkillRegistry(graph)
        r.register("a")
        r.register("b")
        assert len(r.list()) == 2

    def test_search(self, graph):
        r = SkillRegistry(graph)
        r.register("my-skill")
        assert len(r.search("my-skill")) == 1

    def test_delete(self, graph):
        r = SkillRegistry(graph)
        rec = r.register("temp")
        assert r.delete(rec.skill_id) is True

    def test_record_to_dict(self):
        rec = SkillRecord(skill_id="s1", name="test", version="1", intents=["a"])
        d = rec.to_dict()
        assert d["intents"] == ["a"]


class TestPluginRegistry:
    def test_register_and_get(self, graph):
        r = PluginRegistry(graph)
        rec = r.register("analytics", "1.5", status="active")
        fetched = r.get(rec.plugin_id)
        assert fetched is not None
        assert fetched.status == "active"

    def test_list_by_status(self, graph):
        r = PluginRegistry(graph)
        r.register("a", status="active")
        r.register("b", status="inactive")
        assert len(r.list(status="active")) == 1
        assert len(r.list()) == 2

    def test_update_status(self, graph):
        r = PluginRegistry(graph)
        rec = r.register("plug", status="inactive")
        updated = r.update_status(rec.plugin_id, "active")
        assert updated is not None
        assert updated.status == "active"

    def test_record_to_dict(self):
        rec = PluginRecord(plugin_id="p1", name="test", version="1", status="active")
        d = rec.to_dict()
        assert d["status"] == "active"


class TestApiRegistry:
    def test_register_and_get(self, graph):
        r = ApiRegistry(graph)
        rec = r.register("get-users", method="GET", path="/users", auth_required=True)
        fetched = r.get(rec.api_id)
        assert fetched is not None
        assert fetched.method == "GET"
        assert fetched.auth_required is True

    def test_list(self, graph):
        r = ApiRegistry(graph)
        r.register("a", path="/a")
        r.register("b", path="/b")
        assert len(r.list()) == 2

    def test_record_to_dict(self):
        rec = ApiRecord(api_id="a1", name="test", method="POST", path="/test", auth_required=True)
        d = rec.to_dict()
        assert d["auth_required"] is True


class TestModelRegistry:
    def test_register_and_get(self, graph):
        r = ModelRegistry(graph)
        rec = r.register("gpt4", provider="openai", version="turbo", cost_per_call=0.01, latency_ms=500)
        fetched = r.get(rec.model_id)
        assert fetched is not None
        assert fetched.provider == "openai"
        assert fetched.cost_per_call == 0.01

    def test_list(self, graph):
        r = ModelRegistry(graph)
        r.register("a")
        r.register("b")
        assert len(r.list()) == 2

    def test_record_to_dict(self):
        rec = ModelRecord(model_id="m1", name="test", provider="p", version="1", cost_per_call=0.1, latency_ms=100)
        d = rec.to_dict()
        assert d["cost_per_call"] == 0.1
        assert d["latency_ms"] == 100


class TestCrossRegistryQueries:
    def test_which_tools_does_agent_use(self, graph):
        from app.knowledge_graph.integrations.agent_registry import AgentRegistry
        tool_r = ToolRegistry(graph)
        agent_r = AgentRegistry(graph)
        tool_r.register("docker", "20.10")
        agent_r.register_agent(name="Builder", agent_id="builder_1", dependencies=["docker"])
        deps = agent_r.get_agent_dependencies("builder_1")
        assert len(deps) >= 1
        assert deps[0].name == "docker"

    def test_which_api_does_skill_call(self, graph):
        skill_r = SkillRegistry(graph)
        api_r = ApiRegistry(graph)
        skill = skill_r.register("data-fetcher")
        api = api_r.register("fetch-data", method="GET", path="/data")
        # Create relationship from skill to api
        graph.create_relationship(type="uses", source_id=skill.skill_id, target_id=api.api_id)
        outgoing = graph.get_outgoing_relationships(skill.skill_id)
        assert any(r["type"] == "uses" and r["target_id"] == api.api_id for r in outgoing)
