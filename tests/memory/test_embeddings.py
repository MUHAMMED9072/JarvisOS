from __future__ import annotations

import numpy as np
import pytest

from app.memory.embeddings import (
    APIEmbeddingProvider,
    EmbeddingProvider,
    LocalEmbeddingProvider,
    clear_provider_cache,
    get_embedding_provider,
)


class TestEmbeddingProvider:
    def test_abstract_cannot_instantiate(self):
        with pytest.raises(TypeError):
            EmbeddingProvider()  # type: ignore[abstract]

    def test_compute_similarity_identical(self):
        provider = LocalEmbeddingProvider(dimension=4)
        vec = np.array([1.0, 0.0, 0.0, 0.0])
        assert provider.compute_similarity(vec, vec) == pytest.approx(1.0)

    def test_compute_similarity_orthogonal(self):
        provider = LocalEmbeddingProvider(dimension=4)
        a = np.array([1.0, 0.0, 0.0, 0.0])
        b = np.array([0.0, 1.0, 0.0, 0.0])
        assert provider.compute_similarity(a, b) == pytest.approx(0.0)

    def test_compute_similarity_zero_norm(self):
        provider = LocalEmbeddingProvider(dimension=4)
        zero = np.zeros(4)
        assert provider.compute_similarity(zero, zero) == 0.0


class TestLocalEmbeddingProvider:
    def test_embed_returns_correct_dimension(self):
        provider = LocalEmbeddingProvider(dimension=128)
        vec = provider.embed("hello world")
        assert len(vec) == 128

    def test_embed_is_deterministic(self):
        provider = LocalEmbeddingProvider(dimension=64)
        v1 = provider.embed("same text")
        v2 = provider.embed("same text")
        assert np.allclose(v1, v2)

    def test_embed_different_texts_different(self):
        provider = LocalEmbeddingProvider(dimension=64)
        v1 = provider.embed("hello")
        v2 = provider.embed("world")
        assert not np.allclose(v1, v2)

    def test_embed_returns_unit_vector(self):
        provider = LocalEmbeddingProvider(dimension=128)
        vec = provider.embed("test")
        norm = np.linalg.norm(vec)
        assert norm == pytest.approx(1.0, rel=1e-6)

    def test_embed_batch(self):
        provider = LocalEmbeddingProvider(dimension=32)
        texts = ["a", "b", "c"]
        vectors = provider.embed_batch(texts)
        assert len(vectors) == 3
        assert all(len(v) == 32 for v in vectors)


class _MockResponse:
    def __init__(self, status_code=200, json_data=None):
        self.status_code = status_code
        self._json_data = json_data or {}
        self.headers = {}

    def json(self):
        return self._json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")


class TestAPIEmbeddingProvider:
    def test_raises_on_bad_response(self, monkeypatch):
        def mock_post(*args, **kwargs):
            return _MockResponse(status_code=500)
        monkeypatch.setattr("requests.post", mock_post)
        provider = APIEmbeddingProvider(api_url="http://fake.local", dimension=4)
        with pytest.raises(Exception):
            provider.embed("hello")

    def test_raises_on_wrong_dimension(self, monkeypatch):
        def mock_post(*args, **kwargs):
            return _MockResponse(json_data={"data": [{"embedding": [0.1, 0.2, 0.3]}]})
        monkeypatch.setattr("requests.post", mock_post)
        provider = APIEmbeddingProvider(api_url="http://fake.local", dimension=4)
        with pytest.raises(ValueError, match="Expected dimension 4, got 3"):
            provider.embed("hello")

    def test_successful_embed(self, monkeypatch):
        def mock_post(*args, **kwargs):
            return _MockResponse(json_data={"data": [{"embedding": [1.0, 0.0]}]})
        monkeypatch.setattr("requests.post", mock_post)
        provider = APIEmbeddingProvider(api_url="http://fake.local", dimension=2)
        vec = provider.embed("hello")
        assert len(vec) == 2

    def test_sends_api_key(self, monkeypatch):
        captured_headers = {}
        def mock_post(*args, **kwargs):
            captured_headers.update(kwargs.get("headers", {}))
            return _MockResponse(json_data={"data": [{"embedding": [1.0, 0.0]}]})
        monkeypatch.setattr("requests.post", mock_post)
        provider = APIEmbeddingProvider(
            api_url="http://fake.local", dimension=2, api_key="sk-test"
        )
        provider.embed("hello")
        assert captured_headers.get("Authorization") == "Bearer sk-test"


class TestGetEmbeddingProvider:
    def test_default_is_local(self):
        clear_provider_cache()
        provider = get_embedding_provider()
        assert isinstance(provider, LocalEmbeddingProvider)

    def test_local_type(self):
        clear_provider_cache()
        provider = get_embedding_provider(provider_type="local")
        assert isinstance(provider, LocalEmbeddingProvider)

    def test_unknown_type(self):
        clear_provider_cache()
        with pytest.raises(ValueError, match="Unknown provider type"):
            get_embedding_provider(provider_type="unknown")
