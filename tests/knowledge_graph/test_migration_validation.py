from __future__ import annotations

from app.knowledge_graph.migration import MigrationRunner, DataMigration
from app.knowledge_graph.validation import DataValidator, ValidationResult
from app.knowledge_graph.store import GraphStore


def _graph():
    g = GraphStore()
    g.clear()
    return g


class TestMigrationRunner:
    def test_import_entities(self):
        g = _graph()
        runner = MigrationRunner(g)
        result = runner.import_entities([
            {"type": "agent", "name": "Bot1", "id": "b1"},
            {"type": "tool", "name": "Hammer", "id": "h1"},
        ])
        assert result.entities_migrated == 2
        assert result.completed is True
        assert g.get_entity("b1") is not None

    def test_import_entities_with_invalid_type(self):
        g = _graph()
        runner = MigrationRunner(g)
        result = runner.import_entities([
            {"type": "bogus_type", "name": "X"},
            {"type": "agent", "name": "Valid"},
        ])
        assert result.entities_migrated == 1
        assert len(result.errors) == 1

    def test_import_entities_stop_on_error(self):
        g = _graph()
        runner = MigrationRunner(g)
        result = runner.import_entities([
            {"type": "bogus", "name": "X"},
            {"type": "agent", "name": "Valid"},
        ], continue_on_error=False)
        assert result.entities_migrated == 0
        assert len(result.errors) == 1

    def test_import_relationships(self):
        g = _graph()
        g.create_entity(type="agent", name="A", id="a")
        g.create_entity(type="tool", name="T", id="t")
        runner = MigrationRunner(g)
        result = runner.import_relationships([
            {"type": "uses", "source_id": "a", "target_id": "t"},
        ])
        assert result.relationships_migrated == 1
        assert g.relationship_count() == 1

    def test_import_relationships_missing_ids(self):
        g = _graph()
        runner = MigrationRunner(g)
        result = runner.import_relationships([
            {"type": "related_to", "source_id": "", "target_id": ""},
        ])
        assert result.relationships_migrated == 0
        assert len(result.errors) >= 1

    def test_list_migrations(self):
        g = _graph()
        runner = MigrationRunner(g)
        runner.import_entities([{"type": "agent", "name": "A"}])
        assert len(runner.list_migrations()) == 1

    def test_rollback(self):
        g = _graph()
        runner = MigrationRunner(g)
        result = runner.import_entities([{"type": "agent", "name": "A", "id": "a"}])
        assert runner.rollback(result.migration_id) is True

    def test_data_migration_to_dict(self):
        dm = DataMigration(migration_id="m1", entities_migrated=5, completed=True)
        d = dm.to_dict()
        assert d["migration_id"] == "m1"
        assert d["entities_migrated"] == 5


class TestDataValidator:
    def test_validate_valid_graph(self):
        g = _graph()
        g.create_entity(type="agent", name="A", id="a")
        g.create_entity(type="tool", name="T", id="t")
        g.create_relationship(type="uses", source_id="a", target_id="t")
        validator = DataValidator(g)
        result = validator.validate_all()
        assert result.valid is True
        assert result.entity_count == 2
        assert result.relationship_count == 1

    def test_validate_without_orphans(self):
        g = _graph()
        g.create_entity(type="agent", name="A", id="a")
        g.create_entity(type="tool", name="T", id="t")
        g.create_relationship(type="uses", source_id="a", target_id="t")
        validator = DataValidator(g)
        result = validator.validate_all()
        assert result.valid is True
        assert result.entity_count == 2

    def test_validate_entity_found(self):
        g = _graph()
        g.create_entity(type="agent", name="A", id="a")
        validator = DataValidator(g)
        result = validator.validate_entity("a")
        assert result.valid is True

    def test_validate_entity_not_found(self):
        g = _graph()
        validator = DataValidator(g)
        result = validator.validate_entity("nonexistent")
        assert result.valid is False

    def test_validate_relationship_found(self):
        g = _graph()
        g.create_entity(type="agent", name="A", id="a")
        rel = g.create_relationship(type="related_to", source_id="a", target_id="a")
        validator = DataValidator(g)
        result = validator.validate_relationship(rel.id)
        assert result.valid is True

    def test_validate_relationship_not_found(self):
        g = _graph()
        validator = DataValidator(g)
        result = validator.validate_relationship("nonexistent")
        assert result.valid is False

    def test_validation_result_to_dict(self):
        vr = ValidationResult(valid=False, entity_count=5, errors=["err1"])
        d = vr.to_dict()
        assert d["valid"] is False
        assert d["errors"] == ["err1"]

    def test_health(self):
        g = _graph()
        validator = DataValidator(g)
        h = validator.health()
        assert h["alive"] is True
