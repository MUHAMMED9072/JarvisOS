from __future__ import annotations

from app.knowledge_graph.schema import ENTITY_TYPES


class TestEntityTypesRegistration:
    def test_has_minimum_30_types(self):
        types = ENTITY_TYPES.list_types()
        assert len(types) >= 30

    def test_all_required_types_present(self):
        expected = {
            "project", "goal", "task", "file", "code_module",
            "agent", "capability", "tool", "skill", "plugin",
            "model", "api_endpoint", "user", "permission", "role",
            "policy", "knowledge", "memory_entry", "pattern", "heuristic",
            "workflow", "pipeline", "artifact", "event", "metric",
            "audit_log", "incident", "version", "changelog", "milestone",
            "concept",
        }
        actual = {t.name for t in ENTITY_TYPES.list_types()}
        missing = expected - actual
        assert not missing, f"Missing entity types: {missing}"

    def test_each_type_has_description(self):
        for t in ENTITY_TYPES.list_types():
            assert t.description, f"Type '{t.name}' has no description"

    def test_each_type_is_valid(self):
        for t in ENTITY_TYPES.list_types():
            assert ENTITY_TYPES.is_valid(t.name)

    def test_can_create_all_types(self):
        from app.knowledge_graph.store import GraphStore
        g = GraphStore()
        g.clear()
        required_fields = {
            "memory": {"type": "episodic"},
            "task": {"status": "pending"},
            "file": {"path": "/tmp/test"},
        }
        for t in ENTITY_TYPES.list_types():
            props = required_fields.get(t.name, {})
            entity = g.create_entity(type=t.name, name=f"test_{t.name}", properties=props)
            assert entity is not None
            assert entity.type == t.name

    def test_unknown_type_rejected(self):
        from app.knowledge_graph.store import GraphStore
        g = GraphStore()
        g.clear()
        try:
            g.create_entity(type="nonexistent_type")
            assert False, "Should have raised ValueError"
        except ValueError:
            pass

    def test_type_names_are_unique(self):
        names = [t.name for t in ENTITY_TYPES.list_types()]
        assert len(names) == len(set(names))
