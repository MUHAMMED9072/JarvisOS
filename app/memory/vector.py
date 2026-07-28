from __future__ import annotations

import json
import math
import os
import tempfile
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

from .embeddings import EmbeddingProvider, get_embedding_provider

if TYPE_CHECKING:
    from numpy import ndarray


@dataclass
class VectorEntry:
    id: str
    vector: ndarray
    metadata: dict[str, Any] = field(default_factory=dict)
    content: str = ""
    created: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "vector": _encode_vector(self.vector),
            "metadata": self.metadata,
            "content": self.content,
            "created": self.created,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VectorEntry:
        return cls(
            id=data["id"],
            vector=_decode_vector(data["vector"]),
            metadata=data.get("metadata", {}),
            content=data.get("content", ""),
            created=data.get("created", ""),
        )


def _encode_vector(vec: ndarray) -> str:
    return base64_encode(vec.tobytes())


def _decode_vector(raw: str) -> ndarray:
    return np.frombuffer(base64_decode(raw), dtype=np.float64)


def base64_encode(data: bytes) -> str:
    import base64 as _b64
    return _b64.b64encode(data).decode("ascii")


def base64_decode(data: str) -> bytes:
    import base64 as _b64
    return _b64.b64decode(data)


class VectorStore:
    """NumPy-based vector storage with KNN search."""

    def __init__(
        self,
        filename: str = "vectors.json",
        embedding_provider: EmbeddingProvider | None = None,
        dimension: int = 128,
    ) -> None:
        self.path = Path("data") / "memory" / filename
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.dimension = dimension
        self._provider = embedding_provider
        self._entries: dict[str, VectorEntry] = {}
        self._dirty = False
        self._load()

    @property
    def provider(self) -> EmbeddingProvider:
        if self._provider is None:
            self._provider = get_embedding_provider(dimension=self.dimension)
        return self._provider

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for item in data.get("entries", []):
                entry = VectorEntry.from_dict(item)
                self._entries[entry.id] = entry
        except Exception:
            self._entries = {}

    def save(self) -> None:
        data = {
            "dimension": self.dimension,
            "entries": [e.to_dict() for e in self._entries.values()],
        }
        fd, tmp = tempfile.mkstemp(
            dir=str(self.path.parent), prefix=".tmp_", suffix=".json"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(tmp, str(self.path))
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        self._dirty = False

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def add(
        self,
        content: str,
        metadata: dict[str, Any] | None = None,
        vector: ndarray | None = None,
        entry_id: str | None = None,
    ) -> VectorEntry:
        if vector is None:
            vector = self.provider.embed(content)
        entry = VectorEntry(
            id=entry_id or uuid.uuid4().hex,
            vector=vector,
            metadata=metadata or {},
            content=content,
        )
        self._entries[entry.id] = entry
        self._dirty = True
        return entry

    def delete(self, entry_id: str) -> bool:
        if entry_id in self._entries:
            del self._entries[entry_id]
            self._dirty = True
            return True
        return False

    def get(self, entry_id: str) -> VectorEntry | None:
        return self._entries.get(entry_id)

    def update(
        self,
        entry_id: str,
        content: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> VectorEntry | None:
        entry = self._entries.get(entry_id)
        if entry is None:
            return None
        if content is not None:
            entry.content = content
            entry.vector = self.provider.embed(content)
        if metadata is not None:
            entry.metadata.update(metadata)
        entry.created = datetime.now(timezone.utc).isoformat()
        self._dirty = True
        return entry

    def count(self) -> int:
        return len(self._entries)

    def clear(self) -> None:
        self._entries.clear()
        self._dirty = True

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def knn_search(
        self,
        query: ndarray | str,
        k: int = 10,
        min_score: float = 0.0,
    ) -> list[tuple[VectorEntry, float]]:
        if isinstance(query, str):
            query_vec = self.provider.embed(query)
        else:
            query_vec = query

        if not self._entries:
            return []

        vectors = np.array([e.vector for e in self._entries.values()])
        query_norm = np.linalg.norm(query_vec)
        if query_norm == 0:
            return []
        query_normalized = query_vec / query_norm

        norms = np.linalg.norm(vectors, axis=1)
        norms[norms == 0] = 1
        normalized = vectors / norms[:, np.newaxis]

        similarities = np.dot(normalized, query_normalized)

        top_k = min(k, len(similarities))
        indices = np.argpartition(similarities, -top_k)[-top_k:]
        indices = indices[np.argsort(-similarities[indices])]

        entries_list = list(self._entries.values())
        results: list[tuple[VectorEntry, float]] = []
        for idx in indices:
            score = float(similarities[idx])
            if score < min_score:
                continue
            results.append((entries_list[idx], score))
        return results

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def prune(self, ttl_days: int = 30, max_entries: int = 10000) -> int:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=ttl_days)).isoformat()
        to_remove = [
            eid
            for eid, entry in self._entries.items()
            if entry.created < cutoff
        ]
        # If still over limit, remove oldest beyond max_entries
        remaining_count = len(self._entries) - len(to_remove)
        if remaining_count > max_entries:
            sorted_entries = sorted(
                [e for e in self._entries.values() if e.id not in to_remove],
                key=lambda e: e.created,
            )
            extra = sorted_entries[: remaining_count - max_entries]
            to_remove.extend(e.id for e in extra)

        for eid in to_remove:
            del self._entries[eid]

        if to_remove:
            self._dirty = True
        return len(to_remove)
