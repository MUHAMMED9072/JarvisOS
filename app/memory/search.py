from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .history import MemoryHistory
from .vector import VectorEntry, VectorStore

if TYPE_CHECKING:
    from numpy import ndarray


@dataclass
class SearchResult:
    content: str
    score: float
    source: str  # "keyword", "vector", or "hybrid"
    metadata: dict[str, Any] = field(default_factory=dict)
    entry_id: str = ""


class HybridSearch:
    """Combines keyword (history) and vector (semantic) search with configurable weights."""

    def __init__(
        self,
        vector_store: VectorStore,
        history: MemoryHistory,
        keyword_weight: float = 0.3,
        vector_weight: float = 0.7,
        top_k: int = 10,
    ) -> None:
        self.vector_store = vector_store
        self.history = history
        self.keyword_weight = keyword_weight
        self.vector_weight = vector_weight
        self.top_k = top_k

    def search(
        self,
        query: str,
        top_k: int | None = None,
        keyword_weight: float | None = None,
        vector_weight: float | None = None,
        min_score: float = 0.0,
    ) -> list[SearchResult]:
        kw_weight = keyword_weight if keyword_weight is not None else self.keyword_weight
        vec_weight = vector_weight if vector_weight is not None else self.vector_weight
        k = top_k if top_k is not None else self.top_k

        # Keyword results from history
        keyword_results: list[SearchResult] = []
        q = query.lower()
        for item in reversed(self.history.get_all()):
            content = item.get("content", "")
            if q in content.lower():
                keyword_results.append(
                    SearchResult(
                        content=content,
                        score=1.0,
                        source="keyword",
                        metadata=item.get("metadata", {}),
                    )
                )

        # Vector results
        vec_results = self.vector_store.knn_search(query, k=k, min_score=min_score)

        # Merge with weighted score
        merged: dict[str, SearchResult] = {}
        for sr in keyword_results:
            key = sr.content
            merged[key] = SearchResult(
                content=sr.content,
                score=sr.score * kw_weight,
                source="hybrid",
                metadata=sr.metadata,
            )

        for entry, score in vec_results:
            key = entry.content
            if key in merged:
                merged[key].score += score * vec_weight
                merged[key].score = min(merged[key].score, 1.0)
                if score > merged[key].score / max(vec_weight, 0.01):
                    merged[key].metadata = entry.metadata
            else:
                merged[key] = SearchResult(
                    content=entry.content,
                    score=score * vec_weight,
                    source="hybrid",
                    metadata=entry.metadata,
                    entry_id=entry.id,
                )

        sorted_results = sorted(merged.values(), key=lambda r: r.score, reverse=True)
        return sorted_results[:k]

    def semantic_search(
        self,
        query: str,
        top_k: int = 10,
        min_score: float = 0.0,
    ) -> list[SearchResult]:
        results = self.vector_store.knn_search(query, k=top_k, min_score=min_score)
        return [
            SearchResult(
                content=entry.content,
                score=score,
                source="vector",
                metadata=entry.metadata,
                entry_id=entry.id,
            )
            for entry, score in results
        ]
