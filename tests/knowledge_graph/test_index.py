from __future__ import annotations

import pytest

from app.knowledge_graph.entity import Entity
from app.knowledge_graph.index import EntityIndex, RelationshipIndex


class TestEntityIndex:
    def test_add_and_get_by_id(self):
        idx = EntityIndex()
        e = Entity(id="e1", type="agent", name="test")
        idx.add(e)
        assert idx.get_by_id("e1") is e

    def test_get_missing_id(self):
        idx = EntityIndex()
        assert idx.get_by_id("missing") is None

    def test_get_by_name(self):
        idx = EntityIndex()
        e1 = Entity(id="e1", type="agent", name="test")
        e2 = Entity(id="e2", type="agent", name="test")
        idx.add(e1)
        idx.add(e2)
        results = idx.get_by_name("test")
        assert len(results) == 2

    def test_get_by_name_empty(self):
        idx = EntityIndex()
        assert idx.get_by_name("missing") == []

    def test_get_by_type(self):
        idx = EntityIndex()
        e1 = Entity(id="e1", type="agent", name="a")
        e2 = Entity(id="e2", type="tool", name="b")
        e3 = Entity(id="e3", type="agent", name="c")
        idx.add(e1)
        idx.add(e2)
        idx.add(e3)
        results = idx.get_by_type("agent")
        assert len(results) == 2
        results = idx.get_by_type("tool")
        assert len(results) == 1

    def test_remove(self):
        idx = EntityIndex()
        e = Entity(id="e1", type="agent", name="test")
        idx.add(e)
        removed = idx.remove("e1")
        assert removed is e
        assert idx.get_by_id("e1") is None

    def test_remove_cleans_up_indexes(self):
        idx = EntityIndex()
        e = Entity(id="e1", type="agent", name="test")
        idx.add(e)
        idx.remove("e1")
        assert idx.get_by_name("test") == []
        assert idx.get_by_type("agent") == []

    def test_remove_missing(self):
        idx = EntityIndex()
        assert idx.remove("missing") is None

    def test_update_name(self):
        idx = EntityIndex()
        e = Entity(id="e1", type="agent", name="old")
        idx.add(e)
        e.name = "new"
        idx.update(e)
        assert idx.get_by_name("old") == []
        assert len(idx.get_by_name("new")) == 1

    def test_update_type(self):
        idx = EntityIndex()
        e = Entity(id="e1", type="agent", name="test")
        idx.add(e)
        e.type = "tool"
        idx.update(e)
        assert idx.get_by_type("agent") == []
        assert len(idx.get_by_type("tool")) == 1

    def test_count(self):
        idx = EntityIndex()
        assert idx.count() == 0
        idx.add(Entity(id="e1"))
        assert idx.count() == 1

    def test_clear(self):
        idx = EntityIndex()
        idx.add(Entity(id="e1"))
        idx.add(Entity(id="e2"))
        idx.clear()
        assert idx.count() == 0

    def test_all(self):
        idx = EntityIndex()
        idx.add(Entity(id="e1"))
        idx.add(Entity(id="e2"))
        assert len(idx.all()) == 2


class TestRelationshipIndex:
    def test_add_and_get(self):
        idx = RelationshipIndex()
        idx.add("r1", "depends_on", "a", "b", {})
        entry = idx.get("r1")
        assert entry is not None
        assert entry["type"] == "depends_on"

    def test_get_missing(self):
        idx = RelationshipIndex()
        assert idx.get("missing") is None

    def test_get_outgoing(self):
        idx = RelationshipIndex()
        idx.add("r1", "depends_on", "a", "b", {})
        idx.add("r2", "contains", "a", "c", {})
        outgoing = idx.get_outgoing("a")
        assert len(outgoing) == 2

    def test_get_incoming(self):
        idx = RelationshipIndex()
        idx.add("r1", "depends_on", "a", "b", {})
        idx.add("r2", "contains", "c", "b", {})
        incoming = idx.get_incoming("b")
        assert len(incoming) == 2

    def test_remove(self):
        idx = RelationshipIndex()
        idx.add("r1", "depends_on", "a", "b", {})
        assert idx.remove("r1") is True
        assert idx.get("r1") is None
        assert idx.get_outgoing("a") == []
        assert idx.get_incoming("b") == []

    def test_remove_missing(self):
        idx = RelationshipIndex()
        assert idx.remove("missing") is False

    def test_get_by_type(self):
        idx = RelationshipIndex()
        idx.add("r1", "depends_on", "a", "b", {})
        idx.add("r2", "contains", "a", "c", {})
        idx.add("r3", "depends_on", "b", "c", {})
        results = idx.get_by_type("depends_on")
        assert len(results) == 2

    def test_count(self):
        idx = RelationshipIndex()
        assert idx.count() == 0
        idx.add("r1", "depends_on", "a", "b", {})
        assert idx.count() == 1

    def test_clear(self):
        idx = RelationshipIndex()
        idx.add("r1", "depends_on", "a", "b", {})
        idx.clear()
        assert idx.count() == 0

    def test_bfs(self):
        idx = RelationshipIndex()
        # a -> b -> c
        idx.add("r1", "depends_on", "a", "b", {})
        idx.add("r2", "depends_on", "b", "c", {})
        results = idx.bfs("a", max_depth=5)
        assert len(results) == 2
        assert results[0]["id"] == "r1"
        assert results[1]["id"] == "r2"

    def test_bfs_respects_max_depth(self):
        idx = RelationshipIndex()
        idx.add("r1", "depends_on", "a", "b", {})
        idx.add("r2", "depends_on", "b", "c", {})
        results = idx.bfs("a", max_depth=0)
        assert len(results) == 0

    def test_dfs(self):
        idx = RelationshipIndex()
        # a -> b, a -> c
        idx.add("r1", "depends_on", "a", "b", {})
        idx.add("r2", "depends_on", "a", "c", {})
        results = idx.dfs("a", max_depth=5)
        assert len(results) == 2

    def test_bfs_no_edges(self):
        idx = RelationshipIndex()
        results = idx.bfs("isolated", max_depth=5)
        assert results == []

    def test_dfs_no_edges(self):
        idx = RelationshipIndex()
        results = idx.dfs("isolated", max_depth=5)
        assert results == []
