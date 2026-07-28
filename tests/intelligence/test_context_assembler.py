from __future__ import annotations

import pytest

from app.intelligence.context_assembler import Context, ContextAssembler


class TestContext:
    def test_defaults(self):
        c = Context()
        assert c.relevant_entities == []
        assert c.query_time_ms == 0.0

    def test_to_dict(self):
        c = Context(relevant_entities=[{"id": "e1"}], query_time_ms=12.5)
        d = c.to_dict()
        assert len(d["relevant_entities"]) == 1
        assert d["query_time_ms"] == 12.5


class TestContextAssembler:
    def test_assemble_no_matches(self, graph_store):
        assembler = ContextAssembler(graph_store)
        ctx = assembler.assemble("build a trading bot", "create")
        assert ctx.query_time_ms >= 0
        assert isinstance(ctx.relevant_entities, list)

    def test_assemble_finds_matching_entities(self, graph_store):
        graph_store.create_entity(type="tool", name="trading-bot-tool",
                                   properties={"framework": "python"})
        graph_store.create_entity(type="agent", name="test-agent",
                                   properties={"purpose": "general"})
        assembler = ContextAssembler(graph_store)
        ctx = assembler.assemble("build a trading bot", "create")
        assert len(ctx.relevant_entities) >= 1

    def test_assemble_related_artifacts(self, graph_store):
        graph_store.create_entity(type="tool", name="tool",
                                   properties={"tool_type": "data analysis"})
        graph_store.create_entity(type="skill", name="skill",
                                   properties={"domain": "data"})
        assembler = ContextAssembler(graph_store)
        ctx = assembler.assemble("build a data analysis tool", "create")
        assert len(ctx.related_artifacts) >= 2

    def test_assemble_related_artifacts_no_match(self, graph_store):
        graph_store.create_entity(type="tool", name="unrelated-tool")
        assembler = ContextAssembler(graph_store)
        ctx = assembler.assemble("build a trading bot", "create")
        # unrelated-tool name doesn't match goal description
        assert all(a.get("name") != "unrelated-tool" for a in ctx.related_artifacts)

    def test_assemble_includes_recent_goals(self, graph_store):
        graph_store.create_entity(type="concept", name="goal-1", properties={"type": "goal"})
        graph_store.create_entity(type="concept", name="goal-2", properties={"type": "goal"})
        assembler = ContextAssembler(graph_store)
        ctx = assembler.assemble("test goal", "query")
        assert len(ctx.recent_goals) >= 2

    def test_assemble_includes_preferences(self, graph_store):
        graph_store.create_entity(type="concept", name="preference-python",
                                   properties={"value": "python"})
        assembler = ContextAssembler(graph_store)
        ctx = assembler.assemble("build something", "create")
        assert len(ctx.user_preferences) >= 1

    def test_extract_search_terms(self, graph_store):
        assembler = ContextAssembler(graph_store)
        terms = assembler._extract_search_terms("Build a trading bot with Python", "create")
        assert "create" in terms
        assert "trading" in terms
        assert "python" in terms
        assert "a" not in terms  # stop word

    def test_matches_goal_by_type(self, graph_store):
        assembler = ContextAssembler(graph_store)
        from app.knowledge_graph.entity import Entity
        e = Entity(type="tool", name="some-tool")
        assert assembler._matches_goal(e, "build a tool", "tool")

    def test_matches_goal_by_name(self, graph_store):
        assembler = ContextAssembler(graph_store)
        from app.knowledge_graph.entity import Entity
        e = Entity(type="agent", name="trading")
        assert assembler._matches_goal(e, "build a trading bot", "create")

    def test_matches_goal_by_property(self, graph_store):
        assembler = ContextAssembler(graph_store)
        from app.knowledge_graph.entity import Entity
        e = Entity(type="agent", name="helper", properties={"description": "trading"})
        assert assembler._matches_goal(e, "build a trading bot", "create")

    def test_health(self, graph_store):
        assembler = ContextAssembler(graph_store)
        h = assembler.health()
        assert h["alive"]
