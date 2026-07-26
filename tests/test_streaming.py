from __future__ import annotations

from typing import Generator
from unittest.mock import MagicMock, patch

import pytest

from app.ai.manager import AIManager
from app.ai.providers.base import (
    AIResponse,
    AIStreamChunk,
    AIStreamResponse,
    AllProvidersFailedError,
    ProviderCapability,
    ProviderConnectionError,
    ProviderTimeoutError,
    _stream_sdk,
)
from app.ai.router import AIRouter
from app.ai.routing import RoutingConfig


# ---------------------------------------------------------------------------
# Streaming type tests
# ---------------------------------------------------------------------------


class TestAIStreamChunk:

    def test_default_chunk(self) -> None:
        chunk = AIStreamChunk()
        assert chunk.content == ""
        assert chunk.finish_reason is None
        assert chunk.usage is None

    def test_content_chunk(self) -> None:
        chunk = AIStreamChunk(content="hello")
        assert chunk.content == "hello"
        assert chunk.finish_reason is None

    def test_final_chunk(self) -> None:
        chunk = AIStreamChunk(
            content="",
            finish_reason="stop",
            usage={"total_tokens": 10},
        )
        assert chunk.finish_reason == "stop"
        assert chunk.usage == {"total_tokens": 10}


class TestAIStreamResponse:

    def _make_stream(self, chunks: list[str]) -> AIStreamResponse:
        def _gen() -> Generator[AIStreamChunk, None, None]:
            for c in chunks:
                yield AIStreamChunk(content=c)
        return AIStreamResponse("test", "test-model", _gen())

    def test_iteration_yields_chunks(self) -> None:
        stream = self._make_stream(["a", "b", "c"])
        results = [chunk.content for chunk in stream]
        assert results == ["a", "b", "c"]

    def test_final_response_assembles_text(self) -> None:
        stream = self._make_stream(["Hello, ", "world", "!"])
        for _ in stream:
            pass
        result = stream.final_response()
        assert isinstance(result, AIResponse)
        assert result == "Hello, world!"
        assert result.provider == "test"
        assert result.model == "test-model"
        assert result.latency_ms > 0

    def test_final_response_metadata(self) -> None:
        def _gen() -> Generator[AIStreamChunk, None, None]:
            yield AIStreamChunk(content="hello")
            yield AIStreamChunk(
                finish_reason="stop",
                usage={"total_tokens": 5},
            )
        stream = AIStreamResponse("p", "m", _gen())
        for _ in stream:
            pass
        result = stream.final_response()
        assert result == "hello"
        assert result.metadata["finish_reason"] == "stop"
        assert result.metadata["total_tokens"] == 5

    def test_cancel_stops_iteration(self) -> None:
        def _gen() -> Generator[AIStreamChunk, None, None]:
            yield AIStreamChunk(content="a")
            yield AIStreamChunk(content="b")
        stream = AIStreamResponse("p", "m", _gen())
        it = iter(stream)
        chunk1 = next(it)
        assert chunk1.content == "a"
        stream.cancel()
        with pytest.raises(StopIteration):
            next(it)

    def test_final_response_after_cancel(self) -> None:
        def _gen() -> Generator[AIStreamChunk, None, None]:
            yield AIStreamChunk(content="hello")
            yield AIStreamChunk(content=" world")
        stream = AIStreamResponse("p", "m", _gen())
        it = iter(stream)
        next(it)
        stream.cancel()
        result = stream.final_response()
        assert result == "hello"

    def test_empty_stream(self) -> None:
        def _gen() -> Generator[AIStreamChunk, None, None]:
            return
            yield  # pragma: no cover
        stream = AIStreamResponse("p", "m", _gen())
        results = list(stream)
        assert results == []
        result = stream.final_response()
        assert result == ""
        assert result.metadata == {}


# ---------------------------------------------------------------------------
# _stream_sdk helper
# ---------------------------------------------------------------------------


class TestStreamSDK:

    def test_yields_chunks(self) -> None:
        raw_chunks = ["a", "b", "c"]

        def sdk_call() -> list[str]:
            return raw_chunks

        def handler(raw: str) -> AIStreamChunk | None:
            return AIStreamChunk(content=raw)

        chunks = list(_stream_sdk(sdk_call, "test", handler))
        assert len(chunks) == 3
        assert [c.content for c in chunks] == ["a", "b", "c"]

    def test_skips_none_chunks(self) -> None:
        raw_chunks = ["a", "__skip__", "b"]

        def sdk_call() -> list[str]:
            return raw_chunks

        def handler(raw: str) -> AIStreamChunk | None:
            if raw == "__skip__":
                return None
            return AIStreamChunk(content=raw)

        chunks = list(_stream_sdk(sdk_call, "test", handler))
        assert [c.content for c in chunks] == ["a", "b"]

    def test_maps_exception_on_call(self) -> None:
        def sdk_call():
            raise Exception("timeout")

        def handler(raw):
            return AIStreamChunk(content=str(raw))

        with pytest.raises(ProviderTimeoutError):
            list(_stream_sdk(sdk_call, "test", handler))

    def test_maps_exception_during_iteration(self) -> None:
        class FailingStream:
            def __iter__(self):
                return self
            def __next__(self):
                raise Exception("connection refused")

        def sdk_call():
            return FailingStream()

        def handler(raw):
            return AIStreamChunk(content=str(raw))

        with pytest.raises(ProviderConnectionError):
            list(_stream_sdk(sdk_call, "test", handler))


# ---------------------------------------------------------------------------
# Provider streaming (mocked SDK)
# ---------------------------------------------------------------------------


class TestOpenAIStreaming:

    def _make_stream_chunks(
        self, texts: list[str], finish: str | None = None,
    ) -> list[MagicMock]:
        chunks = []
        for i, t in enumerate(texts):
            chunk = MagicMock()
            choice = MagicMock()
            choice.delta.content = t
            choice.delta.__bool__ = lambda self: True
            choice.finish_reason = None
            chunk.choices = [choice]
            chunk.usage = None
            chunks.append(chunk)
        if finish:
            last = MagicMock()
            choice = MagicMock()
            choice.delta.content = ""
            choice.delta.__bool__ = lambda self: True
            choice.finish_reason = finish
            last.choices = [choice]
            last.usage = MagicMock(
                prompt_tokens=10,
                completion_tokens=5,
                total_tokens=15,
            )
            chunks.append(last)
        return chunks

    def test_generate_stream_yields_chunks(self) -> None:
        mock_chunks = self._make_stream_chunks(["Hello", " world"])
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_chunks
        with patch("app.ai.providers.openai.OpenAI", return_value=mock_client):
            from app.ai.providers.openai import OpenAIProvider
            provider = OpenAIProvider(api_key="sk-test")
            stream = AIStreamResponse(
                provider.provider_name, provider._model,
                provider.generate_stream("hi"),
            )
            results = [c.content for c in stream]
            assert results == ["Hello", " world"]

    def test_final_response_with_usage(self) -> None:
        mock_chunks = self._make_stream_chunks(
            ["Hello"], finish="stop",
        )
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_chunks
        with patch("app.ai.providers.openai.OpenAI", return_value=mock_client):
            from app.ai.providers.openai import OpenAIProvider
            provider = OpenAIProvider(api_key="sk-test")
            stream = AIStreamResponse(
                provider.provider_name, provider._model,
                provider.generate_stream("hi"),
            )
            for _ in stream:
                pass
            result = stream.final_response()
            assert result == "Hello"
            assert result.provider == "openai"
            assert result.model == "gpt-4o-mini"
            assert result.metadata["finish_reason"] == "stop"
            assert result.metadata["total_tokens"] == 15

    def test_system_prompt_included(self) -> None:
        mock_chunks = self._make_stream_chunks(["ok"])
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_chunks
        with patch("app.ai.providers.openai.OpenAI", return_value=mock_client):
            from app.ai.providers.openai import OpenAIProvider
            provider = OpenAIProvider(api_key="sk-test", system_prompt="You are helpful.")
            stream = AIStreamResponse(
                provider.provider_name, provider._model,
                provider.generate_stream("hi"),
            )
            for _ in stream:
                pass
            msgs = mock_client.chat.completions.create.call_args.kwargs["messages"]
            assert {"role": "system", "content": "You are helpful."} in msgs

    def test_temperature_and_max_tokens_sent(self) -> None:
        mock_chunks = self._make_stream_chunks(["ok"])
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_chunks
        with patch("app.ai.providers.openai.OpenAI", return_value=mock_client):
            from app.ai.providers.openai import OpenAIProvider
            provider = OpenAIProvider(api_key="sk-test", temperature=0.5, max_tokens=100)
            stream = AIStreamResponse(
                provider.provider_name, provider._model,
                provider.generate_stream("hi"),
            )
            for _ in stream:
                pass
            kwargs = mock_client.chat.completions.create.call_args.kwargs
            assert kwargs["temperature"] == 0.5
            assert kwargs["max_tokens"] == 100
            assert kwargs["stream"] is True

    def test_stream_option_include_usage(self) -> None:
        mock_chunks = self._make_stream_chunks(["ok"])
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_chunks
        with patch("app.ai.providers.openai.OpenAI", return_value=mock_client):
            from app.ai.providers.openai import OpenAIProvider
            provider = OpenAIProvider(api_key="sk-test")
            stream = AIStreamResponse(
                provider.provider_name, provider._model,
                provider.generate_stream("hi"),
            )
            for _ in stream:
                pass
            kwargs = mock_client.chat.completions.create.call_args.kwargs
            assert kwargs.get("stream_options") == {"include_usage": True}


class TestDeepSeekStreaming:

    def _make_stream_chunks(
        self, texts: list[str], finish: str | None = None,
    ) -> list[MagicMock]:
        chunks = []
        for i, t in enumerate(texts):
            chunk = MagicMock()
            choice = MagicMock()
            choice.delta.content = t
            choice.delta.__bool__ = lambda self: True
            choice.finish_reason = None
            chunk.choices = [choice]
            chunk.usage = None
            chunks.append(chunk)
        if finish:
            last = MagicMock()
            choice = MagicMock()
            choice.delta.content = ""
            choice.delta.__bool__ = lambda self: True
            choice.finish_reason = finish
            last.choices = [choice]
            last.usage = MagicMock(
                prompt_tokens=8,
                completion_tokens=4,
                total_tokens=12,
            )
            chunks.append(last)
        return chunks

    def test_generate_stream_yields_chunks(self) -> None:
        mock_chunks = self._make_stream_chunks(["Hello", " DeepSeek"])
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_chunks
        with patch("app.ai.providers.deepseek.OpenAI", return_value=mock_client):
            from app.ai.providers.deepseek import DeepSeekProvider
            provider = DeepSeekProvider(api_key="sk-test")
            stream = AIStreamResponse(
                provider.provider_name, provider._model,
                provider.generate_stream("hi"),
            )
            results = [c.content for c in stream]
            assert results == ["Hello", " DeepSeek"]

    def test_final_response(self) -> None:
        mock_chunks = self._make_stream_chunks(["Hi"], finish="stop")
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_chunks
        with patch("app.ai.providers.deepseek.OpenAI", return_value=mock_client):
            from app.ai.providers.deepseek import DeepSeekProvider
            provider = DeepSeekProvider(api_key="sk-test")
            stream = AIStreamResponse(
                provider.provider_name, provider._model,
                provider.generate_stream("hi"),
            )
            for _ in stream:
                pass
            result = stream.final_response()
            assert result == "Hi"
            assert result.provider == "deepseek"


class TestAnthropicStreaming:

    def _make_stream_events(
        self, texts: list[str],
    ) -> list[MagicMock]:
        events = []
        for t in texts:
            ev = MagicMock()
            ev.type = "content_block_delta"
            ev.delta.text = t
            events.append(ev)
        last = MagicMock()
        last.type = "message_delta"
        last.delta.stop_reason = "end_turn"
        last.usage = MagicMock(input_tokens=5, output_tokens=3)
        events.append(last)
        return events

    def test_generate_stream_yields_chunks(self) -> None:
        mock_events = self._make_stream_events(["Hello", " Claude"])
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_events
        with patch("app.ai.providers.claude.Anthropic", return_value=mock_client):
            from app.ai.providers.claude import AnthropicProvider
            provider = AnthropicProvider(api_key="sk-test")
            stream = AIStreamResponse(
                provider.provider_name, provider._model,
                provider.generate_stream("hi"),
            )
            results = [c for c in stream]
            assert len(results) == 3
            assert [c.content for c in results if c.content] == ["Hello", " Claude"]
            last = results[-1]
            assert last.finish_reason == "end_turn"
            assert last.usage == {"input_tokens": 5, "output_tokens": 3}

    def test_final_response_with_metadata(self) -> None:
        mock_events = self._make_stream_events(["Hi"])
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_events
        with patch("app.ai.providers.claude.Anthropic", return_value=mock_client):
            from app.ai.providers.claude import AnthropicProvider
            provider = AnthropicProvider(api_key="sk-test")
            stream = AIStreamResponse(
                provider.provider_name, provider._model,
                provider.generate_stream("hi"),
            )
            for _ in stream:
                pass
            result = stream.final_response()
            assert result == "Hi"
            assert result.provider == "claude"
            assert result.metadata["finish_reason"] == "end_turn"
            assert result.metadata["input_tokens"] == 5
            assert result.metadata["output_tokens"] == 3

    def test_skip_non_delta_events(self) -> None:
        event1 = MagicMock()
        event1.type = "message_start"
        event1.message = MagicMock()
        event2 = MagicMock()
        event2.type = "content_block_delta"
        event2.delta.text = "hello"
        mock_client = MagicMock()
        mock_client.messages.create.return_value = [event1, event2]
        with patch("app.ai.providers.claude.Anthropic", return_value=mock_client):
            from app.ai.providers.claude import AnthropicProvider
            provider = AnthropicProvider(api_key="sk-test")
            stream = AIStreamResponse(
                provider.provider_name, provider._model,
                provider.generate_stream("hi"),
            )
            results = [c.content for c in stream]
            assert results == ["hello"]


class TestGeminiStreaming:

    def _make_stream_chunks(
        self, texts: list[str],
    ) -> list[MagicMock]:
        chunks = []
        for t in texts:
            chunk = MagicMock()
            chunk.text = t
            chunk.usage_metadata = None
            chunks.append(chunk)
        last = MagicMock()
        last.text = texts[-1] if texts else ""
        last.usage_metadata = MagicMock(
            prompt_token_count=3,
            candidates_token_count=2,
            total_token_count=5,
        )
        if chunks:
            chunks[-1] = last
        else:
            chunks = [last]
        return chunks

    def test_generate_stream_yields_chunks(self) -> None:
        mock_chunks = self._make_stream_chunks(["Hello", " Gemini"])
        mock_model = MagicMock()
        mock_model.generate_content.return_value = mock_chunks
        with patch("app.ai.providers.gemini.GenerativeModel", return_value=mock_model):
            from app.ai.providers.gemini import GeminiProvider
            provider = GeminiProvider(api_key="sk-test")
            stream = AIStreamResponse(
                provider.provider_name, provider._model,
                provider.generate_stream("hi"),
            )
            results = [c.content for c in stream]
            assert results == ["Hello", " Gemini"]

    def test_final_response(self) -> None:
        mock_chunks = self._make_stream_chunks(["Hi"])
        mock_model = MagicMock()
        mock_model.generate_content.return_value = mock_chunks
        with patch("app.ai.providers.gemini.GenerativeModel", return_value=mock_model):
            from app.ai.providers.gemini import GeminiProvider
            provider = GeminiProvider(api_key="sk-test")
            stream = AIStreamResponse(
                provider.provider_name, provider._model,
                provider.generate_stream("hi"),
            )
            for _ in stream:
                pass
            result = stream.final_response()
            assert result == "Hi"
            assert result.provider == "gemini"
            assert result.metadata["total_token_count"] == 5


# ---------------------------------------------------------------------------
# Router streaming
# ---------------------------------------------------------------------------


class _MockStreamProvider:
    """Mock provider with native streaming support for router tests."""

    def __init__(
        self,
        provider_name: str,
        chunks: list[str] | None = None,
        stream_error: type[Exception] | None = None,
        sync_result: str = "",
        sync_error: type[Exception] | None = None,
        available: bool = True,
    ) -> None:
        self.provider_name = provider_name
        self._chunks = chunks or ["a", "b"]
        self._stream_error = stream_error
        self._sync_result = sync_result
        self._sync_error = sync_error
        self._available = available
        self._model = "test-model"

    def generate(self, prompt: str) -> str:
        if self._sync_error:
            raise self._sync_error
        return self._sync_result or f"{self.provider_name}: {prompt}"

    def generate_stream(
        self, prompt: str,
    ) -> Generator[AIStreamChunk, None, None]:
        if self._stream_error:
            raise self._stream_error
        return (AIStreamChunk(content=c) for c in self._chunks)

    def check_availability(self) -> bool:
        return self._available


class _MockSyncProvider:
    """Mock provider WITHOUT native streaming (for sync fallback tests)."""

    def __init__(
        self,
        provider_name: str,
        sync_result: str | None = None,
        sync_error: type[Exception] | None = None,
        available: bool = True,
    ) -> None:
        self.provider_name = provider_name
        self._sync_result = sync_result or "sync result"
        self._sync_error = sync_error
        self._available = available
        self._model = "test-model"

    def generate(self, prompt: str) -> str:
        if self._sync_error:
            raise self._sync_error
        return self._sync_result

    def check_availability(self) -> bool:
        return self._available


def _make_router(
    providers: dict[str, _MockStreamProvider | _MockSyncProvider],
    config: RoutingConfig | None = None,
) -> AIRouter:
    router = AIRouter(routing_config=config)
    router.providers = providers  # type: ignore[assignment]
    return router


class TestRouterStreaming:

    def test_ask_stream_returns_ai_stream_response(self) -> None:
        p = _MockStreamProvider("test", chunks=["hello", " world"])
        router = _make_router({"test": p})
        stream = router.ask_stream("test", "hi")
        assert isinstance(stream, AIStreamResponse)
        results = [c.content for c in stream]
        assert results == ["hello", " world"]

    def test_ask_stream_unknown_provider_raises(self) -> None:
        router = _make_router({})
        with pytest.raises(ValueError, match="Unknown provider"):
            router.ask_stream("unknown", "hi")

    def test_ask_stream_sync_fallback_when_no_generate_stream(self) -> None:
        p = _MockSyncProvider("sync-only", sync_result="sync hello")
        router = _make_router({"sync-only": p})
        stream = router.ask_stream("sync-only", "hi")
        assert isinstance(stream, AIStreamResponse)
        results = [c.content for c in stream]
        assert results == ["sync hello"]
        result = stream.final_response()
        assert result == "sync hello"
        assert result.provider == "sync-only"

    def test_ask_stream_sync_fallback_uses_metadata(self) -> None:
        """Verify sync-fallback path passes metadata through."""
        p = _MockSyncProvider("sync-only", sync_result="data")
        router = _make_router({"sync-only": p})
        stream = router.ask_stream("sync-only", "hi")
        for _ in stream:
            pass
        result = stream.final_response()
        assert result == "data"

    def test_ask_routed_stream_follows_strategy(self) -> None:
        a = _MockStreamProvider("a", chunks=["from a"])
        b = _MockStreamProvider("b", chunks=["from b"])
        router = _make_router(
            {"a": a, "b": b},
            RoutingConfig(providers=("a", "b")),
        )
        stream = router.ask_routed_stream("hi")
        results = [c.content for c in stream]
        assert results == ["from a"]

    def test_ask_routed_stream_fallback_on_error(self) -> None:
        a = _MockStreamProvider(
            "a", stream_error=ProviderTimeoutError("a failed"),
        )
        b = _MockStreamProvider("b", chunks=["from b"])
        router = _make_router(
            {"a": a, "b": b},
            RoutingConfig(providers=("a", "b")),
        )
        stream = router.ask_routed_stream("hi")
        results = [c.content for c in stream]
        assert results == ["from b"]

    def test_ask_routed_stream_all_fail(self) -> None:
        a = _MockStreamProvider(
            "a", stream_error=ProviderTimeoutError("a failed"),
        )
        b = _MockStreamProvider(
            "b", stream_error=ProviderTimeoutError("b failed"),
        )
        router = _make_router(
            {"a": a, "b": b},
            RoutingConfig(providers=("a", "b")),
        )
        with pytest.raises(AllProvidersFailedError):
            router.ask_routed_stream("hi")

    def test_ask_routed_stream_skips_unavailable(self) -> None:
        a = _MockStreamProvider("a", available=False)
        b = _MockStreamProvider("b", chunks=["from b"])
        router = _make_router(
            {"a": a, "b": b},
            RoutingConfig(providers=("a", "b")),
        )
        stream = router.ask_routed_stream("hi")
        results = [c.content for c in stream]
        assert results == ["from b"]

    def test_ask_routed_stream_sync_fallback(self) -> None:
        """Provider without generate_stream uses sync fallback."""
        a = _MockSyncProvider("sync", sync_result="sync result")
        b = _MockStreamProvider("b", chunks=["from b"])
        router = _make_router(
            {"sync": a, "b": b},
            RoutingConfig(providers=("sync", "b")),
        )
        stream = router.ask_routed_stream("hi")
        results = [c.content for c in stream]
        assert results == ["sync result"]


# ---------------------------------------------------------------------------
# AIManager streaming
# ---------------------------------------------------------------------------


class TestAIManagerStreaming:

    def test_ask_stream_delegates_to_router(self) -> None:
        manager = AIManager()
        # Override providers with a controlled mock
        p = _MockStreamProvider("test", chunks=["hello"])
        manager.router.providers = {"test": p}  # type: ignore[assignment]
        stream = manager.ask_stream("test", "hi")
        results = [c.content for c in stream]
        assert results == ["hello"]


# ---------------------------------------------------------------------------
# Streaming capability detection
# ---------------------------------------------------------------------------


class TestStreamingCapability:

    def test_all_providers_have_streaming_flag(self) -> None:
        router = AIRouter()
        for name, provider in router.providers.items():
            caps = getattr(provider, "capabilities", frozenset())
            assert ProviderCapability.STREAMING in caps, (
                f"Provider {name!r} is missing STREAMING capability"
            )
