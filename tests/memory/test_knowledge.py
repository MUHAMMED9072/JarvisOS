from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from app.memory.knowledge import Fact, KnowledgeBase

_DATA_DIR = Path("data") / "memory"


@pytest.fixture
def kb():
    name = f"test_kb_{uuid.uuid4().hex}.json"
    k = KnowledgeBase(filename=name)
    yield k
    path = _DATA_DIR / name
    if path.exists():
        path.unlink()


class TestFact:
    def test_to_dict_from_dict_roundtrip(self):
        fact = Fact(
            id="test-id",
            subject="Jarvis",
            predicate="is",
            obj="an AI",
            confidence=0.95,
            source="test",
            metadata={"version": 1},
        )
        d = fact.to_dict()
        restored = Fact.from_dict(d)
        assert restored.id == "test-id"
        assert restored.subject == "Jarvis"
        assert restored.predicate == "is"
        assert restored.obj == "an AI"
        assert restored.confidence == 0.95
        assert restored.source == "test"
        assert restored.metadata == {"version": 1}

    def test_defaults(self):
        fact = Fact(id="1", subject="s", predicate="p", obj="o")
        assert fact.confidence == 1.0
        assert fact.source == ""
        assert fact.metadata == {}


class TestKnowledgeBase:
    def test_add_fact_returns_fact(self, kb):
        fact = kb.add_fact("Earth", "orbits", "Sun")
        assert fact.subject == "Earth"
        assert fact.predicate == "orbits"
        assert fact.obj == "Sun"

    def test_get_fact_existing(self, kb):
        fact = kb.add_fact("Earth", "orbits", "Sun")
        retrieved = kb.get_fact(fact.id)
        assert retrieved is not None
        assert retrieved.subject == "Earth"

    def test_get_fact_missing(self, kb):
        assert kb.get_fact("nonexistent") is None

    def test_query_by_subject(self, kb):
        kb.add_fact("Earth", "orbits", "Sun")
        kb.add_fact("Mars", "orbits", "Sun")
        kb.add_fact("Earth", "has", "Moon")
        results = kb.query(subject="Earth")
        assert len(results) == 2

    def test_query_by_predicate(self, kb):
        kb.add_fact("Earth", "orbits", "Sun")
        kb.add_fact("Mars", "orbits", "Sun")
        results = kb.query(predicate="orbits")
        assert len(results) == 2

    def test_query_by_object(self, kb):
        kb.add_fact("Earth", "orbits", "Sun")
        kb.add_fact("Mars", "orbits", "Sun")
        results = kb.query(obj="Sun")
        assert len(results) == 2

    def test_query_combined(self, kb):
        kb.add_fact("Earth", "orbits", "Sun")
        kb.add_fact("Mars", "orbits", "Sun")
        results = kb.query(subject="Earth", predicate="orbits")
        assert len(results) == 1

    def test_delete_fact(self, kb):
        fact = kb.add_fact("test", "is", "test")
        assert kb.delete_fact(fact.id) is True
        assert kb.get_fact(fact.id) is None

    def test_delete_fact_missing(self, kb):
        assert kb.delete_fact("nonexistent") is False

    def test_update_fact(self, kb):
        fact = kb.add_fact("test", "is", "test")
        updated = kb.update_fact(fact.id, confidence=0.5)
        assert updated is not None
        assert updated.confidence == 0.5

    def test_update_fact_missing(self, kb):
        assert kb.update_fact("nonexistent", confidence=0.5) is None

    def test_count(self, kb):
        kb.add_fact("a", "is", "a")
        kb.add_fact("b", "is", "b")
        assert kb.count() == 2

    def test_clear(self, kb):
        kb.add_fact("a", "is", "a")
        kb.clear()
        assert kb.count() == 0

    def test_search(self, kb):
        kb.add_fact("Python", "is", "language")
        kb.add_fact("Java", "is", "language")
        results = kb.search("python")
        assert len(results) == 1
        assert results[0].subject == "Python"

    def test_persistence(self, kb):
        kb.add_fact("persist", "test", "value")
        kb2 = KnowledgeBase(filename=kb.path.name)
        assert kb2.count() == 1

    def test_add_fact_with_metadata(self, kb):
        fact = kb.add_fact("test", "is", "test", confidence=0.8, source="unit_test", metadata={"key": "val"})
        assert fact.confidence == 0.8
        assert fact.source == "unit_test"
        assert fact.metadata == {"key": "val"}
