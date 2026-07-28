from __future__ import annotations

import pytest

from app.knowledge_graph.store import GraphStore
from app.knowledge_graph.traversal import (
    PathResult,
    all_paths,
    bfs_traverse,
    dfs_traverse,
    extract_subgraph,
    k_nearest_neighbors,
    shortest_path,
)


@pytest.fixture
def graph():
    g = GraphStore()
    g.clear()
    a = g.create_entity(type="concept", name="A", id="a")
    b = g.create_entity(type="concept", name="B", id="b")
    c = g.create_entity(type="concept", name="C", id="c")
    d = g.create_entity(type="concept", name="D", id="d")
    e = g.create_entity(type="concept", name="E", id="e")
    g.create_relationship(type="related_to", source_id="a", target_id="b")
    g.create_relationship(type="related_to", source_id="b", target_id="c")
    g.create_relationship(type="related_to", source_id="b", target_id="d")
    g.create_relationship(type="related_to", source_id="c", target_id="e")
    g.create_relationship(type="related_to", source_id="d", target_id="e")
    return g


class TestShortestPath:
    def test_direct_path(self, graph):
        path = shortest_path(graph, "a", "b")
        assert path is not None
        assert path.nodes == ["a", "b"]

    def test_indirect_path(self, graph):
        path = shortest_path(graph, "a", "c")
        assert path is not None
        assert path.nodes == ["a", "b", "c"]

    def test_no_path(self, graph):
        isolated = graph.create_entity(type="concept", name="Z", id="z")
        path = shortest_path(graph, "a", "z")
        assert path is None

    def test_same_node(self, graph):
        path = shortest_path(graph, "a", "a")
        assert path is not None
        assert path.nodes == ["a"]

    def test_path_to_dict(self, graph):
        path = shortest_path(graph, "a", "b")
        d = path.to_dict()
        assert d["nodes"] == ["a", "b"]


class TestAllPaths:
    def test_single_path(self, graph):
        paths = all_paths(graph, "a", "c")
        assert len(paths) >= 1

    def test_multiple_paths(self, graph):
        paths = all_paths(graph, "a", "e")
        assert len(paths) >= 2

    def test_no_path(self, graph):
        paths = all_paths(graph, "a", "z")
        assert len(paths) == 0


class TestBfsDfs:
    def test_bfs(self, graph):
        result = bfs_traverse(graph, "a")
        assert len(result) > 0

    def test_dfs(self, graph):
        result = dfs_traverse(graph, "a")
        assert len(result) > 0


class TestKNearest:
    def test_basic(self, graph):
        neighbors = k_nearest_neighbors(graph, "a", k=3)
        assert len(neighbors) <= 3

    def test_returns_dicts(self, graph):
        neighbors = k_nearest_neighbors(graph, "a", k=2)
        for n in neighbors:
            assert "entity" in n
            assert "relationship" in n
            assert "distance" in n


class TestSubgraph:
    def test_extract(self, graph):
        sg = extract_subgraph(graph, "a", radius=1)
        assert sg["node_count"] >= 1
        assert sg["center_id"] == "a"

    def test_radius(self, graph):
        sg = extract_subgraph(graph, "a", radius=2)
        assert sg["node_count"] >= 2


class TestPathResult:
    def test_defaults(self):
        pr = PathResult()
        assert pr.nodes == []
        assert pr.edges == []
        assert pr.total_weight == 0.0
