from __future__ import annotations

import pytest

from app.knowledge_graph.relationship import Relationship


class TestRelationship:
    def test_default_type_is_related_to(self):
        r = Relationship()
        assert r.type == "related_to"

    def test_to_dict_roundtrip(self):
        r = Relationship(
            type="depends_on",
            source_id="src-1",
            target_id="tgt-1",
            properties={"weight": 1.0},
        )
        d = r.to_dict()
        restored = Relationship.from_dict(d)
        assert restored.id == r.id
        assert restored.type == "depends_on"
        assert restored.source_id == "src-1"
        assert restored.target_id == "tgt-1"
        assert restored.properties == {"weight": 1.0}

    def test_create_valid_relationship(self):
        r = Relationship.create(
            type="depends_on", source_id="src-1", target_id="tgt-1"
        )
        assert r.type == "depends_on"
        assert r.source_id == "src-1"
        assert r.target_id == "tgt-1"

    def test_create_invalid_type_raises(self):
        with pytest.raises(ValueError, match="Unknown relationship type"):
            Relationship.create(type="nonexistent", source_id="a", target_id="b")

    def test_create_with_custom_id(self):
        r = Relationship.create(
            type="related_to", source_id="a", target_id="b", id="my-rel"
        )
        assert r.id == "my-rel"

    def test_reversed_swaps_source_and_target(self):
        r = Relationship(type="depends_on", source_id="a", target_id="b", properties={"x": 1})
        rev = r.reversed()
        assert rev.source_id == "b"
        assert rev.target_id == "a"
        assert rev.type == "depends_on"
        assert rev.properties == {"x": 1}

    def test_unique_ids(self):
        r1 = Relationship.create(type="related_to", source_id="a", target_id="b")
        r2 = Relationship.create(type="related_to", source_id="a", target_id="b")
        assert r1.id != r2.id
