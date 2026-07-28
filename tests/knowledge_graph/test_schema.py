from __future__ import annotations

import pytest

from app.knowledge_graph.schema import (
    ENTITY_TYPES,
    RELATIONSHIP_TYPES,
    EntityType,
    EntityTypeRegistry,
    RelationshipType,
    RelationshipTypeRegistry,
)


class TestEntityType:
    def test_frozen(self):
        et = EntityType("test", fields={"name": str})
        with pytest.raises(Exception):
            et.name = "changed"  # type: ignore[misc]

    def test_validate_passes(self):
        et = EntityType("test", fields={"name": str})
        assert et.validate({"name": "hello"}) == []

    def test_validate_missing_field(self):
        et = EntityType("test", fields={"name": str, "status": str})
        errors = et.validate({"name": "hello"})
        assert len(errors) == 1
        assert "Missing required field 'status'" in errors[0]

    def test_validate_wrong_type(self):
        et = EntityType("test", fields={"count": int})
        errors = et.validate({"count": "not_int"})
        assert len(errors) == 1
        assert "expected int, got str" in errors[0]

    def test_validate_empty_fields(self):
        et = EntityType("test")
        assert et.validate({"anything": 123}) == []


class TestEntityTypeRegistry:
    def test_register_and_get(self):
        reg = EntityTypeRegistry()
        et = EntityType("custom")
        reg.register(et)
        assert reg.get("custom") is et

    def test_get_missing(self):
        reg = EntityTypeRegistry()
        assert reg.get("missing") is None

    def test_is_valid(self):
        reg = EntityTypeRegistry()
        reg.register(EntityType("valid"))
        assert reg.is_valid("valid") is True
        assert reg.is_valid("invalid") is False

    def test_list_types(self):
        reg = EntityTypeRegistry()
        reg.register(EntityType("a"))
        reg.register(EntityType("b"))
        assert len(reg.list_types()) == 2

    def test_validate_properties(self):
        reg = EntityTypeRegistry()
        reg.register(EntityType("test", fields={"x": int}))
        assert len(reg.validate_properties("test", {"x": 1})) == 0

    def test_validate_properties_unknown_type(self):
        reg = EntityTypeRegistry()
        errors = reg.validate_properties("unknown", {})
        assert "Unknown entity type" in errors[0]

    def test_clear(self):
        reg = EntityTypeRegistry()
        reg.register(EntityType("a"))
        reg.clear()
        assert reg.list_types() == []


class TestBuiltinEntityTypes:
    def test_agent_type_exists(self):
        assert ENTITY_TYPES.is_valid("agent")

    def test_tool_type_exists(self):
        assert ENTITY_TYPES.is_valid("tool")

    def test_invalid_type_fails(self):
        assert not ENTITY_TYPES.is_valid("nonexistent")

    def test_agent_requires_name(self):
        errors = ENTITY_TYPES.validate_properties("agent", {})
        assert any("Missing required field 'name'" in e for e in errors)

    def test_agent_accepts_valid_properties(self):
        assert ENTITY_TYPES.validate_properties("agent", {"name": "test"}) == []


class TestRelationshipType:
    def test_validate_source_no_constraints(self):
        rt = RelationshipType("test")
        assert rt.validate_source("anything") is True

    def test_validate_source_with_constraint(self):
        rt = RelationshipType("test", source_types=["agent"])
        assert rt.validate_source("agent") is True
        assert rt.validate_source("tool") is False

    def test_validate_target_with_constraint(self):
        rt = RelationshipType("test", target_types=["tool"])
        assert rt.validate_target("tool") is True
        assert rt.validate_target("agent") is False


class TestRelationshipTypeRegistry:
    def test_register_and_get(self):
        reg = RelationshipTypeRegistry()
        rt = RelationshipType("custom")
        reg.register(rt)
        assert reg.get("custom") is rt

    def test_get_missing(self):
        reg = RelationshipTypeRegistry()
        assert reg.get("missing") is None

    def test_is_valid(self):
        reg = RelationshipTypeRegistry()
        reg.register(RelationshipType("valid"))
        assert reg.is_valid("valid") is True

    def test_clear(self):
        reg = RelationshipTypeRegistry()
        reg.register(RelationshipType("a"))
        reg.clear()
        assert reg.list_types() == []


class TestBuiltinRelationshipTypes:
    def test_depends_on_exists(self):
        assert RELATIONSHIP_TYPES.is_valid("depends_on")

    def test_contains_exists(self):
        assert RELATIONSHIP_TYPES.is_valid("contains")

    def test_related_to_exists(self):
        assert RELATIONSHIP_TYPES.is_valid("related_to")

    def test_invalid_type_fails(self):
        assert not RELATIONSHIP_TYPES.is_valid("nonexistent")
