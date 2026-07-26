"""Tests for AIManager AI event publishing via EventBus."""

from __future__ import annotations

from typing import Generator
from unittest.mock import MagicMock, patch

import pytest

from app.ai.manager import AIManager
from app.ai.providers.base import AIProviderError, AIResponse, AIStreamChunk, AIStreamResponse
from app.core.events import AIEvents


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ai_response(text: str = "response", **kw: object) -> AIResponse:
    return AIResponse(
        text,
        provider=kw.get("provider", "test"),
        model=kw.get("model", "mock"),
        latency_ms=kw.get("latency_ms", 5.0),
        metadata=kw.get("metadata", {}),
    )


def _make_stream_response(
    chunks: list[str] | None = None,
    provider: str = "test",
    model: str = "mock",
) -> AIStreamResponse:
    chunks = chunks or ["chunk1", "chunk2"]

    def _gen() -> Generator[AIStreamChunk, None, None]:
        for c in chunks:
            yield AIStreamChunk(content=c)

    return AIStreamResponse(provider, model, _gen())


def _make_event_bus() -> MagicMock:
    return MagicMock()


# ==========================================================================
# Request / Response events
# ==========================================================================


class TestAskEvents:
    """AIManager.ask() publishes REQUEST and RESPONSE events."""

    def test_publishes_request_event(self):
        bus = _make_event_bus()
        mgr = AIManager(event_bus=bus)
        with patch.object(mgr.router, "ask_routed") as mock_ask:
            mock_ask.return_value = _make_ai_response()

            mgr.ask(None, "hello")

            bus.publish.assert_any_call(AIEvents.REQUEST, {
                "prompt_length": 5,
                "provider": None,
                "has_tools": False,
                "has_schema": False,
                "conversation_id": None,
            })

    def test_publishes_response_event(self):
        bus = _make_event_bus()
        mgr = AIManager(event_bus=bus)
        with patch.object(mgr.router, "ask_routed") as mock_ask:
            mock_ask.return_value = _make_ai_response("hi", provider="deepseek")

            mgr.ask(None, "hello")

            bus.publish.assert_any_call(AIEvents.RESPONSE, {
                "provider": "deepseek",
                "model": "mock",
                "latency_ms": 5.0,
                "response_length": 2,
                "conversation_id": None,
            })

    def test_publishes_with_conversation_id(self):
        bus = _make_event_bus()
        mgr = AIManager(event_bus=bus)
        conv = mgr.create_conversation()

        with patch.object(mgr.router, "ask_routed") as mock_ask:
            mock_ask.return_value = _make_ai_response("reply")

            mgr.ask(None, "hello", conversation_id=conv.conversation_id)

            bus.publish.assert_any_call(AIEvents.REQUEST, {
                "prompt_length": 5,
                "provider": None,
                "has_tools": False,
                "has_schema": False,
                "conversation_id": conv.conversation_id,
            })
            bus.publish.assert_any_call(AIEvents.RESPONSE, {
                "provider": "test",
                "model": "mock",
                "latency_ms": 5.0,
                "response_length": 5,
                "conversation_id": conv.conversation_id,
            })

    def test_does_not_publish_without_event_bus(self):
        mgr = AIManager()  # no event_bus
        with patch.object(mgr.router, "ask_routed") as mock_ask:
            mock_ask.return_value = _make_ai_response()

            mgr.ask(None, "hello")

    def test_publishes_with_explicit_provider(self):
        bus = _make_event_bus()
        mgr = AIManager(event_bus=bus)
        with patch.object(mgr.router, "ask") as mock_ask:
            mock_ask.return_value = _make_ai_response("ok", provider="openai")

            mgr.ask("openai", "prompt")

            bus.publish.assert_any_call(AIEvents.REQUEST, {
                "prompt_length": 6,
                "provider": "openai",
                "has_tools": False,
                "has_schema": False,
                "conversation_id": None,
            })


# ==========================================================================
# Streaming events
# ==========================================================================


class TestStreamEvents:
    """AIManager.ask_stream() publishes STREAM_START, STREAM_COMPLETE, STREAM_CANCEL."""

    def _get_event_data(self, bus: MagicMock, event: str) -> dict | None:
        for call in bus.publish.call_args_list:
            if call.args[0] == event:
                return call.args[1]
        return None

    def test_publishes_stream_start(self):
        bus = _make_event_bus()
        mgr = AIManager(event_bus=bus)
        with patch.object(mgr.router, "ask_stream") as mock_stream:
            mock_stream.return_value = _make_stream_response()
            stream = mgr.ask_stream("test", "hello")
            assert stream is not None

            data = self._get_event_data(bus, AIEvents.STREAM_START)
            assert data is not None
            assert data["provider"] == "test"
            assert data["prompt_length"] == 5
            assert data["conversation_id"] is None
            assert isinstance(data["stream_id"], str)
            assert data["stream_id"].startswith("test-")

    def test_publishes_stream_complete_on_exhaustion(self):
        bus = _make_event_bus()
        mgr = AIManager(event_bus=bus)
        with patch.object(mgr.router, "ask_stream") as mock_stream:
            mock_stream.return_value = _make_stream_response(
                ["hello ", "world"], provider="test", model="mock"
            )
            stream = mgr.ask_stream("test", "hello")
            list(stream)  # exhaust

            data = self._get_event_data(bus, AIEvents.STREAM_COMPLETE)
            assert data is not None
            assert isinstance(data["stream_id"], str)
            assert data["provider"] == "test"
            assert data["model"] == "mock"
            assert data["final_length"] == 11  # "hello world"

    def test_publishes_stream_cancel(self):
        bus = _make_event_bus()
        mgr = AIManager(event_bus=bus)
        with patch.object(mgr.router, "ask_stream") as mock_stream:
            mock_stream.return_value = _make_stream_response(
                ["a", "b", "c"], provider="test", model="mock"
            )
            stream = mgr.ask_stream("test", "hello")
            stream.cancel()

            data = self._get_event_data(bus, AIEvents.STREAM_CANCEL)
            assert data is not None
            assert isinstance(data["stream_id"], str)
            assert data["provider"] == "test"
            assert data["model"] == "mock"

    def test_stream_start_has_unique_stream_id(self):
        bus1 = _make_event_bus()
        bus2 = _make_event_bus()
        mgr1 = AIManager(event_bus=bus1)
        mgr2 = AIManager(event_bus=bus2)

        with patch.object(mgr1.router, "ask_stream") as mock_s1:
            mock_s1.return_value = _make_stream_response()
            s1 = mgr1.ask_stream("test", "hi")
            assert s1 is not None

        with patch.object(mgr2.router, "ask_stream") as mock_s2:
            mock_s2.return_value = _make_stream_response()
            s2 = mgr2.ask_stream("test", "hi")
            assert s2 is not None

        id1 = self._get_event_data(bus1, AIEvents.STREAM_START)["stream_id"]
        id2 = self._get_event_data(bus2, AIEvents.STREAM_START)["stream_id"]
        assert id1 != id2


# ==========================================================================
# Planning events
# ==========================================================================


class TestPlanEvents:
    """AIManager.plan() publishes PLAN_START, PLAN_COMPLETE, PLAN_FAIL."""

    def test_publishes_plan_start(self):
        bus = _make_event_bus()
        mgr = AIManager(event_bus=bus)
        with patch.object(mgr.router, "ask_routed") as mock_ask:
            mock_ask.return_value = _make_ai_response(
                '{"title": "t", "objective": "test", "steps": []}'
            )

            mgr.plan("test")

            bus.publish.assert_any_call(AIEvents.PLAN_START, {
                "objective": "test",
                "provider": None,
                "conversation_id": None,
            })

    def test_publishes_plan_complete(self):
        bus = _make_event_bus()
        mgr = AIManager(event_bus=bus)
        with patch.object(mgr.router, "ask_routed") as mock_ask:
            mock_ask.return_value = _make_ai_response(
                '{"title": "t", "objective": "test", '
                '"steps": [{"id": "s1", "title": "do"}]}'
            )

            mgr.plan("test")

            bus.publish.assert_any_call(AIEvents.PLAN_COMPLETE, {
                "provider": "test",
                "model": "mock",
                "num_steps": 1,
                "valid": True,
                "duration_ms": pytest.approx(0, abs=1000),
                "conversation_id": None,
            })

    def test_publishes_plan_fail_on_error(self):
        bus = _make_event_bus()
        mgr = AIManager(event_bus=bus)
        with patch.object(mgr.router, "ask_routed") as mock_ask:
            mock_ask.side_effect = AIProviderError("plan failed")

            with pytest.raises(AIProviderError):
                mgr.plan("test")

            bus.publish.assert_any_call(AIEvents.PLAN_FAIL, {
                "objective": "test",
                "error": "plan failed",
                "provider": None,
            })


# ==========================================================================
# Reasoning events
# ==========================================================================


class TestReasonEvents:
    """AIManager.reason() publishes REASON_START, REASON_COMPLETE, REASON_FAIL."""

    def test_publishes_reason_start(self):
        bus = _make_event_bus()
        mgr = AIManager(event_bus=bus)
        with patch.object(mgr.router, "ask_routed") as mock_ask:
            mock_ask.return_value = _make_ai_response(
                '{"objective": "why", "steps": [], "conclusion": "c"}'
            )

            mgr.reason("why")

            bus.publish.assert_any_call(AIEvents.REASON_START, {
                "objective": "why",
                "provider": None,
                "conversation_id": None,
            })

    def test_publishes_reason_complete(self):
        bus = _make_event_bus()
        mgr = AIManager(event_bus=bus)
        with patch.object(mgr.router, "ask_routed") as mock_ask:
            mock_ask.return_value = _make_ai_response(
                '{"objective": "why", "steps": [{"id": "rs1", '
                '"title": "think", "action": "act", "result": "ok"}], '
                '"conclusion": "c"}'
            )

            mgr.reason("why")

            bus.publish.assert_any_call(AIEvents.REASON_COMPLETE, {
                "provider": "test",
                "model": "mock",
                "num_steps": 1,
                "valid": True,
                "duration_ms": pytest.approx(0, abs=1000),
                "conversation_id": None,
            })

    def test_publishes_reason_fail_on_error(self):
        bus = _make_event_bus()
        mgr = AIManager(event_bus=bus)
        with patch.object(mgr.router, "ask_routed") as mock_ask:
            mock_ask.side_effect = AIProviderError("reason failed")

            with pytest.raises(AIProviderError):
                mgr.reason("why")

            bus.publish.assert_any_call(AIEvents.REASON_FAIL, {
                "objective": "why",
                "error": "reason failed",
                "provider": None,
            })


# ==========================================================================
# Conversation lifecycle events
# ==========================================================================


class TestConversationEvents:
    """AIManager.create_conversation() publishes CONVERSATION_CREATE."""

    def test_publishes_conversation_create(self):
        bus = _make_event_bus()
        mgr = AIManager(event_bus=bus)

        conv = mgr.create_conversation(provider="test", model="mock")

        bus.publish.assert_called_with(AIEvents.CONVERSATION_CREATE, {
            "conversation_id": conv.conversation_id,
            "provider": "test",
            "model": "mock",
        })


# ==========================================================================
# Event ordering
# ==========================================================================


class TestEventOrdering:
    """Events are published in the correct order for each operation."""

    def test_ask_events_ordered_request_then_response(self):
        bus = _make_event_bus()
        mgr = AIManager(event_bus=bus)
        with patch.object(mgr.router, "ask_routed") as mock_ask:
            mock_ask.return_value = _make_ai_response("ok")

            mgr.ask(None, "hello")

            events = [call.args[0] for call in bus.publish.call_args_list]
            assert events == [AIEvents.REQUEST, AIEvents.RESPONSE]

    def test_plan_events_ordered_start_then_complete(self):
        bus = _make_event_bus()
        mgr = AIManager(event_bus=bus)
        with patch.object(mgr.router, "ask_routed") as mock_ask:
            mock_ask.return_value = _make_ai_response(
                '{"title": "t", "objective": "test", '
                '"steps": [{"id": "s1", "title": "do", "action": "a", "result": "r"}]}'
            )

            mgr.plan("test")

            events = [call.args[0] for call in bus.publish.call_args_list]
            assert events == [
                AIEvents.PLAN_START,
                AIEvents.PLAN_COMPLETE,
            ]

    def test_reason_events_ordered_start_then_complete(self):
        bus = _make_event_bus()
        mgr = AIManager(event_bus=bus)
        with patch.object(mgr.router, "ask_routed") as mock_ask:
            mock_ask.return_value = _make_ai_response(
                '{"objective": "why", "steps": [], "conclusion": "c"}'
            )

            mgr.reason("why")

            events = [call.args[0] for call in bus.publish.call_args_list]
            assert events == [
                AIEvents.REASON_START,
                AIEvents.REASON_COMPLETE,
            ]

    def test_stream_events_ordered_start_then_complete(self):
        bus = _make_event_bus()
        mgr = AIManager(event_bus=bus)
        with patch.object(mgr.router, "ask_stream") as mock_stream:
            mock_stream.return_value = _make_stream_response(
                ["a"], provider="test", model="mock"
            )
            stream = mgr.ask_stream("test", "hello")
            list(stream)

            events = [call.args[0] for call in bus.publish.call_args_list]
            assert AIEvents.STREAM_START in events
            assert AIEvents.STREAM_COMPLETE in events
            assert events.index(AIEvents.STREAM_START) < events.index(
                AIEvents.STREAM_COMPLETE
            )


# ==========================================================================
# Error handling
# ==========================================================================


class TestEventErrorHandling:
    """Event failures never interrupt AI operations."""

    def test_event_bus_error_does_not_break_ask(self):
        bus = _make_event_bus()
        bus.publish.side_effect = RuntimeError("bus down")
        mgr = AIManager(event_bus=bus)

        with patch.object(mgr.router, "ask_routed") as mock_ask:
            mock_ask.return_value = _make_ai_response("ok")
            result = mgr.ask(None, "hello")
            assert str(result) == "ok"


# ==========================================================================
# Metadata in events
# ==========================================================================


class TestEventMetadata:
    """Events carry relevant operational metadata."""

    def test_response_event_has_provider_model_latency(self):
        bus = _make_event_bus()
        mgr = AIManager(event_bus=bus)
        with patch.object(mgr.router, "ask_routed") as mock_ask:
            mock_ask.return_value = _make_ai_response(
                "x", provider="deepseek", model="v3", latency_ms=42.0
            )

            mgr.ask(None, "prompt")

            for call in bus.publish.call_args_list:
                if call.args[0] == AIEvents.RESPONSE:
                    data = call.args[1]
                    assert data["provider"] == "deepseek"
                    assert data["model"] == "v3"
                    assert data["latency_ms"] == 42.0
                    break
            else:
                pytest.fail("RESPONSE event not found")

    def test_request_event_has_prompt_length(self):
        bus = _make_event_bus()
        mgr = AIManager(event_bus=bus)
        with patch.object(mgr.router, "ask_routed") as mock_ask:
            mock_ask.return_value = _make_ai_response("x")

            mgr.ask(None, "12345")

            for call in bus.publish.call_args_list:
                if call.args[0] == AIEvents.REQUEST:
                    data = call.args[1]
                    assert data["prompt_length"] == 5
                    break
            else:
                pytest.fail("REQUEST event not found")

    def test_plan_complete_has_step_count(self):
        bus = _make_event_bus()
        mgr = AIManager(event_bus=bus)
        with patch.object(mgr.router, "ask_routed") as mock_ask:
            mock_ask.return_value = _make_ai_response(
                '{"title": "t", "objective": "test", '
                '"steps": [{"id": "s1", "title": "do"}]}'
            )

            mgr.plan("test")

            for call in bus.publish.call_args_list:
                if call.args[0] == AIEvents.PLAN_COMPLETE:
                    data = call.args[1]
                    assert data["num_steps"] == 1
                    break
            else:
                pytest.fail("PLAN_COMPLETE event not found")


# ==========================================================================
# Backward compatibility
# ==========================================================================


class TestBackwardCompatibility:
    """AIManager without event_bus works exactly as before."""

    def test_ask_works_without_event_bus(self):
        mgr = AIManager()
        with patch.object(mgr.router, "ask_routed") as mock_ask:
            mock_ask.return_value = _make_ai_response("ok")
            result = mgr.ask(None, "hello")
            assert str(result) == "ok"

    def test_ask_stream_works_without_event_bus(self):
        mgr = AIManager()
        with patch.object(mgr.router, "ask_stream") as mock_stream:
            mock_stream.return_value = _make_stream_response(
                ["data"], provider="test", model="mock"
            )
            stream = mgr.ask_stream("test", "hello")
            assert list(stream)

    def test_plan_works_without_event_bus(self):
        mgr = AIManager()
        with patch.object(mgr.router, "ask_routed") as mock_ask:
            mock_ask.return_value = _make_ai_response(
                '{"title": "t", "objective": "test", "steps": []}'
            )
            result = mgr.plan("test")
            assert result.provider == "test"

    def test_reason_works_without_event_bus(self):
        mgr = AIManager()
        with patch.object(mgr.router, "ask_routed") as mock_ask:
            mock_ask.return_value = _make_ai_response(
                '{"objective": "why", "steps": [], "conclusion": "c"}'
            )
            result = mgr.reason("why")
            assert result.provider == "test"

    def test_create_conversation_works_without_event_bus(self):
        mgr = AIManager()
        conv = mgr.create_conversation()
        assert conv is not None
        assert conv.conversation_id
