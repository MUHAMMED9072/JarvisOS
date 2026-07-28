from __future__ import annotations

import pytest

from app.knowledge_graph.query import QueryEngine, QueryResult
from app.knowledge_graph.pattern_matcher import PatternTemplate
from app.knowledge_graph.store import GraphStore


@pytest.fixture
def engine():
    g = GraphStore()
    g.clear()
    g.create_entity(type="concept", name="Alpha", id="alpha")
    g.create_entity(type="concept", name="Beta", id="beta")
    g.create_entity(type="concept", name="Gamma", id="gamma")
    g.create_relationship(type="related_to", source_id="alpha", target_id="beta")
    g.create_relationship(type="related_to", source_id="beta", target_id="gamma")
    return QueryEngine(g)


class TestQueryEngine:
    def test_get_entity_found(self, engine):
        r = engine.get_entity("alpha")
        assert r.success is True
        assert r.data["name"] == "Alpha"

    def test_get_entity_not_found(self, engine):
        r = engine.get_entity("nonexistent")
        assert r.success is False

    def test_find_entities_by_type(self, engine):
        r = engine.find_entities(type="concept")
        assert r.success is True
        assert len(r.data) == 3

    def test_find_entities_by_name(self, engine):
        r = engine.find_entities(name="Alpha")
        assert r.success is True
        assert len(r.data) == 1

    def test_search(self, engine):
        r = engine.search("Alpha")
        assert r.success is True
        assert len(r.data) >= 1

    def test_get_relationships(self, engine):
        r = engine.get_relationships("alpha")
        assert r.success is True
        assert len(r.data["outgoing"]) == 1

    def test_bfs(self, engine):
        r = engine.bfs("alpha")
        assert r.success is True

    def test_dfs(self, engine):
        r = engine.dfs("alpha")
        assert r.success is True

    def test_shortest_path(self, engine):
        r = engine.shortest_path("alpha", "gamma")
        assert r.success is True
        assert r.data["nodes"] == ["alpha", "beta", "gamma"]

    def test_shortest_path_no_path(self, engine):
        r = engine.shortest_path("alpha", "nonexistent")
        assert r.success is False

    def test_all_paths(self, engine):
        r = engine.all_paths("alpha", "gamma")
        assert r.success is True
        assert len(r.data) >= 1

    def test_k_nearest(self, engine):
        r = engine.k_nearest("alpha", k=2)
        assert r.success is True
        assert len(r.data) <= 2

    def test_subgraph(self, engine):
        r = engine.subgraph("alpha", radius=2)
        assert r.success is True
        assert r.data["node_count"] >= 1

    def test_match_pattern(self, engine):
        pattern = PatternTemplate(
            node_types={"a": "concept", "b": "concept"},
            edges=[("a", "related_to", "b")],
        )
        r = engine.match_pattern(pattern)
        assert r.success is True

    def test_store_access(self, engine):
        assert engine.store is not None

    def test_query_result_to_dict(self):
        r = QueryResult(success=True, data={"key": "value"}, execution_time_ms=1.5)
        d = r.to_dict()
        assert d["success"] is True
        assert d["data"]["key"] == "value"
