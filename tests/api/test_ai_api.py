"""Tests for the AI REST API layer (P11-02)."""

from __future__ import annotations

from typing import Any, Generator
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.ai.conversation import Conversation, ConversationManager
from app.ai.manager import AIManager
from app.ai.providers.base import AIResponse, AIStreamChunk, AIStreamResponse
from app.ai.routing import ProviderStatus
from app.api.schemas import (
    ChatResponse,
    ConversationCreateResponse,
    ConversationListResponse,
    ConversationSummary,
    MessageListResponse,
    MessageResponse,
    ModelInfo,
    ModelListResponse,
    PlanResponse,
    PlanStep as PlanStepSchema,
    ProviderInfo,
    ProviderListResponse,
    ReasonResponse,
    ReasonStep as ReasonStepSchema,
)
from app.api.server import create_app
from app.core.registry import ServiceRegistry


# ==========================================================================
# Helpers
# ==========================================================================


def _make_ai_response(
    text: str = "Hello!",
    provider: str = "test_provider",
    model: str = "test-model",
    latency_ms: float = 10.0,
    metadata: dict | None = None,
) -> MagicMock:
    resp = MagicMock(spec=AIResponse)
    resp.__str__.return_value = text
    resp.provider = provider
    resp.model = model
    resp.latency_ms = latency_ms
    resp.metadata = metadata or {}
    return resp


def _make_plan_result(steps: list | None = None, **kwargs) -> MagicMock:
    res = MagicMock()
    res.provider = kwargs.get("provider", "test_provider")
    res.model = kwargs.get("model", "test-model")
    res.duration_ms = kwargs.get("duration_ms", 20.0)
    res.valid = kwargs.get("valid", True)
    res.validation_errors = kwargs.get("validation_errors", [])
    res.metadata = kwargs.get("metadata", {})
    plan = MagicMock()
    s = steps or [
        MagicMock(step=1, action="Do A", reasoning="Because", expected_outcome="Out A"),
        MagicMock(step=2, action="Do B", reasoning="Therefore", expected_outcome="Out B"),
    ]
    plan.steps = s
    res.plan = plan
    return res


def _make_reason_result(steps: list | None = None, **kwargs) -> MagicMock:
    res = MagicMock()
    res.provider = kwargs.get("provider", "test_provider")
    res.model = kwargs.get("model", "test-model")
    res.duration_ms = kwargs.get("duration_ms", 15.0)
    res.valid = kwargs.get("valid", True)
    res.validation_errors = kwargs.get("validation_errors", [])
    res.metadata = kwargs.get("metadata", {})
    chain = MagicMock()
    s = steps or [
        MagicMock(step=1, statement="Fact A", evidence="Proof A", conclusion="Thus A"),
        MagicMock(step=2, statement="Fact B", evidence="Proof B", conclusion="Thus B"),
    ]
    chain.steps = s
    res.chain = chain
    return res


class _ChunkStream(AIStreamResponse):
    """A simple stream that yields chunks and returns a final response."""

    def __init__(
        self,
        chunks: list[str],
        final_text: str = "Complete!",
        provider: str = "test_provider",
        model: str = "test-model",
        latency: float = 5.0,
    ):
        self._chunks = chunks
        self._final_text = final_text
        self._provider = provider
        self._model = model
        self._latency = latency

    def __iter__(self):
        yield from [AIStreamChunk(content=c) for c in self._chunks]

    def __next__(self) -> AIStreamChunk:
        raise StopIteration

    def final_response(self) -> AIResponse:
        return _make_ai_response(
            text=self._final_text,
            provider=self._provider,
            model=self._model,
            latency_ms=self._latency,
        )

    def cancel(self) -> None:
        pass


def _make_app(
    registry: ServiceRegistry | None = None,
    ai_manager: AIManager | None = None,
) -> FastAPI:
    if registry is None:
        registry = ServiceRegistry()
    if ai_manager is not None:
        registry.register("ai_manager", ai_manager)
    return create_app(registry)


def _make_client(
    registry: ServiceRegistry | None = None,
    ai_manager: AIManager | None = None,
) -> TestClient:
    app = _make_app(registry, ai_manager)
    return TestClient(app)


# ==========================================================================
# AI route registration
# ==========================================================================


class TestAIRouteRegistration:
    """AI routes are registered in the OpenAPI schema."""

    def test_ai_routes_in_openapi(self):
        client = _make_client()
        schema = client.get("/api/v1/openapi.json").json()
        paths = schema["paths"]
        assert "/api/v1/ai/chat" in paths
        assert "/api/v1/ai/chat/stream" in paths
        assert "/api/v1/ai/plan" in paths
        assert "/api/v1/ai/reason" in paths
        assert "/api/v1/ai/conversations" in paths
        assert "/api/v1/ai/providers" in paths
        assert "/api/v1/ai/models" in paths

    def test_ai_routes_return_503_without_service(self):
        client = _make_client()
        for path, method in [
            ("/api/v1/ai/chat", "post"),
            ("/api/v1/ai/chat/stream", "post"),
            ("/api/v1/ai/plan", "post"),
            ("/api/v1/ai/reason", "post"),
            ("/api/v1/ai/conversations", "get"),
            ("/api/v1/ai/conversations", "post"),
            ("/api/v1/ai/providers", "get"),
            ("/api/v1/ai/models", "get"),
        ]:
            if method == "post":
                r = client.post(path, json={"prompt": "hi"})
            else:
                r = client.get(path)
            assert r.status_code == 503, f"{method.upper()} {path}"

    def test_ai_routes_openapi_types(self):
        client = _make_client()
        schema = client.get("/api/v1/openapi.json").json()
        paths = schema["paths"]
        assert "post" in paths["/api/v1/ai/chat"]
        assert "post" in paths["/api/v1/ai/chat/stream"]
        assert "post" in paths["/api/v1/ai/plan"]
        assert "post" in paths["/api/v1/ai/reason"]
        assert "get" in paths["/api/v1/ai/conversations"]
        assert "post" in paths["/api/v1/ai/conversations"]
        assert "get" in paths["/api/v1/ai/providers"]
        assert "get" in paths["/api/v1/ai/models"]


# ==========================================================================
# Chat endpoint
# ==========================================================================


class TestChatEndpoint:
    """POST /api/v1/ai/chat."""

    def test_chat_returns_response(self):
        ai = MagicMock(spec=AIManager)
        ai.ask.return_value = _make_ai_response("Hello world")
        client = _make_client(ai_manager=ai)
        r = client.post("/api/v1/ai/chat", json={"prompt": "Hi"})
        assert r.status_code == 200
        data = r.json()
        assert data["response"] == "Hello world"
        assert data["provider"] == "test_provider"
        assert data["model"] == "test-model"

    def test_chat_passes_conversation_id(self):
        ai = MagicMock(spec=AIManager)
        ai.ask.return_value = _make_ai_response("Reply")
        client = _make_client(ai_manager=ai)
        r = client.post(
            "/api/v1/ai/chat",
            json={"prompt": "Hi", "conversation_id": "conv-123"},
        )
        assert r.status_code == 200
        assert ai.ask.call_args[1]["conversation_id"] == "conv-123"

    def test_chat_passes_provider(self):
        ai = MagicMock(spec=AIManager)
        ai.ask.return_value = _make_ai_response("Reply")
        client = _make_client(ai_manager=ai)
        r = client.post(
            "/api/v1/ai/chat",
            json={"prompt": "Hi", "provider": "openai"},
        )
        assert r.status_code == 200
        assert ai.ask.call_args[1]["provider"] == "openai"

    def test_chat_passes_prompt_template(self):
        ai = MagicMock(spec=AIManager)
        ai.ask.return_value = _make_ai_response("Reply")
        client = _make_client(ai_manager=ai)
        r = client.post(
            "/api/v1/ai/chat",
            json={
                "prompt": "Hi",
                "prompt_template": "greeting",
                "template_variables": {"name": "Alex"},
            },
        )
        assert r.status_code == 200
        assert ai.ask.call_args[1]["prompt_template"] == "greeting"
        assert ai.ask.call_args[1]["template_variables"] == {"name": "Alex"}

    def test_chat_returns_latency(self):
        ai = MagicMock(spec=AIManager)
        ai.ask.return_value = _make_ai_response("Hi", latency_ms=42.5)
        client = _make_client(ai_manager=ai)
        r = client.post("/api/v1/ai/chat", json={"prompt": "Hi"})
        assert r.json()["latency_ms"] == 42.5

    def test_chat_returns_metadata(self):
        ai = MagicMock(spec=AIManager)
        ai.ask.return_value = _make_ai_response("Hi", metadata={"tokens": 10})
        client = _make_client(ai_manager=ai)
        r = client.post("/api/v1/ai/chat", json={"prompt": "Hi"})
        assert r.json()["metadata"].get("tokens") == 10

    def test_chat_model_validation(self):
        ai = MagicMock(spec=AIManager)
        ai.ask.return_value = _make_ai_response("Hi")
        client = _make_client(ai_manager=ai)
        r = client.post("/api/v1/ai/chat", json={"prompt": "Hi"})
        model = ChatResponse(**r.json())
        assert model.response == "Hi"

    def test_chat_without_prompt_returns_422(self):
        ai = MagicMock(spec=AIManager)
        client = _make_client(ai_manager=ai)
        r = client.post("/api/v1/ai/chat", json={})
        assert r.status_code == 422

    def test_chat_handles_unknown_provider(self):
        ai = MagicMock(spec=AIManager)
        ai.ask.side_effect = ValueError("Unknown provider: foo")
        client = _make_client(ai_manager=ai)
        r = client.post(
            "/api/v1/ai/chat",
            json={"prompt": "Hi", "provider": "foo"},
        )
        assert r.status_code == 404
        assert "foo" in r.json()["error"]["message"]

    def test_chat_is_sorted_by_conversation_id(self):
        ai = MagicMock(spec=AIManager)
        ai.ask.return_value = _make_ai_response("Hi")
        client = _make_client(ai_manager=ai)
        r = client.post(
            "/api/v1/ai/chat",
            json={"prompt": "Hi", "conversation_id": "conv-abc"},
        )
        assert r.status_code == 200
        assert r.json()["conversation_id"] == "conv-abc"


# ==========================================================================
# Streaming chat endpoint
# ==========================================================================


class TestChatStreamEndpoint:
    """POST /api/v1/ai/chat/stream."""

    def test_stream_returns_200(self):
        ai = MagicMock(spec=AIManager)
        ai.ask_stream.return_value = _ChunkStream(["Hello", " world"])
        client = _make_client(ai_manager=ai)
        r = client.post(
            "/api/v1/ai/chat/stream",
            json={"prompt": "Hi"},
        )
        assert r.status_code == 200

    def test_stream_content_type(self):
        ai = MagicMock(spec=AIManager)
        ai.ask_stream.return_value = _ChunkStream([])
        client = _make_client(ai_manager=ai)
        r = client.post(
            "/api/v1/ai/chat/stream",
            json={"prompt": "Hi"},
        )
        assert r.headers.get("content-type", "").startswith("text/event-stream")

    def test_stream_yields_chunks(self):
        ai = MagicMock(spec=AIManager)
        ai.ask_stream.return_value = _ChunkStream(["Hello", " world"])
        client = _make_client(ai_manager=ai)
        r = client.post(
            "/api/v1/ai/chat/stream",
            json={"prompt": "Hi"},
        )
        assert r.status_code == 200
        text = r.text
        assert "Hello" in text
        assert "world" in text

    def test_stream_yields_final_response(self):
        ai = MagicMock(spec=AIManager)
        ai.ask_stream.return_value = _ChunkStream(["Hello"], final_text="Hello!")
        client = _make_client(ai_manager=ai)
        r = client.post(
            "/api/v1/ai/chat/stream",
            json={"prompt": "Hi"},
        )
        assert r.status_code == 200
        assert "Hello!" in r.text

    def test_stream_yields_done_marker(self):
        ai = MagicMock(spec=AIManager)
        ai.ask_stream.return_value = _ChunkStream([])
        client = _make_client(ai_manager=ai)
        r = client.post(
            "/api/v1/ai/chat/stream",
            json={"prompt": "Hi"},
        )
        assert "[DONE]" in r.text

    def test_stream_handles_unknown_provider(self):
        ai = MagicMock(spec=AIManager)
        ai.ask_stream.side_effect = ValueError("Unknown provider: foo")
        client = _make_client(ai_manager=ai)
        r = client.post(
            "/api/v1/ai/chat/stream",
            json={"prompt": "Hi", "provider": "foo"},
        )
        assert r.status_code == 200
        assert "error" in r.text

    def test_stream_defaults_to_openai_provider(self):
        ai = MagicMock(spec=AIManager)
        ai.ask_stream.return_value = _ChunkStream([])
        client = _make_client(ai_manager=ai)
        r = client.post(
            "/api/v1/ai/chat/stream",
            json={"prompt": "Hi"},
        )
        assert r.status_code == 200
        call_kwargs = ai.ask_stream.call_args[1]
        assert call_kwargs["provider"] == "openai"

    def test_stream_passes_conversation_id(self):
        ai = MagicMock(spec=AIManager)
        ai.ask_stream.return_value = _ChunkStream([])
        client = _make_client(ai_manager=ai)
        r = client.post(
            "/api/v1/ai/chat/stream",
            json={"prompt": "Hi", "conversation_id": "conv-5"},
        )
        assert r.status_code == 200
        assert ai.ask_stream.call_args[1]["conversation_id"] == "conv-5"

    def test_stream_headers(self):
        ai = MagicMock(spec=AIManager)
        ai.ask_stream.return_value = _ChunkStream([])
        client = _make_client(ai_manager=ai)
        r = client.post(
            "/api/v1/ai/chat/stream",
            json={"prompt": "Hi"},
        )
        assert r.headers.get("cache-control") == "no-cache"
        assert r.headers.get("x-accel-buffering") == "no"


# ==========================================================================
# Plan endpoint
# ==========================================================================


class TestPlanEndpoint:
    """POST /api/v1/ai/plan."""

    def test_plan_returns_steps(self):
        ai = MagicMock(spec=AIManager)
        ai.plan.return_value = _make_plan_result()
        client = _make_client(ai_manager=ai)
        r = client.post(
            "/api/v1/ai/plan",
            json={"objective": "Build a house"},
        )
        assert r.status_code == 200
        data = r.json()
        assert len(data["steps"]) == 2
        assert data["steps"][0]["action"] == "Do A"

    def test_plan_returns_provider_model(self):
        ai = MagicMock(spec=AIManager)
        ai.plan.return_value = _make_plan_result(
            provider="openai", model="gpt-4",
        )
        client = _make_client(ai_manager=ai)
        r = client.post("/api/v1/ai/plan", json={"objective": "X"})
        assert r.json()["provider"] == "openai"
        assert r.json()["model"] == "gpt-4"

    def test_plan_returns_duration(self):
        ai = MagicMock(spec=AIManager)
        ai.plan.return_value = _make_plan_result(duration_ms=33.0)
        client = _make_client(ai_manager=ai)
        r = client.post("/api/v1/ai/plan", json={"objective": "X"})
        assert r.json()["duration_ms"] == 33.0

    def test_plan_returns_validation(self):
        ai = MagicMock(spec=AIManager)
        ai.plan.return_value = _make_plan_result(
            valid=False, validation_errors=["Step 1 too vague"],
        )
        client = _make_client(ai_manager=ai)
        r = client.post("/api/v1/ai/plan", json={"objective": "X"})
        assert r.json()["valid"] is False
        assert "too vague" in r.json()["validation_errors"][0]

    def test_plan_model_validation(self):
        ai = MagicMock(spec=AIManager)
        ai.plan.return_value = _make_plan_result()
        client = _make_client(ai_manager=ai)
        r = client.post("/api/v1/ai/plan", json={"objective": "X"})
        model = PlanResponse(**r.json())
        assert len(model.steps) == 2

    def test_plan_passes_custom_prompt(self):
        ai = MagicMock(spec=AIManager)
        ai.plan.return_value = _make_plan_result()
        client = _make_client(ai_manager=ai)
        r = client.post(
            "/api/v1/ai/plan",
            json={
                "objective": "X",
                "planning_prompt": "Plan: {objective}",
            },
        )
        assert r.status_code == 200
        assert ai.plan.call_args[1]["planning_prompt"] == "Plan: {objective}"

    def test_plan_passes_template(self):
        ai = MagicMock(spec=AIManager)
        ai.plan.return_value = _make_plan_result()
        client = _make_client(ai_manager=ai)
        r = client.post(
            "/api/v1/ai/plan",
            json={
                "objective": "X",
                "prompt_template": "planner",
                "template_variables": {"goal": "X"},
            },
        )
        assert r.status_code == 200
        assert ai.plan.call_args[1]["prompt_template"] == "planner"

    def test_plan_without_objective_returns_422(self):
        ai = MagicMock(spec=AIManager)
        client = _make_client(ai_manager=ai)
        r = client.post("/api/v1/ai/plan", json={})
        assert r.status_code == 422

    def test_plan_metadata(self):
        ai = MagicMock(spec=AIManager)
        ai.plan.return_value = _make_plan_result(metadata={"routing": "preferred"})
        client = _make_client(ai_manager=ai)
        r = client.post("/api/v1/ai/plan", json={"objective": "X"})
        assert r.json()["metadata"].get("routing") == "preferred"


# ==========================================================================
# Reason endpoint
# ==========================================================================


class TestReasonEndpoint:
    """POST /api/v1/ai/reason."""

    def test_reason_returns_steps(self):
        ai = MagicMock(spec=AIManager)
        ai.reason.return_value = _make_reason_result()
        client = _make_client(ai_manager=ai)
        r = client.post(
            "/api/v1/ai/reason",
            json={"objective": "Why?"},
        )
        assert r.status_code == 200
        data = r.json()
        assert len(data["steps"]) == 2
        assert data["steps"][0]["statement"] == "Fact A"

    def test_reason_returns_provider_model(self):
        ai = MagicMock(spec=AIManager)
        ai.reason.return_value = _make_reason_result(
            provider="anthropic", model="claude-3",
        )
        client = _make_client(ai_manager=ai)
        r = client.post("/api/v1/ai/reason", json={"objective": "X"})
        assert r.json()["provider"] == "anthropic"
        assert r.json()["model"] == "claude-3"

    def test_reason_returns_duration(self):
        ai = MagicMock(spec=AIManager)
        ai.reason.return_value = _make_reason_result(duration_ms=25.0)
        client = _make_client(ai_manager=ai)
        r = client.post("/api/v1/ai/reason", json={"objective": "X"})
        assert r.json()["duration_ms"] == 25.0

    def test_reason_validation(self):
        ai = MagicMock(spec=AIManager)
        ai.reason.return_value = _make_reason_result(
            valid=False, validation_errors=["Missing evidence"],
        )
        client = _make_client(ai_manager=ai)
        r = client.post("/api/v1/ai/reason", json={"objective": "X"})
        assert r.json()["valid"] is False
        assert "Missing evidence" in r.json()["validation_errors"][0]

    def test_reason_model_validation(self):
        ai = MagicMock(spec=AIManager)
        ai.reason.return_value = _make_reason_result()
        client = _make_client(ai_manager=ai)
        r = client.post("/api/v1/ai/reason", json={"objective": "X"})
        model = ReasonResponse(**r.json())
        assert len(model.steps) == 2

    def test_reason_passes_custom_prompt(self):
        ai = MagicMock(spec=AIManager)
        ai.reason.return_value = _make_reason_result()
        client = _make_client(ai_manager=ai)
        r = client.post(
            "/api/v1/ai/reason",
            json={
                "objective": "X",
                "reasoning_prompt": "Reason: {objective}",
            },
        )
        assert r.status_code == 200
        assert ai.reason.call_args[1]["reasoning_prompt"] == "Reason: {objective}"

    def test_reason_without_objective_returns_422(self):
        ai = MagicMock(spec=AIManager)
        client = _make_client(ai_manager=ai)
        r = client.post("/api/v1/ai/reason", json={})
        assert r.status_code == 422

    def test_reason_handles_value_error(self):
        ai = MagicMock(spec=AIManager)
        ai.reason.side_effect = ValueError("Bad provider")
        client = _make_client(ai_manager=ai)
        r = client.post("/api/v1/ai/reason", json={"objective": "X"})
        assert r.status_code == 404

    def test_reason_metadata(self):
        ai = MagicMock(spec=AIManager)
        ai.reason.return_value = _make_reason_result(metadata={"logic": "deductive"})
        client = _make_client(ai_manager=ai)
        r = client.post("/api/v1/ai/reason", json={"objective": "X"})
        assert r.json()["metadata"].get("logic") == "deductive"


# ==========================================================================
# Conversation endpoints
# ==========================================================================


class TestListConversationsEndpoint:
    """GET /api/v1/ai/conversations."""

    def test_list_returns_empty_when_no_conversations(self):
        cm = ConversationManager()
        ai = MagicMock(spec=AIManager)
        ai.conversation_manager = cm
        client = _make_client(ai_manager=ai)
        r = client.get("/api/v1/ai/conversations")
        assert r.status_code == 200
        assert r.json()["conversations"] == []

    def test_list_returns_conversations(self):
        cm = ConversationManager()
        cm.create(provider="openai", model="gpt-4", system_prompt="Be helpful")
        ai = MagicMock(spec=AIManager)
        ai.conversation_manager = cm
        client = _make_client(ai_manager=ai)
        r = client.get("/api/v1/ai/conversations")
        assert r.status_code == 200
        data = r.json()
        assert len(data["conversations"]) == 1
        assert data["conversations"][0]["provider"] == "openai"

    def test_list_sorted_by_updated_at(self):
        cm = ConversationManager()
        c1 = cm.create()
        c2 = cm.create()
        c3 = cm.create()
        import time
        time.sleep(0.01)
        ai = MagicMock(spec=AIManager)
        ai.conversation_manager = cm
        client = _make_client(ai_manager=ai)
        r = client.get("/api/v1/ai/conversations")
        times = [c["updated_at"] for c in r.json()["conversations"]]
        assert times == sorted(times, reverse=True)

    def test_list_model_validation(self):
        cm = ConversationManager()
        cm.create(provider="x", model="y")
        ai = MagicMock(spec=AIManager)
        ai.conversation_manager = cm
        client = _make_client(ai_manager=ai)
        r = client.get("/api/v1/ai/conversations")
        ConversationListResponse(**r.json())

    def test_list_shows_message_count(self):
        cm = ConversationManager()
        conv = cm.create()
        cm.add_message(conv.conversation_id, "user", "Hi")
        cm.add_message(conv.conversation_id, "assistant", "Hello")
        ai = MagicMock(spec=AIManager)
        ai.conversation_manager = cm
        client = _make_client(ai_manager=ai)
        r = client.get("/api/v1/ai/conversations")
        assert r.json()["conversations"][0]["message_count"] == 2

    def test_list_includes_system_prompt(self):
        cm = ConversationManager()
        cm.create(system_prompt="You are a bot")
        ai = MagicMock(spec=AIManager)
        ai.conversation_manager = cm
        client = _make_client(ai_manager=ai)
        r = client.get("/api/v1/ai/conversations")
        assert r.json()["conversations"][0]["system_prompt"] == "You are a bot"


class TestGetConversationEndpoint:
    """GET /api/v1/ai/conversations/{id}."""

    def test_get_returns_conversation(self):
        cm = ConversationManager()
        conv = cm.create(provider="openai", model="gpt-4")
        ai = MagicMock(spec=AIManager)
        ai.conversation_manager = cm
        client = _make_client(ai_manager=ai)
        r = client.get(f"/api/v1/ai/conversations/{conv.conversation_id}")
        assert r.status_code == 200
        assert r.json()["provider"] == "openai"
        assert r.json()["model"] == "gpt-4"

    def test_get_returns_404_for_missing(self):
        ai = MagicMock(spec=AIManager)
        ai.conversation_manager = ConversationManager()
        client = _make_client(ai_manager=ai)
        r = client.get("/api/v1/ai/conversations/nonexistent")
        assert r.status_code == 404

    def test_get_model_validation(self):
        cm = ConversationManager()
        conv = cm.create()
        ai = MagicMock(spec=AIManager)
        ai.conversation_manager = cm
        client = _make_client(ai_manager=ai)
        r = client.get(f"/api/v1/ai/conversations/{conv.conversation_id}")
        ConversationSummary(**r.json())

    def test_get_includes_system_prompt(self):
        cm = ConversationManager()
        conv = cm.create(system_prompt="Helpful assistant")
        ai = MagicMock(spec=AIManager)
        ai.conversation_manager = cm
        client = _make_client(ai_manager=ai)
        r = client.get(f"/api/v1/ai/conversations/{conv.conversation_id}")
        assert r.json()["system_prompt"] == "Helpful assistant"


class TestDeleteConversationEndpoint:
    """DELETE /api/v1/ai/conversations/{id}."""

    def test_delete_returns_success(self):
        cm = ConversationManager()
        conv = cm.create()
        ai = MagicMock(spec=AIManager)
        ai.conversation_manager = cm
        client = _make_client(ai_manager=ai)
        r = client.delete(f"/api/v1/ai/conversations/{conv.conversation_id}")
        assert r.status_code == 200
        assert r.json()["status"] == "deleted"

    def test_delete_actually_removes(self):
        cm = ConversationManager()
        conv = cm.create()
        ai = MagicMock(spec=AIManager)
        ai.conversation_manager = cm
        client = _make_client(ai_manager=ai)
        client.delete(f"/api/v1/ai/conversations/{conv.conversation_id}")
        assert cm.get(conv.conversation_id) is None

    def test_delete_returns_404_for_missing(self):
        ai = MagicMock(spec=AIManager)
        ai.conversation_manager = ConversationManager()
        client = _make_client(ai_manager=ai)
        r = client.delete("/api/v1/ai/conversations/nonexistent")
        assert r.status_code == 404


class TestCreateConversationEndpoint:
    """POST /api/v1/ai/conversations."""

    def test_create_returns_conversation_id(self):
        ai = MagicMock(spec=AIManager)
        conv = Conversation(provider="openai", model="gpt-4")
        ai.create_conversation.return_value = conv
        client = _make_client(ai_manager=ai)
        r = client.post(
            "/api/v1/ai/conversations",
            json={"provider": "openai", "model": "gpt-4", "system_prompt": "Be nice"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["id"] == conv.conversation_id
        assert data["provider"] == "openai"

    def test_create_model_validation(self):
        ai = MagicMock(spec=AIManager)
        ai.create_conversation.return_value = Conversation()
        client = _make_client(ai_manager=ai)
        r = client.post(
            "/api/v1/ai/conversations",
            json={"provider": "openai", "model": "gpt-4"},
        )
        ConversationCreateResponse(**r.json())

    def test_create_passes_metadata(self):
        ai = MagicMock(spec=AIManager)
        ai.create_conversation.return_value = Conversation()
        client = _make_client(ai_manager=ai)
        r = client.post(
            "/api/v1/ai/conversations",
            json={"provider": "x", "model": "y", "metadata": {"tag": "test"}},
        )
        assert r.status_code == 200
        assert ai.create_conversation.call_args[1]["metadata"] == {"tag": "test"}

    def test_create_passes_max_messages(self):
        ai = MagicMock(spec=AIManager)
        ai.create_conversation.return_value = Conversation()
        client = _make_client(ai_manager=ai)
        r = client.post(
            "/api/v1/ai/conversations",
            json={"provider": "x", "model": "y", "max_messages": 10},
        )
        assert r.status_code == 200
        assert ai.create_conversation.call_args[1]["max_messages"] == 10


class TestGetConversationMessagesEndpoint:
    """GET /api/v1/ai/conversations/{id}/messages."""

    def test_get_messages_returns_list(self):
        cm = ConversationManager()
        conv = cm.create()
        cm.add_message(conv.conversation_id, "user", "Hello")
        cm.add_message(conv.conversation_id, "assistant", "Hi there")
        ai = MagicMock(spec=AIManager)
        ai.conversation_manager = cm
        client = _make_client(ai_manager=ai)
        r = client.get(
            f"/api/v1/ai/conversations/{conv.conversation_id}/messages",
        )
        assert r.status_code == 200
        data = r.json()
        assert len(data["messages"]) == 2
        assert data["messages"][0]["role"] == "user"
        assert data["messages"][1]["role"] == "assistant"

    def test_get_messages_returns_404_for_missing(self):
        ai = MagicMock(spec=AIManager)
        ai.conversation_manager = ConversationManager()
        client = _make_client(ai_manager=ai)
        r = client.get("/api/v1/ai/conversations/nonexistent/messages")
        assert r.status_code == 404

    def test_get_messages_model_validation(self):
        cm = ConversationManager()
        conv = cm.create()
        cm.add_message(conv.conversation_id, "user", "Hi")
        ai = MagicMock(spec=AIManager)
        ai.conversation_manager = cm
        client = _make_client(ai_manager=ai)
        r = client.get(
            f"/api/v1/ai/conversations/{conv.conversation_id}/messages",
        )
        MessageListResponse(**r.json())

    def test_get_messages_empty_conversation(self):
        cm = ConversationManager()
        conv = cm.create()
        ai = MagicMock(spec=AIManager)
        ai.conversation_manager = cm
        client = _make_client(ai_manager=ai)
        r = client.get(
            f"/api/v1/ai/conversations/{conv.conversation_id}/messages",
        )
        assert len(r.json()["messages"]) == 0

    def test_get_messages_has_timestamps(self):
        cm = ConversationManager()
        conv = cm.create()
        cm.add_message(conv.conversation_id, "user", "Hi")
        ai = MagicMock(spec=AIManager)
        ai.conversation_manager = cm
        client = _make_client(ai_manager=ai)
        r = client.get(
            f"/api/v1/ai/conversations/{conv.conversation_id}/messages",
        )
        assert r.json()["messages"][0]["timestamp"] > 0


# ==========================================================================
# Providers endpoint
# ==========================================================================


class TestListProvidersEndpoint:
    """GET /api/v1/ai/providers."""

    def test_list_providers_returns_list(self):
        ai = MagicMock(spec=AIManager)
        mock_router = MagicMock()
        mock_router.providers = {}
        ai.router = mock_router
        client = _make_client(ai_manager=ai)
        r = client.get("/api/v1/ai/providers")
        assert r.status_code == 200
        ProviderListResponse(**r.json())

    def test_list_providers_sorted(self):
        ai = MagicMock(spec=AIManager)
        mock_router = MagicMock()
        p1 = MagicMock()
        p1._model = "model-a"
        p1.capabilities = frozenset()
        p2 = MagicMock()
        p2._model = "model-b"
        p2.capabilities = frozenset()
        mock_router.providers = {"z_provider": p2, "a_provider": p1}
        ai.router = mock_router
        client = _make_client(ai_manager=ai)
        r = client.get("/api/v1/ai/providers")
        names = [p["name"] for p in r.json()["providers"]]
        assert names == sorted(names)

    def test_list_providers_shows_availability(self):
        ai = MagicMock(spec=AIManager)
        mock_router = MagicMock()
        p = MagicMock()
        p._model = "m"
        p.capabilities = frozenset()
        mock_router.providers = {"test": p}
        mock_router.provider_status.return_value = ProviderStatus.AVAILABLE
        ai.router = mock_router
        client = _make_client(ai_manager=ai)
        r = client.get("/api/v1/ai/providers")
        assert r.json()["providers"][0]["available"] is True

    def test_list_providers_shows_capabilities(self):
        ai = MagicMock(spec=AIManager)
        mock_router = MagicMock()
        from app.ai.providers.base import ProviderCapability

        p = MagicMock()
        p._model = "m"
        p.capabilities = frozenset({ProviderCapability.STREAMING, ProviderCapability.FUNCTION_CALLING})
        mock_router.providers = {"test": p}
        ai.router = mock_router
        client = _make_client(ai_manager=ai)
        r = client.get("/api/v1/ai/providers")
        caps = r.json()["providers"][0]["capabilities"]
        assert "streaming" in caps
        assert "function_calling" in caps


# ==========================================================================
# Models endpoint
# ==========================================================================


class TestListModelsEndpoint:
    """GET /api/v1/ai/models."""

    def test_list_models_returns_list(self):
        ai = MagicMock(spec=AIManager)
        mock_router = MagicMock()
        p1 = MagicMock()
        p1._model = "gpt-4"
        p2 = MagicMock()
        p2._model = "claude-3"
        mock_router.providers = {"openai": p1, "anthropic": p2}
        ai.router = mock_router
        client = _make_client(ai_manager=ai)
        r = client.get("/api/v1/ai/models")
        assert r.status_code == 200
        ModelListResponse(**r.json())

    def test_list_models_skips_empty_model(self):
        ai = MagicMock(spec=AIManager)
        mock_router = MagicMock()
        p = MagicMock()
        p._model = ""
        mock_router.providers = {"empty": p}
        ai.router = mock_router
        client = _make_client(ai_manager=ai)
        r = client.get("/api/v1/ai/models")
        assert len(r.json()["models"]) == 0

    def test_list_models_deduplicates(self):
        ai = MagicMock(spec=AIManager)
        mock_router = MagicMock()
        p = MagicMock()
        p._model = "same-model"
        mock_router.providers = {"p1": p, "p2": p}
        ai.router = mock_router
        client = _make_client(ai_manager=ai)
        r = client.get("/api/v1/ai/models")
        assert len(r.json()["models"]) <= 2

    def test_list_models_sorted(self):
        ai = MagicMock(spec=AIManager)
        mock_router = MagicMock()
        p1 = MagicMock()
        p1._model = "z-model"
        p2 = MagicMock()
        p2._model = "a-model"
        mock_router.providers = {"b_provider": p1, "a_provider": p2}
        ai.router = mock_router
        client = _make_client(ai_manager=ai)
        r = client.get("/api/v1/ai/models")
        names = [m["model"] for m in r.json()["models"]]
        assert names == sorted(names)


# ==========================================================================
# AI schema models validation
# ==========================================================================


class TestAISchemaModels:
    """AI Pydantic model validation."""

    def test_chat_response_model(self):
        m = ChatResponse(response="Hello", provider="p", model="m")
        assert m.response == "Hello"
        assert m.latency_ms == 0.0

    def test_chat_response_with_conversation_id(self):
        m = ChatResponse(
            response="Hi", provider="p", model="m", conversation_id="c-1",
        )
        assert m.conversation_id == "c-1"

    def test_plan_step_model(self):
        s = PlanStepSchema(step=1, action="Act", reasoning="Why")
        assert s.step == 1

    def test_plan_response_model(self):
        steps = [PlanStepSchema(step=1, action="A", reasoning="R")]
        m = PlanResponse(steps=steps, provider="p", model="m")
        assert len(m.steps) == 1
        assert m.valid is True

    def test_reason_step_model(self):
        s = ReasonStepSchema(step=1, statement="S", evidence="E", conclusion="C")
        assert s.statement == "S"

    def test_reason_response_model(self):
        steps = [ReasonStepSchema(step=1, statement="S", evidence="E", conclusion="C")]
        m = ReasonResponse(steps=steps, provider="p", model="m")
        assert len(m.steps) == 1
        assert m.valid is True

    def test_conversation_summary_model(self):
        m = ConversationSummary(id="c1")
        assert m.id == "c1"
        assert m.message_count == 0

    def test_conversation_list_response_model(self):
        c = ConversationSummary(id="c1")
        m = ConversationListResponse(conversations=[c])
        assert len(m.conversations) == 1

    def test_message_response_model(self):
        m = MessageResponse(role="user", content="Hi")
        assert m.content == "Hi"
        assert m.timestamp == 0.0

    def test_message_list_response_model(self):
        msgs = [MessageResponse(role="user", content="Hi")]
        m = MessageListResponse(messages=msgs)
        assert len(m.messages) == 1

    def test_provider_info_model(self):
        m = ProviderInfo(name="openai", model="gpt-4")
        assert m.name == "openai"

    def test_provider_list_response_model(self):
        p = ProviderInfo(name="openai", model="gpt-4")
        m = ProviderListResponse(providers=[p])
        assert len(m.providers) == 1

    def test_model_info_model(self):
        m = ModelInfo(provider="openai", model="gpt-4")
        assert m.provider == "openai"

    def test_model_list_response_model(self):
        m = ModelInfo(provider="openai", model="gpt-4")
        res = ModelListResponse(models=[m])
        assert len(res.models) == 1

    def test_conversation_create_request_model(self):
        from app.api.schemas import ConversationCreateRequest

        m = ConversationCreateRequest()
        assert m.provider == ""
        assert m.model == ""

    def test_conversation_create_response_model(self):
        m = ConversationCreateResponse(
            id="c1", provider="p", model="m", created_at=100.0,
        )
        assert m.id == "c1"

    def test_chat_request_without_prompt_invalid(self):
        from app.api.schemas import ChatRequest

        with pytest.raises(ValueError):
            ChatRequest()

    def test_plan_request_without_objective_invalid(self):
        from app.api.schemas import PlanRequest

        with pytest.raises(ValueError):
            PlanRequest()

    def test_reason_request_without_objective_invalid(self):
        from app.api.schemas import ReasonRequest

        with pytest.raises(ValueError):
            ReasonRequest()

    def test_chat_request_optional_fields(self):
        from app.api.schemas import ChatRequest

        m = ChatRequest(prompt="Hi")
        assert m.provider is None
        assert m.conversation_id is None

    def test_all_ai_models_importable(self):
        from app.api.schemas import (
            ChatRequest,
            ChatResponse,
            ConversationCreateRequest,
            ConversationCreateResponse,
            ConversationListResponse,
            ConversationSummary,
            MessageListResponse,
            MessageResponse,
            ModelInfo,
            ModelListResponse,
            PlanRequest,
            PlanResponse,
            PlanStep,
            ProviderInfo,
            ProviderListResponse,
            ReasonRequest,
            ReasonResponse,
            ReasonStep,
            StreamChunk,
        )
        assert ChatRequest is not None
        assert ChatResponse is not None
        assert ConversationCreateRequest is not None
        assert ConversationCreateResponse is not None
        assert ConversationListResponse is not None
        assert ConversationSummary is not None
        assert MessageListResponse is not None
        assert MessageResponse is not None
        assert ModelInfo is not None
        assert ModelListResponse is not None
        assert PlanRequest is not None
        assert PlanResponse is not None
        assert PlanStep is not None
        assert ProviderInfo is not None
        assert ProviderListResponse is not None
        assert ReasonRequest is not None
        assert ReasonResponse is not None
        assert ReasonStep is not None
        assert StreamChunk is not None


# ==========================================================================
# Route registration
# ==========================================================================


class TestAIConversationRouteRegistration:
    """Conversation sub-routes are registered."""

    def test_conversation_detail_route_exists(self):
        client = _make_client()
        schema = client.get("/api/v1/openapi.json").json()
        paths = schema["paths"]
        conv_id_path = "/api/v1/ai/conversations/{conversation_id}"
        assert conv_id_path in paths
        assert "get" in paths[conv_id_path]
        assert "delete" in paths[conv_id_path]

    def test_conversation_messages_route_exists(self):
        client = _make_client()
        schema = client.get("/api/v1/openapi.json").json()
        path = "/api/v1/ai/conversations/{conversation_id}/messages"
        assert path in schema["paths"]
        assert "get" in schema["paths"][path]

    def test_conversation_post_route_exists(self):
        client = _make_client()
        schema = client.get("/api/v1/openapi.json").json()
        assert "post" in schema["paths"]["/api/v1/ai/conversations"]
