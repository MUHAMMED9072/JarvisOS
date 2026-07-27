"""Tests for the Memory REST API (P11-06)."""

from __future__ import annotations

from unittest.mock import MagicMock, PropertyMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.schemas import (
    MemoryActionResponse,
    MemoryListResponse,
    MemoryRecentResponse,
    MemoryRememberResponse,
    MemorySearchResponse,
    MemorySessionDetailResponse,
    MemorySessionListResponse,
)
from app.api.server import create_app
from app.core.registry import ServiceRegistry
from app.memory.history import MemoryHistory
from app.memory.manager import MemoryManager
from app.memory.session import SessionMemory


@pytest.fixture(autouse=True)
def _fresh_memory():
    """Clear the shared memory file before each test to avoid cross-test pollution."""
    mm = MemoryManager()
    mm.clear()


# ==========================================================================
# Helpers
# ==========================================================================


def _make_app(
    registry: ServiceRegistry | None = None,
    memory_manager: MemoryManager | None = None,
) -> FastAPI:
    if registry is None:
        registry = ServiceRegistry()
    if memory_manager is not None:
        registry.register("memory", memory_manager)
    registry.register("dispatcher", MagicMock())
    registry.register("event_bus", MagicMock())
    return create_app(registry)


def _make_client(
    registry: ServiceRegistry | None = None,
    memory_manager: MemoryManager | None = None,
) -> TestClient:
    app = _make_app(registry, memory_manager)
    return TestClient(app)


# ==========================================================================
# Route registration
# ==========================================================================


class TestMemoryRouteRegistration:
    """Memory routes appear in OpenAPI schema."""

    def test_memory_routes_in_openapi(self):
        mm = MemoryManager()
        client = _make_client(memory_manager=mm)
        schema = client.get("/api/v1/openapi.json").json()
        paths = schema["paths"]
        assert "/api/v1/memory" in paths
        assert "/api/v1/memory/search" in paths
        assert "/api/v1/memory/recent" in paths
        assert "/api/v1/memory/sessions" in paths
        assert "/api/v1/memory/sessions/{session_id}" in paths
        assert "/api/v1/memory/remember" in paths


# ==========================================================================
# List memories
# ==========================================================================


class TestListMemories:
    """GET /api/v1/memory"""

    def test_list_empty(self):
        mm = MemoryManager()
        client = _make_client(memory_manager=mm)
        resp = client.get("/api/v1/memory")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["count"] == 0

    def test_list_with_items(self):
        mm = MemoryManager()
        mm.remember("user", "Hello")
        mm.remember("assistant", "Hi there")
        client = _make_client(memory_manager=mm)
        resp = client.get("/api/v1/memory")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 2
        assert data["items"][0]["role"] == "user"
        assert data["items"][0]["content"] == "Hello"
        assert data["items"][1]["role"] == "assistant"
        assert data["items"][1]["content"] == "Hi there"


# ==========================================================================
# Search
# ==========================================================================


class TestSearchMemories:
    """GET /api/v1/memory/search"""

    def test_search_found(self):
        mm = MemoryManager()
        mm.remember("user", "Hello world")
        mm.remember("user", "Goodbye")
        client = _make_client(memory_manager=mm)
        resp = client.get("/api/v1/memory/search", params={"q": "world"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert data["query"] == "world"
        assert "Hello world" in data["items"][0]["content"]

    def test_search_not_found(self):
        mm = MemoryManager()
        mm.remember("user", "Hello world")
        client = _make_client(memory_manager=mm)
        resp = client.get("/api/v1/memory/search", params={"q": "nonexistent"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 0
        assert data["items"] == []

    def test_search_case_insensitive(self):
        mm = MemoryManager()
        mm.remember("user", "Hello World")
        client = _make_client(memory_manager=mm)
        resp = client.get("/api/v1/memory/search", params={"q": "world"})
        assert resp.status_code == 200
        assert resp.json()["count"] == 1

    def test_search_empty_query(self):
        mm = MemoryManager()
        client = _make_client(memory_manager=mm)
        resp = client.get("/api/v1/memory/search", params={"q": ""})
        assert resp.status_code == 422

    def test_search_missing_query(self):
        mm = MemoryManager()
        client = _make_client(memory_manager=mm)
        resp = client.get("/api/v1/memory/search")
        assert resp.status_code == 422


# ==========================================================================
# Recent
# ==========================================================================


class TestRecentMemories:
    """GET /api/v1/memory/recent"""

    def test_recent_empty(self):
        mm = MemoryManager()
        client = _make_client(memory_manager=mm)
        resp = client.get("/api/v1/memory/recent")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["count"] == 0

    def test_recent_returns_last_n(self):
        mm = MemoryManager()
        for i in range(5):
            mm.remember("user", f"Message {i}")
        client = _make_client(memory_manager=mm)
        resp = client.get("/api/v1/memory/recent", params={"limit": 3})
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 3
        contents = [item["content"] for item in data["items"]]
        assert "Message 2" in contents
        assert "Message 4" in contents

    def test_recent_default_limit(self):
        mm = MemoryManager()
        for i in range(15):
            mm.remember("user", f"Message {i}")
        client = _make_client(memory_manager=mm)
        resp = client.get("/api/v1/memory/recent")
        assert resp.status_code == 200
        assert resp.json()["count"] == 10

    def test_recent_invalid_limit_low(self):
        mm = MemoryManager()
        client = _make_client(memory_manager=mm)
        resp = client.get("/api/v1/memory/recent", params={"limit": 0})
        assert resp.status_code == 422

    def test_recent_invalid_limit_high(self):
        mm = MemoryManager()
        client = _make_client(memory_manager=mm)
        resp = client.get("/api/v1/memory/recent", params={"limit": 200})
        assert resp.status_code == 422


# ==========================================================================
# Remember
# ==========================================================================


class TestRemember:
    """POST /api/v1/memory/remember"""

    def test_remember_user(self):
        mm = MemoryManager()
        client = _make_client(memory_manager=mm)
        resp = client.post(
            "/api/v1/memory/remember",
            json={"role": "user", "content": "Store this"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert len(mm.history.get_all()) == 1

    def test_remember_assistant(self):
        mm = MemoryManager()
        client = _make_client(memory_manager=mm)
        resp = client.post(
            "/api/v1/memory/remember",
            json={"role": "assistant", "content": "Response stored"},
        )
        assert resp.status_code == 200

    def test_remember_with_metadata(self):
        mm = MemoryManager()
        client = _make_client(memory_manager=mm)
        resp = client.post(
            "/api/v1/memory/remember",
            json={
                "role": "user",
                "content": "With metadata",
                "metadata": {"source": "test", "priority": 1},
            },
        )
        assert resp.status_code == 200
        items = mm.history.get_all()
        assert items[0]["metadata"]["source"] == "test"

    def test_remember_invalid_role(self):
        mm = MemoryManager()
        client = _make_client(memory_manager=mm)
        resp = client.post(
            "/api/v1/memory/remember",
            json={"role": "admin", "content": "bad role"},
        )
        assert resp.status_code == 400

    def test_remember_missing_content(self):
        mm = MemoryManager()
        client = _make_client(memory_manager=mm)
        resp = client.post(
            "/api/v1/memory/remember",
            json={"role": "user", "content": ""},
        )
        assert resp.status_code == 422

    def test_remember_empty_content(self):
        mm = MemoryManager()
        client = _make_client(memory_manager=mm)
        resp = client.post(
            "/api/v1/memory/remember",
            json={"role": "user", "content": ""},
        )
        assert resp.status_code == 422


# ==========================================================================
# Sessions
# ==========================================================================


class TestListSessions:
    """GET /api/v1/memory/sessions"""

    def test_list_sessions_empty(self):
        mm = MemoryManager()
        client = _make_client(memory_manager=mm)
        resp = client.get("/api/v1/memory/sessions")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["sessions"]) == 1
        assert data["sessions"][0]["id"] == "current"
        assert data["sessions"][0]["message_count"] == 0

    def test_list_sessions_with_messages(self):
        mm = MemoryManager()
        mm.remember("user", "Hello")
        mm.remember("assistant", "Hi")
        client = _make_client(memory_manager=mm)
        resp = client.get("/api/v1/memory/sessions")
        data = resp.json()
        assert data["sessions"][0]["message_count"] == 2


class TestGetSession:
    """GET /api/v1/memory/sessions/{session_id}"""

    def test_get_current_session(self):
        mm = MemoryManager()
        mm.remember("user", "Session message")
        client = _make_client(memory_manager=mm)
        resp = client.get("/api/v1/memory/sessions/current")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "current"
        assert data["message_count"] >= 1
        assert len(data["messages"]) >= 1

    def test_get_nonexistent_session(self):
        mm = MemoryManager()
        client = _make_client(memory_manager=mm)
        resp = client.get("/api/v1/memory/sessions/nonexistent")
        assert resp.status_code == 404


class TestDeleteSession:
    """DELETE /api/v1/memory/sessions/{session_id}"""

    def test_delete_current(self):
        mm = MemoryManager()
        mm.remember("user", "Will be cleared")
        client = _make_client(memory_manager=mm)
        resp = client.delete("/api/v1/memory/sessions/current")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert mm.get_session_messages() == []

    def test_delete_nonexistent(self):
        mm = MemoryManager()
        client = _make_client(memory_manager=mm)
        resp = client.delete("/api/v1/memory/sessions/nonexistent")
        assert resp.status_code == 404


# ==========================================================================
# Clear all memory
# ==========================================================================


class TestClearMemory:
    """DELETE /api/v1/memory"""

    def test_clear_empty(self):
        mm = MemoryManager()
        client = _make_client(memory_manager=mm)
        resp = client.delete("/api/v1/memory")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

    def test_clear_with_data(self):
        mm = MemoryManager()
        mm.remember("user", "Will be cleared")
        mm.remember("assistant", "Also cleared")
        client = _make_client(memory_manager=mm)
        resp = client.delete("/api/v1/memory")
        assert resp.status_code == 200
        assert mm.history.get_all() == []
        assert mm.get_session_messages() == []


# ==========================================================================
# Error handling
# ==========================================================================


class TestMemoryErrorHandling:
    """Verify proper error status codes."""

    def test_service_unavailable(self):
        registry = ServiceRegistry()
        registry.register("dispatcher", MagicMock())
        registry.register("event_bus", MagicMock())
        client = TestClient(create_app(registry))
        resp = client.get("/api/v1/memory")
        assert resp.status_code == 503

    def test_validation_on_remember_bad_role(self):
        mm = MemoryManager()
        client = _make_client(memory_manager=mm)
        resp = client.post(
            "/api/v1/memory/remember",
            json={"role": "", "content": "test"},
        )
        assert resp.status_code == 400


# ==========================================================================
# Response model shapes
# ==========================================================================


class TestMemoryResponseShapes:
    """Verify response payloads match expected Pydantic models."""

    def test_list_response_shape(self):
        mm = MemoryManager()
        mm.remember("user", "test")
        client = _make_client(memory_manager=mm)
        resp = client.get("/api/v1/memory")
        data = resp.json()
        for field in ("items", "count"):
            assert field in data, f"Missing field: {field}"
        for field in ("role", "content", "metadata", "timestamp"):
            assert field in data["items"][0], f"Missing field: {field}"

    def test_search_response_shape(self):
        mm = MemoryManager()
        mm.remember("user", "searchable content")
        client = _make_client(memory_manager=mm)
        resp = client.get("/api/v1/memory/search", params={"q": "searchable"})
        data = resp.json()
        for field in ("query", "items", "count"):
            assert field in data, f"Missing field: {field}"

    def test_recent_response_shape(self):
        mm = MemoryManager()
        mm.remember("user", "recent item")
        client = _make_client(memory_manager=mm)
        resp = client.get("/api/v1/memory/recent")
        data = resp.json()
        for field in ("items", "count"):
            assert field in data, f"Missing field: {field}"

    def test_session_list_response_shape(self):
        mm = MemoryManager()
        client = _make_client(memory_manager=mm)
        resp = client.get("/api/v1/memory/sessions")
        data = resp.json()
        for field in ("sessions",):
            assert field in data, f"Missing field: {field}"
        for field in ("id", "message_count", "last_intent", "last_application", "last_skill"):
            assert field in data["sessions"][0], f"Missing field: {field}"

    def test_session_detail_response_shape(self):
        mm = MemoryManager()
        client = _make_client(memory_manager=mm)
        resp = client.get("/api/v1/memory/sessions/current")
        data = resp.json()
        for field in ("id", "messages", "last_intent", "last_entities",
                      "last_application", "last_skill", "message_count"):
            assert field in data, f"Missing field: {field}"

    def test_action_response_shape(self):
        mm = MemoryManager()
        client = _make_client(memory_manager=mm)
        resp = client.delete("/api/v1/memory")
        data = resp.json()
        for field in ("status", "message"):
            assert field in data, f"Missing field: {field}"
