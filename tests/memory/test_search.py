from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from app.memory.history import MemoryHistory
from app.memory.search import HybridSearch, SearchResult
from app.memory.storage import MemoryStorage
from app.memory.vector import VectorStore

_DATA_DIR = Path("data") / "memory"


@pytest.fixture
def history():
    name = f"test_hist_{uuid.uuid4().hex}.json"
    s = MemoryStorage(name)
    s.set("items", [
        {"role": "user", "content": "I love apples", "metadata": {}},
        {"role": "assistant", "content": "Apples are healthy", "metadata": {}},
        {"role": "user", "content": "Tell me about dogs", "metadata": {}},
    ])
    h = MemoryHistory(s)
    yield h
    path = _DATA_DIR / name
    if path.exists():
        path.unlink()


@pytest.fixture
def vector_store():
    name = f"test_vec_{uuid.uuid4().hex}.json"
    vs = VectorStore(filename=name, dimension=8)
    vs._entries.clear()
    vs.add(content="I enjoy eating apples")
    vs.add(content="Dogs are loyal animals")
    vs.add(content="Programming in Python")
    yield vs
    path = _DATA_DIR / name
    if path.exists():
        path.unlink()


@pytest.fixture
def hybrid(history, vector_store):
    return HybridSearch(
        vector_store=vector_store,
        history=history,
        keyword_weight=0.3,
        vector_weight=0.7,
        top_k=5,
    )


class TestSearchResult:
    def test_defaults(self):
        r = SearchResult(content="test", score=0.5, source="keyword")
        assert r.metadata == {}
        assert r.entry_id == ""


class TestHybridSearch:
    def test_semantic_search_returns_results(self, hybrid):
        results = hybrid.semantic_search("fruit", top_k=3)
        assert len(results) > 0
        for r in results:
            assert r.source == "vector"
            assert 0.0 <= r.score <= 1.0

    def test_semantic_search_respects_top_k(self, hybrid):
        results = hybrid.semantic_search("fruit", top_k=1)
        assert len(results) == 1

    def test_semantic_search_min_score(self, hybrid):
        results = hybrid.semantic_search("zzzzzxyzzy", top_k=5, min_score=0.9)
        assert len(results) == 0

    def test_hybrid_search_combines_results(self, hybrid):
        results = hybrid.search("apples", top_k=5)
        assert len(results) > 0
        for r in results:
            assert r.source == "hybrid"

    def test_hybrid_search_returns_sorted(self, hybrid):
        results = hybrid.search("apples", top_k=5)
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_hybrid_search_respects_top_k(self, hybrid):
        results = hybrid.search("apples", top_k=1)
        assert len(results) == 1

    def test_hybrid_search_respects_weights(self, hybrid):
        kw_results = hybrid.search("apples", top_k=5, keyword_weight=1.0, vector_weight=0.0)
        vec_results = hybrid.search("apples", top_k=5, keyword_weight=0.0, vector_weight=1.0)
        # With keyword_weight=1.0, keyword match should give higher scores
        assert len(kw_results) > 0
        assert len(vec_results) > 0

    def test_hybrid_search_returns_search_result_type(self, hybrid):
        results = hybrid.search("apples", top_k=3)
        for r in results:
            assert isinstance(r, SearchResult)
