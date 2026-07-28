from __future__ import annotations

from app.knowledge_graph.cascade import CircularDependencyError, would_create_cycle, validate_and_create
from app.knowledge_graph.schema import RELATIONSHIP_TYPES
from app.knowledge_graph.batch import BatchResult, batch_create_relationships, batch_delete_relationships
from app.knowledge_graph.store import GraphStore


def _graph():
    g = GraphStore()
    g.clear()
    return g


class TestRelationshipTypesRegistration:
    def test_has_minimum_40_types(self):
        types = RELATIONSHIP_TYPES.list_types()
        assert len(types) >= 40

    def test_common_types_present(self):
        expected = {
            "depends_on", "contains", "uses", "created_by",
            "references", "implements", "extends", "related_to",
            "owns", "manages", "triggers", "produces", "consumes",
            "grants", "supersedes", "derived_from",
        }
        actual = {t.name for t in RELATIONSHIP_TYPES.list_types()}
        missing = expected - actual
        assert not missing, f"Missing: {missing}"

    def test_each_type_has_description(self):
        for t in RELATIONSHIP_TYPES.list_types():
            assert t.description, f"Missing description for '{t.name}'"

    def test_type_names_are_unique(self):
        names = [t.name for t in RELATIONSHIP_TYPES.list_types()]
        assert len(names) == len(set(names))


class TestCircularDependencyDetection:
    def test_no_cycle_direct(self):
        g = _graph()
        a = g.create_entity(type="concept", name="A", id="a")
        b = g.create_entity(type="concept", name="B", id="b")
        g.create_relationship(type="depends_on", source_id="a", target_id="b")
        cycle = would_create_cycle(g, "b", "a")
        assert len(cycle) > 0  # b -> a would create cycle

    def test_no_cycle_different_branch(self):
        g = _graph()
        g.create_entity(type="concept", name="A", id="a")
        g.create_entity(type="concept", name="B", id="b")
        g.create_entity(type="concept", name="C", id="c")
        g.create_relationship(type="depends_on", source_id="a", target_id="b")
        cycle = would_create_cycle(g, "a", "c")
        assert len(cycle) == 0  # a -> c is fine

    def test_self_cycle(self):
        g = _graph()
        g.create_entity(type="concept", name="A", id="a")
        cycle = would_create_cycle(g, "a", "a")
        assert len(cycle) > 0

    def test_validate_and_create_rejects_cycle(self):
        g = _graph()
        g.create_entity(type="concept", name="A", id="a")
        g.create_entity(type="concept", name="B", id="b")
        g.create_relationship(type="depends_on", source_id="a", target_id="b")
        try:
            validate_and_create(g, "depends_on", "b", "a")
            assert False, "Should have raised CircularDependencyError"
        except CircularDependencyError:
            pass

    def test_validate_and_create_accepts_valid(self):
        g = _graph()
        g.create_entity(type="concept", name="A", id="a")
        g.create_entity(type="concept", name="B", id="b")
        rel = validate_and_create(g, "depends_on", "a", "b")
        assert rel is not None

    def test_cycle_in_deep_graph(self):
        g = _graph()
        for i in range(5):
            g.create_entity(type="concept", name=f"N{i}", id=f"n{i}")
        g.create_relationship(type="depends_on", source_id="n0", target_id="n1")
        g.create_relationship(type="depends_on", source_id="n1", target_id="n2")
        g.create_relationship(type="depends_on", source_id="n2", target_id="n3")
        g.create_relationship(type="depends_on", source_id="n3", target_id="n4")
        cycle = would_create_cycle(g, "n4", "n0")
        assert len(cycle) > 0


class TestBatchOperations:
    def test_batch_create(self):
        g = _graph()
        g.create_entity(type="concept", name="A", id="a")
        g.create_entity(type="concept", name="B", id="b")
        g.create_entity(type="concept", name="C", id="c")
        result = batch_create_relationships(g, [
            {"type": "related_to", "source_id": "a", "target_id": "b"},
            {"type": "related_to", "source_id": "b", "target_id": "c"},
        ])
        assert result.created == 2
        assert result.skipped == 0

    def test_batch_create_with_errors(self):
        g = _graph()
        g.create_entity(type="concept", name="A", id="a")
        result = batch_create_relationships(g, [
            {"type": "related_to", "source_id": "a", "target_id": "b"},  # b doesn't exist
            {"type": "related_to", "source_id": "", "target_id": ""},     # missing ids
        ])
        assert result.created == 0
        assert result.skipped == 2

    def test_batch_create_stop_on_error(self):
        g = _graph()
        g.create_entity(type="concept", name="A", id="a")
        g.create_entity(type="concept", name="B", id="b")
        result = batch_create_relationships(g, [
            {"type": "related_to", "source_id": "a", "target_id": "ghost"},
            {"type": "related_to", "source_id": "a", "target_id": "b"},
        ], continue_on_error=False)
        assert result.created == 0
        assert result.skipped == 1

    def test_batch_delete(self):
        g = _graph()
        g.create_entity(type="concept", name="A", id="a")
        g.create_entity(type="concept", name="B", id="b")
        r1 = g.create_relationship(type="related_to", source_id="a", target_id="b")
        r2 = g.create_relationship(type="related_to", source_id="a", target_id="a")
        result = batch_delete_relationships(g, [r1.id, r2.id])
        assert result.created == 2

    def test_batch_result_to_dict(self):
        br = BatchResult()
        br.created = 5
        br.duration_ms = 10.5
        d = br.to_dict()
        assert d["created"] == 5
        assert d["duration_ms"] == 10.5

    def test_batch_create_many(self):
        g = _graph()
        for i in range(5):
            g.create_entity(type="concept", name=f"N{i}", id=f"n{i}")
        rels = [
            {"type": "related_to", "source_id": f"n{i}", "target_id": f"n{i+1}"}
            for i in range(4)
        ]
        result = batch_create_relationships(g, rels, check_cycle=True)
        assert result.created == 4
