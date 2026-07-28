from __future__ import annotations

import pytest

from app.knowledge_graph.entity import Entity


class TestEntity:
    def test_default_type_is_concept(self):
        e = Entity()
        assert e.type == "concept"

    def test_default_name_is_empty(self):
        e = Entity()
        assert e.name == ""

    def test_to_dict_roundtrip(self):
        e = Entity(type="agent", name="test-agent", properties={"key": "val"})
        d = e.to_dict()
        restored = Entity.from_dict(d)
        assert restored.id == e.id
        assert restored.type == "agent"
        assert restored.name == "test-agent"
        assert restored.properties == {"key": "val"}

    def test_create_valid_entity(self):
        e = Entity.create(type="agent", name="my-agent", properties={"name": "my-agent"})
        assert e.type == "agent"
        assert e.name == "my-agent"

    def test_create_invalid_type_raises(self):
        with pytest.raises(ValueError, match="Invalid entity type"):
            Entity.create(type="nonexistent", name="test")

    def test_create_validates_required_fields(self):
        with pytest.raises(ValueError, match="validation failed"):
            # task type requires "status" field which we omit
            Entity.create(type="task", name="test", properties={"name": "test"})

    def test_create_concept_accepts_anything(self):
        e = Entity.create(type="concept", name="anything", properties={"foo": "bar"})
        assert e.name == "anything"
        assert e.properties == {"foo": "bar"}

    def test_create_with_custom_id(self):
        e = Entity.create(type="concept", name="test", id="my-custom-id")
        assert e.id == "my-custom-id"

    def test_unique_ids(self):
        e1 = Entity.create(type="concept", name="a")
        e2 = Entity.create(type="concept", name="b")
        assert e1.id != e2.id
