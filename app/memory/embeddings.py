from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from numpy import ndarray


class EmbeddingProvider(ABC):
    """Abstract base for pluggable embedding providers."""

    dimension: int

    @abstractmethod
    def embed(self, text: str) -> ndarray:
        ...

    def embed_batch(self, texts: list[str]) -> list[ndarray]:
        return [self.embed(t) for t in texts]

    def compute_similarity(self, a: ndarray, b: ndarray) -> float:
        norm = np.linalg.norm(a) * np.linalg.norm(b)
        if norm == 0:
            return 0.0
        return float(np.dot(a, b) / norm)


class LocalEmbeddingProvider(EmbeddingProvider):
    """Deterministic hash-based embedding for local use."""

    def __init__(self, dimension: int = 128) -> None:
        self.dimension = dimension

    def embed(self, text: str) -> ndarray:
        h = hashlib.sha256(text.encode("utf-8")).digest()
        seed = int.from_bytes(h[:8], "big")
        rng = np.random.default_rng(seed)
        vec = rng.normal(0, 1, self.dimension)
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec /= norm
        return vec


class APIEmbeddingProvider(EmbeddingProvider):
    """Calls an external HTTP API for embeddings."""

    def __init__(
        self,
        api_url: str,
        dimension: int = 768,
        api_key: str | None = None,
        timeout: int = 30,
    ) -> None:
        self.api_url = api_url.rstrip("/")
        self.dimension = dimension
        self.api_key = api_key
        self.timeout = timeout

    def embed(self, text: str) -> ndarray:
        import requests

        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        resp = requests.post(
            f"{self.api_url}/embeddings",
            json={"input": text},
            headers=headers,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        vec = np.array(data.get("data", [{}])[0].get("embedding", []), dtype=np.float64)
        if len(vec) != self.dimension:
            raise ValueError(
                f"Expected dimension {self.dimension}, got {len(vec)}"
            )
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec /= norm
        return vec


_provider_cache: dict[str, EmbeddingProvider] = {}


def get_embedding_provider(
    provider_type: str = "local",
    dimension: int = 128,
    api_url: str | None = None,
    api_key: str | None = None,
) -> EmbeddingProvider:
    cache_key = f"{provider_type}:{dimension}"
    if cache_key in _provider_cache:
        return _provider_cache[cache_key]

    if provider_type == "local":
        provider: EmbeddingProvider = LocalEmbeddingProvider(dimension=dimension)
    elif provider_type == "api":
        provider = APIEmbeddingProvider(
            api_url=api_url or "http://localhost:8000",
            dimension=dimension,
            api_key=api_key,
        )
    else:
        raise ValueError(f"Unknown provider type: {provider_type}")
    _provider_cache[cache_key] = provider
    return provider


def clear_provider_cache() -> None:
    _provider_cache.clear()
