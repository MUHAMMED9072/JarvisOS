from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from app.memory.manager import MemoryManager

_DATA_DIR = Path("data") / "memory"


def _unique_marker() -> str:
    return uuid.uuid4().hex


@pytest.fixture
def manager():
    m = MemoryManager()
    # Use a unique filename to avoid collisions
    unique = _unique_marker()
    m.storage.path = _DATA_DIR / f"test_manager_{unique}.json"
    m.storage.save({})
    yield m
    path = m.storage.path
    if path.exists():
        path.unlink()


class TestMemoryManager:
    # ------------------------------------------------------------------
    # remember / get_session_messages
    # ------------------------------------------------------------------

    def test_remember_adds_to_session(self, manager):
        manager.remember("user", "hello")
        msgs = manager.get_session_messages()
        assert len(msgs) == 1
        assert msgs[0]["role"] == "user"
        assert msgs[0]["content"] == "hello"

    def test_remember_adds_to_history(self, manager):
        manager.remember("user", "stored")
        all_items = manager.history.get_all()
        assert any(it["content"] == "stored" for it in all_items)

    def test_remember_with_metadata(self, manager):
        manager.remember("assistant", "response", metadata={"source": "ai"})
        all_items = manager.history.get_all()
        entry = next(it for it in all_items if it["content"] == "response")
        assert entry["metadata"]["source"] == "ai"

    # ------------------------------------------------------------------
    # get_recent
    # ------------------------------------------------------------------

    def test_get_recent_empty(self, manager):
        assert manager.get_recent() == []

    def test_get_recent_after_remember(self, manager):
        manager.remember("user", "first")
        manager.remember("user", "second")
        recent = manager.get_recent(limit=1)
        assert len(recent) == 1
        assert recent[0]["content"] == "second"

    # ------------------------------------------------------------------
    # search
    # ------------------------------------------------------------------

    def test_search_no_results(self, manager):
        manager.remember("user", "hello world")
        results = manager.search("goodbye")
        assert results == []

    def test_search_finds_match(self, manager):
        manager.remember("user", "hello world")
        results = manager.search("hello")
        assert len(results) == 1

    # ------------------------------------------------------------------
    # get_session_messages
    # ------------------------------------------------------------------

    def test_get_session_messages_empty_initial(self, manager):
        assert manager.get_session_messages() == []

    def test_get_session_messages_returns_recent(self, manager):
        manager.remember("user", "q1")
        manager.remember("assistant", "a1")
        msgs = manager.get_session_messages()
        assert len(msgs) == 2
        assert msgs[0]["role"] == "user"
        assert msgs[1]["role"] == "assistant"

    # ------------------------------------------------------------------
    # set_context
    # ------------------------------------------------------------------

    def test_set_context_updates_session(self, manager):
        manager.set_context(intent="test_intent", skill="test_skill")
        assert manager.session.last_intent == "test_intent"
        assert manager.session.last_skill == "test_skill"

    # ------------------------------------------------------------------
    # get_last_application
    # ------------------------------------------------------------------

    def test_get_last_application_from_session(self, manager):
        manager.set_context(entities={"application": "notepad"})
        assert manager.get_last_application() == "notepad"

    def test_get_last_application_from_history(self, manager):
        manager.remember(
            "user", "open calc",
            metadata={"entities": {"application": "calculator"}},
        )
        assert manager.get_last_application() == "calculator"

    def test_get_last_application_none(self, manager):
        assert manager.get_last_application() is None

    # ------------------------------------------------------------------
    # prune_all
    # ------------------------------------------------------------------

    def test_prune_all_removes_old(self, manager):
        manager.remember("user", "current")
        manager.history.storage.set("items", [
            {"role": "user", "content": "old", "timestamp": "2000-01-01T00:00:00"},
            {"role": "user", "content": "current", "timestamp": "2026-07-24T00:00:00"},
        ])
        removed = manager.prune_all(ttl_days=30)
        # The "old" item is from 2000 — should be removed
        # The "current" item is from 2026 — should be kept
        assert removed == 1
        remaining = manager.history.get_all()
        assert all(it["content"] != "old" for it in remaining)

    # ------------------------------------------------------------------
    # clear
    # ------------------------------------------------------------------

    def test_clear_empties_session(self, manager):
        manager.remember("user", "hello")
        manager.clear()
        assert manager.get_session_messages() == []

    def test_clear_empties_history(self, manager):
        manager.remember("user", "hello")
        manager.clear()
        assert manager.history.get_all() == []
