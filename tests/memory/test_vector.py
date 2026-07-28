from __future__ import annotations

import uuid
from pathlib import Path

import numpy as np
import pytest

from app.memory.embeddings import LocalEmbeddingProvider
from app.memory.vector import VectorEntry, VectorStore, _decode_vector, _encode_vector

_DATA_DIR = Path("data") / "memory"


@pytest.fixture
def store():
    name = f"test_vectors_{uuid.uuid4().hex}.json"
    s = VectorStore(filename=name, dimension=8)
    s._entries.clear()
    yield s
    path = _DATA_DIR / name
    if path.exists():
        path.unlink()


@pytest.fixture
def populated_store(store):
    for text in ["apple fruit", "banana fruit", "carrot vegetable", "dog animal"]:
        store.add(content=text)
    return store


class TestVectorEntry:
    def test_to_dict_from_dict_roundtrip(self):
        entry = VectorEntry(
            id="test-id",
            vector=np.array([1.0, 2.0, 3.0]),
            metadata={"key": "val"},
            content="hello",
        )
        d = entry.to_dict()
        restored = VectorEntry.from_dict(d)
        assert restored.id == "test-id"
        assert np.allclose(restored.vector, [1.0, 2.0, 3.0])
        assert restored.metadata == {"key": "val"}
        assert restored.content == "hello"

    def test_encode_decode_roundtrip(self):
        vec = np.array([0.5, -1.0, 3.14], dtype=np.float64)
        encoded = _encode_vector(vec)
        decoded = _decode_vector(encoded)
        assert np.allclose(vec, decoded)


class TestVectorStore:
    def test_add_returns_entry(self, store):
        entry = store.add(content="test", metadata={"source": "user"})
        assert entry.content == "test"
        assert entry.metadata == {"source": "user"}
        assert entry.id is not None

    def test_add_generates_id(self, store):
        entry = store.add(content="test")
        assert len(entry.id) > 0

    def test_add_with_custom_id(self, store):
        entry = store.add(content="test", entry_id="my-id")
        assert entry.id == "my-id"

    def test_get_existing(self, store):
        entry = store.add(content="hello")
        assert store.get(entry.id) is entry

    def test_get_missing(self, store):
        assert store.get("nonexistent") is None

    def test_delete_existing(self, store):
        entry = store.add(content="hello")
        assert store.delete(entry.id) is True
        assert store.get(entry.id) is None

    def test_delete_missing(self, store):
        assert store.delete("nonexistent") is False

    def test_update_content(self, store):
        entry = store.add(content="old")
        updated = store.update(entry.id, content="new")
        assert updated is not None
        assert updated.content == "new"

    def test_update_metadata(self, store):
        entry = store.add(content="test")
        updated = store.update(entry.id, metadata={"key": "val"})
        assert updated is not None
        assert updated.metadata == {"key": "val"}

    def test_update_nonexistent(self, store):
        assert store.update("nonexistent", content="new") is None

    def test_count(self, populated_store):
        assert populated_store.count() == 4

    def test_clear(self, populated_store):
        populated_store.clear()
        assert populated_store.count() == 0

    def test_knn_search_returns_results(self, populated_store):
        results = populated_store.knn_search("fruit", k=2)
        assert len(results) == 2

    def test_knn_search_returns_entries_and_scores(self, populated_store):
        results = populated_store.knn_search("fruit", k=2)
        for entry, score in results:
            assert isinstance(entry, VectorEntry)
            assert 0.0 <= score <= 1.0

    def test_knn_search_respects_k(self, populated_store):
        results = populated_store.knn_search("fruit", k=1)
        assert len(results) == 1

    def test_knn_search_empty_store(self, store):
        results = store.knn_search("test", k=5)
        assert results == []

    def test_knn_search_with_min_score(self, populated_store):
        results = populated_store.knn_search("fruit", k=10, min_score=0.5)
        for _, score in results:
            assert score >= 0.5

    def test_knn_search_with_string_query(self, populated_store):
        results = populated_store.knn_search("fruit", k=2)
        assert len(results) == 2

    def test_prune_removes_old_entries(self, store):
        import json
        from datetime import datetime, timedelta, timezone

        # Manually create an old entry
        old_id = uuid.uuid4().hex
        store._entries[old_id] = VectorEntry(
            id=old_id,
            vector=np.zeros(8),
            content="old",
            created=(datetime.now(timezone.utc) - timedelta(days=100)).isoformat(),
        )
        store.add(content="new")
        removed = store.prune(ttl_days=50)
        assert removed == 1
        assert store.get(old_id) is None

    def test_prune_respects_max_entries(self, store):
        for i in range(20):
            store.add(content=f"item{i}")
        removed = store.prune(ttl_days=365, max_entries=10)
        assert removed == 10
        assert store.count() <= 10

    def test_save_and_load_persistence(self, store):
        store.add(content="persist test")
        store.save()

        store2 = VectorStore(filename=store.path.name, dimension=8)
        assert store2.count() == 1
        entries = list(store2._entries.values())
        assert entries[0].content == "persist test"

        # cleanup
        path = _DATA_DIR / store.path.name
        if path.exists():
            path.unlink()
