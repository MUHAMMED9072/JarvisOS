from __future__ import annotations

from unittest.mock import MagicMock, PropertyMock

import pytest

from app.gui.controllers.memory_controller import (
    MemoryController,
    MemoryStats,
    SearchResult,
)


class TestMemoryController:
    @pytest.fixture
    def memory_manager(self):
        mgr = MagicMock()
        mgr.history.get_all.return_value = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ]
        mgr.get_session_messages.return_value = [
            {"role": "user", "content": "question"},
            {"role": "assistant", "content": "answer"},
        ]
        mgr.get_last_application.return_value = "notepad"
        mgr.storage.get.return_value = {"theme": "dark"}
        mgr.search.return_value = [
            MagicMock(content="found item", role="assistant", timestamp=100.0),
        ]
        return mgr

    @pytest.fixture
    def registry(self, memory_manager):
        r = MagicMock()
        r.get.side_effect = lambda name: {
            "memory": memory_manager,
        }[name]
        return r

    @pytest.fixture
    def controller(self, registry):
        return MemoryController(registry)

    # ------------------------------------------------------------------
    # Session messages
    # ------------------------------------------------------------------

    def test_get_session_messages(self, controller):
        msgs = controller.get_session_messages()
        assert len(msgs) == 2
        assert msgs[0]["role"] == "user"

    def test_get_session_messages_empty(self, controller):
        controller.registry.get("memory").get_session_messages.return_value = []
        assert controller.get_session_messages() == []

    def test_get_session_context(self, controller):
        ctx = controller.get_session_context()
        assert "messages" in ctx

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def test_search_memories_returns_results(self, controller):
        results = controller.search_memories("query")
        assert len(results) == 1
        assert isinstance(results[0], SearchResult)
        assert results[0].content == "found item"

    def test_search_memories_empty_query(self, controller):
        assert controller.search_memories("") == []

    def test_search_memories_whitespace(self, controller):
        assert controller.search_memories("   ") == []

    def test_search_memories_no_results(self, controller):
        controller.registry.get("memory").search.return_value = []
        assert controller.search_memories("query") == []

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    def test_get_statistics_type(self, controller):
        stats = controller.get_statistics()
        assert isinstance(stats, MemoryStats)

    def test_get_statistics_values(self, controller):
        stats = controller.get_statistics()
        assert stats.total_items == 2
        assert stats.session_messages == 2
        assert stats.last_application == "notepad"

    def test_get_statistics_empty(self, controller):
        mgr = controller.registry.get("memory")
        mgr.history.get_all.return_value = []
        mgr.get_session_messages.return_value = []
        mgr.get_last_application.return_value = None
        stats = controller.get_statistics()
        assert stats.total_items == 0
        assert stats.session_messages == 0
        assert stats.last_application is None

    # ------------------------------------------------------------------
    # Preferences
    # ------------------------------------------------------------------

    def test_get_preferences(self, controller):
        prefs = controller.get_preferences()
        assert prefs == {"theme": "dark"}

    def test_get_preferences_empty(self, controller):
        controller.registry.get("memory").storage.get.return_value = {}
        assert controller.get_preferences() == {}

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def test_clear_session_calls_memory_session_clear(self, controller):
        controller.clear_session()
        controller.registry.get("memory").session.clear.assert_called_once()

    def test_clear_all_calls_memory_clear(self, controller):
        controller.clear_all()
        controller.registry.get("memory").clear.assert_called_once()
