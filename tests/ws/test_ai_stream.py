"""Tests for the Live AI Streaming over WebSockets (P12-03)."""

from __future__ import annotations

import asyncio
import json
from typing import Any, Generator
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import WebSocket

from app.ai.providers.base import AIResponse, AIStreamChunk, AIStreamResponse
from app.ai.manager import AIManager
from app.ws.ai_stream import AIStreamManager
from app.ws.manager import WebSocketConnectionManager
from app.ws.schemas import ServerMessage, WSMessageType


# ==========================================================================
# Helpers
# ==========================================================================


class _ChunkStream(AIStreamResponse):
    """A controllable stream for testing."""

    def __init__(
        self,
        chunks: list[str] | None = None,
        final_text: str = "Complete!",
        provider: str = "test_provider",
        model: str = "test-model",
        latency: float = 5.0,
        fail_on_iter: bool = False,
    ):
        super().__init__(provider, model, (c for c in []))
        self._chunks = chunks or ["Hello", " world"]
        self._final_text = final_text
        self._provider = provider
        self._model = model
        self._latency = latency
        self._fail_on_iter = fail_on_iter
        self._cancel_called = False
        self._cancelled = False

    def __iter__(self) -> AIStreamResponse:
        return self

    def __next__(self) -> AIStreamChunk:
        if self._fail_on_iter:
            raise RuntimeError("stream failure")
        if self._cancelled:
            raise StopIteration
        remaining = getattr(self, "_remaining", list(self._chunks))
        if not remaining:
            raise StopIteration
        chunk_text = remaining.pop(0)
        setattr(self, "_remaining", remaining)
        return AIStreamChunk(content=chunk_text)

    def final_response(self) -> AIResponse:
        meta: dict = {"finish_reason": "stop"}
        return AIResponse(
            self._final_text,
            provider=self._provider,
            model=self._model,
            latency_ms=self._latency,
            metadata=meta,
        )

    def cancel(self) -> None:
        self._cancel_called = True
        self._cancelled = True


def _make_ws() -> AsyncMock:
    ws = AsyncMock(spec=WebSocket)
    ws.headers = {}
    return ws


def _make_stream_manager(
    ai_manager: Any = None,
    ws_manager: Any = None,
) -> AIStreamManager:
    if ai_manager is None:
        am = MagicMock(spec=AIManager)
        am.ask_stream.return_value = _ChunkStream()
        ai_manager = am
    if ws_manager is None:
        ws_manager = WebSocketConnectionManager()
    return AIStreamManager(ai_manager=ai_manager, ws_manager=ws_manager)


def _make_controlled_ws():
    """Return (ws, sent_list, unblock) where ws.send_json blocks until unblock.set().

    The event starts **set** (sends pass through).  Call ``block.clear()``
    to stall sends, then ``block.set()`` to resume.
    """
    block = asyncio.Event()
    block.set()
    sent: list[dict] = []

    async def _send_json(data, *a, **kw):
        await block.wait()
        sent.append(data)

    ws = _make_ws()
    ws.send_json = _send_json
    return ws, sent, block


# ==========================================================================
# Lifecycle
# ==========================================================================


class TestAIStreamManagerLifecycle:
    @pytest.mark.asyncio
    async def test_start_stream_returns_stream_id(self):
        ws = _make_ws()
        wm = WebSocketConnectionManager()
        await wm.connect(ws, client_id="cli-1")
        mgr = _make_stream_manager(ws_manager=wm)
        sid = await mgr.start_stream("cli-1", "openai", "Hello")
        assert sid is not None
        assert sid.startswith("ws-")

    @pytest.mark.asyncio
    async def test_start_stream_with_custom_id(self):
        ws = _make_ws()
        wm = WebSocketConnectionManager()
        await wm.connect(ws, client_id="cli-1")
        mgr = _make_stream_manager(ws_manager=wm)
        sid = await mgr.start_stream("cli-1", "openai", "Hello", stream_id="my-id")
        assert sid == "my-id"

    @pytest.mark.asyncio
    async def test_cancel_stream_returns_true(self):
        ws = _make_ws()
        wm = WebSocketConnectionManager()
        await wm.connect(ws, client_id="cli-1")
        mgr = _make_stream_manager(ws_manager=wm)
        sid = await mgr.start_stream("cli-1", "openai", "Hello")
        result = await mgr.cancel_stream("cli-1", sid)
        assert result is True

    @pytest.mark.asyncio
    async def test_cancel_stream_wrong_client(self):
        ws = _make_ws()
        wm = WebSocketConnectionManager()
        await wm.connect(ws, client_id="cli-1")
        mgr = _make_stream_manager(ws_manager=wm)
        sid = await mgr.start_stream("cli-1", "openai", "Hello")
        result = await mgr.cancel_stream("cli-2", sid)
        assert result is False

    @pytest.mark.asyncio
    async def test_cancel_stream_unknown(self):
        mgr = _make_stream_manager()
        result = await mgr.cancel_stream("cli-1", "nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_cancel_all(self):
        ws, _sent, block = _make_controlled_ws()
        wm = WebSocketConnectionManager()
        await wm.connect(ws, client_id="cli-1")
        ws2, _sent2, block2 = _make_controlled_ws()
        await wm.connect(ws2, client_id="cli-2")
        mgr = _make_stream_manager(ws_manager=wm)
        block.clear()
        block2.clear()
        await mgr.start_stream("cli-1", "openai", "A")
        await mgr.start_stream("cli-1", "openai", "B")
        await mgr.start_stream("cli-2", "openai", "C")
        count = await mgr.cancel_all("cli-1")
        block.set()
        await asyncio.sleep(0.02)
        assert count == 2
        assert await mgr.get_active_count("cli-1") == 0
        assert await mgr.get_active_count("cli-2") == 1
        block2.set()
        await asyncio.sleep(0.02)

    @pytest.mark.asyncio
    async def test_cleanup(self):
        ws, _sent, block = _make_controlled_ws()
        wm = WebSocketConnectionManager()
        block.clear()
        await wm.connect(ws, client_id="cli-1")
        mgr = _make_stream_manager(ws_manager=wm)
        await mgr.start_stream("cli-1", "openai", "A")
        await mgr.cleanup("cli-1")
        block.set()
        assert await mgr.get_active_count("cli-1") == 0

    @pytest.mark.asyncio
    async def test_get_active_count(self):
        ws, _sent, block = _make_controlled_ws()
        wm = WebSocketConnectionManager()
        block.clear()
        await wm.connect(ws, client_id="cli-1")
        mgr = _make_stream_manager(ws_manager=wm)
        assert await mgr.get_active_count() == 0
        await mgr.start_stream("cli-1", "openai", "A")
        assert await mgr.get_active_count() == 1
        assert await mgr.get_active_count("cli-1") == 1
        assert await mgr.get_active_count("cli-2") == 0
        block.set()


# ==========================================================================
# Streaming behaviour
# ==========================================================================


class TestAIStreamForwarding:
    @pytest.mark.asyncio
    async def test_sends_chunks_to_client(self):
        ws = _make_ws()
        ws_mgr = WebSocketConnectionManager()
        await ws_mgr.connect(ws, client_id="cli-stream")
        stream = _ChunkStream(chunks=["Hel", "lo!"], final_text="Hello!")
        ai_mgr = MagicMock(spec=AIManager)
        ai_mgr.ask_stream.return_value = stream
        mgr = _make_stream_manager(ai_manager=ai_mgr, ws_manager=ws_mgr)
        await mgr.start_stream("cli-stream", "openai", "test")
        await asyncio.sleep(0.1)
        assert ws.send_json.await_count >= 2

    @pytest.mark.asyncio
    async def test_sends_complete_event(self):
        ws = _make_ws()
        ws_mgr = WebSocketConnectionManager()
        await ws_mgr.connect(ws, client_id="cli-complete")
        stream = _ChunkStream(chunks=["Hi"], final_text="Hi there!")
        ai_mgr = MagicMock(spec=AIManager)
        ai_mgr.ask_stream.return_value = stream
        mgr = _make_stream_manager(ai_manager=ai_mgr, ws_manager=ws_mgr)
        await mgr.start_stream("cli-complete", "openai", "test")
        await asyncio.sleep(0.1)
        calls = [c[0][0] for c in ws.send_json.await_args_list]
        complete_calls = [c for c in calls if c.get("type") == "ai.stream.complete"]
        assert len(complete_calls) == 1
        payload = complete_calls[0].get("payload", {})
        assert payload.get("content") == "Hi there!"
        assert payload.get("provider") == "test_provider"
        assert payload.get("latency_ms") == 5.0

    @pytest.mark.asyncio
    async def test_chunk_contains_metadata(self):
        ws = _make_ws()
        ws_mgr = WebSocketConnectionManager()
        await ws_mgr.connect(ws, client_id="cli-meta")
        stream = _ChunkStream(chunks=["Hello"])
        ai_mgr = MagicMock(spec=AIManager)
        ai_mgr.ask_stream.return_value = stream
        mgr = _make_stream_manager(ai_manager=ai_mgr, ws_manager=ws_mgr)
        await mgr.start_stream("cli-meta", "openai", "test")
        await asyncio.sleep(0.1)
        calls = [c[0][0] for c in ws.send_json.await_args_list]
        chunk = next(c for c in calls if c.get("type") == "ai.stream.chunk")
        payload = chunk.get("payload", {})
        assert "stream_id" in payload
        assert payload.get("content") == "Hello"
        assert payload.get("provider") == "openai"

    @pytest.mark.asyncio
    async def test_stream_error_sends_error_event(self):
        ws = _make_ws()
        ws_mgr = WebSocketConnectionManager()
        await ws_mgr.connect(ws, client_id="cli-err")
        stream = _ChunkStream(chunks=["x"], fail_on_iter=False)
        stream._fail_on_iter = True
        # Actually let's modify __next__ to raise on first call
        ai_mgr = MagicMock(spec=AIManager)
        fail_stream = _ChunkStream(chunks=[], fail_on_iter=True)
        ai_mgr.ask_stream.return_value = fail_stream
        mgr = _make_stream_manager(ai_manager=ai_mgr, ws_manager=ws_mgr)
        await mgr.start_stream("cli-err", "openai", "test")
        await asyncio.sleep(0.1)
        calls = [c[0][0] for c in ws.send_json.await_args_list]
        error_calls = [c for c in calls if c.get("type") == "ai.stream.error"]
        assert len(error_calls) >= 1


# ==========================================================================
# Cancellation
# ==========================================================================


class TestAICancellation:
    @pytest.mark.asyncio
    async def test_cancel_sends_cancelled_event(self):
        ws = _make_ws()
        ws_mgr = WebSocketConnectionManager()
        await ws_mgr.connect(ws, client_id="cli-cancel")
        stream = _ChunkStream(chunks=["Slow", "stream", "..."])
        ai_mgr = MagicMock(spec=AIManager)
        ai_mgr.ask_stream.return_value = stream
        mgr = _make_stream_manager(ai_manager=ai_mgr, ws_manager=ws_mgr)
        sid = await mgr.start_stream("cli-cancel", "openai", "test")
        await mgr.cancel_stream("cli-cancel", sid)
        await asyncio.sleep(0.05)
        calls = [c[0][0] for c in ws.send_json.await_args_list]
        cancelled = [c for c in calls if c.get("type") == "ai.stream.cancelled"]
        assert len(cancelled) >= 1

    @pytest.mark.asyncio
    async def test_cancel_calls_stream_cancel(self):
        stream = _ChunkStream(chunks=["Hello"])
        ai_mgr = MagicMock(spec=AIManager)
        ai_mgr.ask_stream.return_value = stream
        ws_mgr = WebSocketConnectionManager()
        ws, _sent, block = _make_controlled_ws()
        await ws_mgr.connect(ws, client_id="cli-cancel2")
        mgr = _make_stream_manager(ai_manager=ai_mgr, ws_manager=ws_mgr)
        block.clear()
        sid = await mgr.start_stream("cli-cancel2", "openai", "test")
        await mgr.cancel_stream("cli-cancel2", sid)
        block.set()
        assert stream._cancel_called is True

    @pytest.mark.asyncio
    async def test_cancel_all_cleans_up(self):
        ws, _sent, block = _make_controlled_ws()
        ws_mgr = WebSocketConnectionManager()
        block.clear()
        await ws_mgr.connect(ws, client_id="cli-ca")
        mgr = _make_stream_manager(ws_manager=ws_mgr)
        await mgr.start_stream("cli-ca", "openai", "A")
        await mgr.start_stream("cli-ca", "openai", "B")
        assert await mgr.get_active_count("cli-ca") == 2
        await mgr.cancel_all("cli-ca")
        block.set()
        assert await mgr.get_active_count("cli-ca") == 0


# ==========================================================================
# Incoming message handling
# ==========================================================================


class TestTryHandleMessage:
    @pytest.mark.asyncio
    async def test_ai_stream_start_message(self):
        ws = _make_ws()
        ws_mgr = WebSocketConnectionManager()
        await ws_mgr.connect(ws, client_id="cli-msg")
        stream = _ChunkStream(chunks=["Hi"])
        ai_mgr = MagicMock(spec=AIManager)
        ai_mgr.ask_stream.return_value = stream
        mgr = _make_stream_manager(ai_manager=ai_mgr, ws_manager=ws_mgr)
        raw = json.dumps({
            "type": "ai.stream.start",
            "payload": {"provider": "openai", "prompt": "Hello"},
        })
        handled = await mgr.try_handle_message("cli-msg", raw)
        assert handled is True
        await asyncio.sleep(0.05)
        assert ws.send_json.await_count >= 1

    @pytest.mark.asyncio
    async def test_ai_stream_cancel_message(self):
        ws = _make_ws()
        ws_mgr = WebSocketConnectionManager()
        await ws_mgr.connect(ws, client_id="cli-cancel-msg")
        stream = _ChunkStream(chunks=["Hello", "World"])
        ai_mgr = MagicMock(spec=AIManager)
        ai_mgr.ask_stream.return_value = stream
        mgr = _make_stream_manager(ai_manager=ai_mgr, ws_manager=ws_mgr)
        sid = await mgr.start_stream("cli-cancel-msg", "openai", "test")
        raw = json.dumps({
            "type": "ai.stream.cancel",
            "payload": {"stream_id": sid},
        })
        handled = await mgr.try_handle_message("cli-cancel-msg", raw)
        assert handled is True

    @pytest.mark.asyncio
    async def test_unknown_message_not_handled(self):
        mgr = _make_stream_manager()
        raw = json.dumps({"type": "subscribe", "event": "test"})
        handled = await mgr.try_handle_message("cli", raw)
        assert handled is False

    @pytest.mark.asyncio
    async def test_invalid_json_not_handled(self):
        mgr = _make_stream_manager()
        handled = await mgr.try_handle_message("cli", "not json{{{")
        assert handled is False

    @pytest.mark.asyncio
    async def test_start_without_provider_returns_error(self):
        ws = _make_ws()
        ws_mgr = WebSocketConnectionManager()
        await ws_mgr.connect(ws, client_id="cli-no-provider")
        mgr = _make_stream_manager(ws_manager=ws_mgr)
        raw = json.dumps({
            "type": "ai.stream.start",
            "payload": {"prompt": "Hello"},
        })
        handled = await mgr.try_handle_message("cli-no-provider", raw)
        assert handled is True
        await asyncio.sleep(0.05)
        calls = [c[0][0] for c in ws.send_json.await_args_list]
        errors = [c for c in calls if c.get("type") == "error"]
        assert len(errors) >= 1


# ==========================================================================
# Concurrent streams
# ==========================================================================


class TestConcurrentStreams:
    @pytest.mark.asyncio
    async def test_multiple_simultaneous_streams(self):
        ws, _sent, block = _make_controlled_ws()
        ws_mgr = WebSocketConnectionManager()
        block.clear()
        await ws_mgr.connect(ws, client_id="cli-con")
        ai_mgr = MagicMock(spec=AIManager)
        ai_mgr.ask_stream.return_value = _ChunkStream(chunks=["a", "b"])
        mgr = _make_stream_manager(ai_manager=ai_mgr, ws_manager=ws_mgr)
        s1 = await mgr.start_stream("cli-con", "openai", "Q1")
        s2 = await mgr.start_stream("cli-con", "openai", "Q2")
        assert await mgr.get_active_count("cli-con") == 2
        block.set()

    @pytest.mark.asyncio
    async def test_streams_isolated_per_client(self):
        ws1, _sent1, block1 = _make_controlled_ws()
        ws2, _sent2, block2 = _make_controlled_ws()
        ws_mgr = WebSocketConnectionManager()
        block1.clear()
        block2.clear()
        await ws_mgr.connect(ws1, client_id="cli-a")
        await ws_mgr.connect(ws2, client_id="cli-b")
        ai_mgr = MagicMock(spec=AIManager)
        ai_mgr.ask_stream.return_value = _ChunkStream(chunks=["x"])
        mgr = _make_stream_manager(ai_manager=ai_mgr, ws_manager=ws_mgr)
        await mgr.start_stream("cli-a", "openai", "A")
        await mgr.start_stream("cli-b", "openai", "B")
        assert await mgr.get_active_count("cli-a") == 1
        assert await mgr.get_active_count("cli-b") == 1
        await mgr.cancel_all("cli-a")
        block1.set()
        await asyncio.sleep(0.02)
        assert await mgr.get_active_count("cli-a") == 0
        assert await mgr.get_active_count("cli-b") == 1
        block2.set()
        await asyncio.sleep(0.02)


# ==========================================================================
# Connection lifecycle integration
# ==========================================================================


class TestConnectionLifecycle:
    @pytest.mark.asyncio
    async def test_disconnect_cleans_up_streams(self):
        ws, _sent, block = _make_controlled_ws()
        ws_mgr = WebSocketConnectionManager()
        block.clear()
        await ws_mgr.connect(ws, client_id="cli-disc")
        ai_mgr = MagicMock(spec=AIManager)
        ai_mgr.ask_stream.return_value = _ChunkStream(chunks=["a", "b", "c"])
        mgr = _make_stream_manager(ai_manager=ai_mgr, ws_manager=ws_mgr)
        await mgr.start_stream("cli-disc", "openai", "Q")
        assert await mgr.get_active_count("cli-disc") == 1
        await mgr.cleanup("cli-disc")
        block.set()
        assert await mgr.get_active_count("cli-disc") == 0

    @pytest.mark.asyncio
    async def test_cleanup_is_idempotent(self):
        mgr = _make_stream_manager()
        await mgr.cleanup("nonexistent")
        assert await mgr.get_active_count() == 0


# ==========================================================================
# Completion metadata
# ==========================================================================


class TestCompletionMetadata:
    @pytest.mark.asyncio
    async def test_complete_contains_provider_and_model(self):
        ws = _make_ws()
        ws_mgr = WebSocketConnectionManager()
        await ws_mgr.connect(ws, client_id="cli-meta")
        stream = _ChunkStream(
            chunks=["Hi"],
            provider="anthropic",
            model="claude-3",
        )
        ai_mgr = MagicMock(spec=AIManager)
        ai_mgr.ask_stream.return_value = stream
        mgr = _make_stream_manager(ai_manager=ai_mgr, ws_manager=ws_mgr)
        await mgr.start_stream("cli-meta", "anthropic", "test")
        await asyncio.sleep(0.1)
        calls = [c[0][0] for c in ws.send_json.await_args_list]
        complete = next(c for c in calls if c.get("type") == "ai.stream.complete")
        p = complete["payload"]
        assert p["provider"] == "anthropic"
        assert p["model"] == "claude-3"
        assert p["latency_ms"] == 5.0
        assert p["finish_reason"] == "stop"

    @pytest.mark.asyncio
    async def test_complete_contains_conversation_id(self):
        ws = _make_ws()
        ws_mgr = WebSocketConnectionManager()
        await ws_mgr.connect(ws, client_id="cli-conv")
        ai_mgr = MagicMock(spec=AIManager)
        ai_mgr.ask_stream.return_value = _ChunkStream()
        mgr = _make_stream_manager(ai_manager=ai_mgr, ws_manager=ws_mgr)
        await mgr.start_stream("cli-conv", "openai", "test", conversation_id="conv-111")
        await asyncio.sleep(0.1)
        calls = [c[0][0] for c in ws.send_json.await_args_list]
        complete = next(c for c in calls if c.get("type") == "ai.stream.complete")
        assert complete["payload"].get("conversation_id") == "conv-111"


# ==========================================================================
# Delegate to AIManager
# ==========================================================================


class TestDelegatesToAIManager:
    @pytest.mark.asyncio
    async def test_passes_provider_and_prompt(self):
        ai_mgr = MagicMock(spec=AIManager)
        ai_mgr.ask_stream.return_value = _ChunkStream()
        ws_mgr = WebSocketConnectionManager()
        ws = _make_ws()
        await ws_mgr.connect(ws, client_id="cli-del")
        mgr = _make_stream_manager(ai_manager=ai_mgr, ws_manager=ws_mgr)
        await mgr.start_stream("cli-del", "openai", "my prompt")
        ai_mgr.ask_stream.assert_called_once_with(
            "openai", "my prompt",
            conversation_id=None,
            prompt_template=None,
            template_variables=None,
        )

    @pytest.mark.asyncio
    async def test_passes_conversation_id(self):
        ai_mgr = MagicMock(spec=AIManager)
        ai_mgr.ask_stream.return_value = _ChunkStream()
        ws_mgr = WebSocketConnectionManager()
        ws = _make_ws()
        await ws_mgr.connect(ws, client_id="cli-del2")
        mgr = _make_stream_manager(ai_manager=ai_mgr, ws_manager=ws_mgr)
        await mgr.start_stream(
            "cli-del2", "openai", "prompt",
            conversation_id="conv-42",
        )
        ai_mgr.ask_stream.assert_called_once_with(
            "openai", "prompt",
            conversation_id="conv-42",
            prompt_template=None,
            template_variables=None,
        )

    @pytest.mark.asyncio
    async def test_ask_stream_called_with_all_params(self):
        ai_mgr = MagicMock(spec=AIManager)
        ai_mgr.ask_stream.return_value = _ChunkStream()
        ws_mgr = WebSocketConnectionManager()
        ws = _make_ws()
        await ws_mgr.connect(ws, client_id="cli-del3")
        mgr = _make_stream_manager(ai_manager=ai_mgr, ws_manager=ws_mgr)
        await mgr.start_stream(
            "cli-del3", "anthropic", "Hello",
            conversation_id="conv-1",
            prompt_template="my_template",
            template_variables={"name": "World"},
        )
        ai_mgr.ask_stream.assert_called_once_with(
            "anthropic", "Hello",
            conversation_id="conv-1",
            prompt_template="my_template",
            template_variables={"name": "World"},
        )


# ==========================================================================
# Backward compatibility
# ==========================================================================


class TestBackwardCompatibility:
    @pytest.mark.asyncio
    async def test_health_still_works(self):
        from app.api.server import create_app
        from fastapi.testclient import TestClient

        app = create_app()
        client = TestClient(app)
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200

    def test_ws_manager_unchanged(self):
        manager = WebSocketConnectionManager()
        assert hasattr(manager, "connect")
        assert hasattr(manager, "disconnect")
        assert hasattr(manager, "broadcast")
        assert hasattr(manager, "send_to_subscribers")
        assert hasattr(manager, "handle_message")

    def test_ws_message_types_extended(self):
        assert WSMessageType.AI_STREAM_START.value == "ai.stream.start"
        assert WSMessageType.AI_STREAM_CANCEL.value == "ai.stream.cancel"
        assert WSMessageType.AI_STREAM_CHUNK.value == "ai.stream.chunk"
        assert WSMessageType.AI_STREAM_COMPLETE.value == "ai.stream.complete"
        assert WSMessageType.AI_STREAM_CANCELLED.value == "ai.stream.cancelled"
        assert WSMessageType.AI_STREAM_ERROR.value == "ai.stream.error"
        assert WSMessageType.AI_STREAM_STARTED.value == "ai.stream.started"
