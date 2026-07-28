from __future__ import annotations

import pytest

from app.knowledge_graph.pattern_matcher import PatternMatcher, PatternTemplate, MatchResult
from app.knowledge_graph.store import GraphStore


@pytest.fixture
def graph():
    g = GraphStore()
    g.clear()
    g.create_entity(type="agent", name="AgentA", id="agent_a")
    g.create_entity(type="agent", name="AgentB", id="agent_b")
    g.create_entity(type="concept", name="TaskX", id="task_x")
    g.create_entity(type="concept", name="TaskY", id="task_y")
    g.create_entity(type="concept", name="Python", id="cap_py")
    g.create_relationship(type="uses", source_id="agent_a", target_id="cap_py")
    g.create_relationship(type="uses", source_id="agent_b", target_id="cap_py")
    g.create_relationship(type="contains", source_id="agent_a", target_id="task_x")
    g.create_relationship(type="contains", source_id="agent_b", target_id="task_y")
    return g


class TestPatternMatcher:
    def test_simple_match(self, graph):
        pm = PatternMatcher(graph)
        pattern = PatternTemplate(
            node_types={"agent": "agent", "cap": "concept"},
            edges=[("agent", "uses", "cap")],
        )
        matches = pm.match(pattern)
        assert len(matches) >= 2

    def test_no_match(self, graph):
        pm = PatternMatcher(graph)
        pattern = PatternTemplate(
            node_types={"x": "concept", "y": "concept"},
            edges=[("x", "unknown_rel", "y")],
        )
        matches = pm.match(pattern)
        assert len(matches) == 0

    def test_empty_edges(self, graph):
        pm = PatternMatcher(graph)
        pattern = PatternTemplate()
        matches = pm.match(pattern)
        assert matches == []

    def test_match_result_to_dict(self):
        mr = MatchResult(
            nodes={"a": {"id": "1", "type": "agent"}},
            edges=[{"id": "r1", "type": "related"}],
        )
        d = mr.to_dict()
        assert "nodes" in d
        assert "edges" in d

    def test_pattern_template_to_dict(self):
        pt = PatternTemplate(
            node_types={"a": "agent", "b": "task"},
            edges=[("a", "assigned", "b")],
        )
        d = pt.to_dict()
        assert d["node_types"]["a"] == "agent"
        assert d["edges"][0] == ("a", "assigned", "b")
