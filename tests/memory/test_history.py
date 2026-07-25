from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.memory.history import MemoryHistory
from app.memory.storage import MemoryStorage

_DATA_DIR = Path("data") / "memory"


def _unique_storage() -> MemoryStorage:
    name = f"test_{uuid.uuid4().hex}.json"
    s = MemoryStorage(name)
    # Pre-populate with sample items
    s.set("items", [
        {"role": "user", "content": "hello", "timestamp": _ts(days=0)},
        {"role": "assistant", "content": "hi there", "timestamp": _ts(days=0)},
        {"role": "user", "content": "weather?", "timestamp": _ts(days=1)},
        {"role": "assistant", "content": "sunny", "timestamp": _ts(days=1)},
        {"role": "user", "content": "old memory", "timestamp": _ts(days=100)},
    ])
    return s


def _ts(*, days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


@pytest.fixture
def history():
    storage = _unique_storage()
    h = MemoryHistory(storage)
    yield h
    path = _DATA_DIR / storage.path.name
    if path.exists():
        path.unlink()


class TestMemoryHistory:
    # ------------------------------------------------------------------
    # get_all
    # ------------------------------------------------------------------

    def test_get_all_returns_all(self, history):
        all_items = history.get_all()
        assert len(all_items) == 5

    def test_get_all_empty(self):
        storage = _unique_storage()
        storage.set("items", [])
        h = MemoryHistory(storage)
        assert h.get_all() == []
        path = _DATA_DIR / storage.path.name
        if path.exists():
            path.unlink()

    # ------------------------------------------------------------------
    # get_recent
    # ------------------------------------------------------------------

    def test_get_recent_default_limit(self, history):
        recent = history.get_recent()
        assert len(recent) == 5

    def test_get_recent_custom_limit(self, history):
        recent = history.get_recent(limit=2)
        assert len(recent) == 2

    def test_get_recent_returns_last_items(self, history):
        recent = history.get_recent(limit=2)
        assert recent[-1]["content"] == "old memory"

    # ------------------------------------------------------------------
    # search
    # ------------------------------------------------------------------

    def test_search_finds_match(self, history):
        results = history.search("hello")
        assert len(results) == 1
        assert results[0]["content"] == "hello"

    def test_search_case_insensitive(self, history):
        results = history.search("HELLO")
        assert len(results) == 1

    def test_search_multiple_matches(self, history):
        results = history.search("sunny")
        assert len(results) >= 1

    def test_search_no_match(self, history):
        assert history.search("zzzzz") == []

    def test_search_empty_query_matches_all(self, history):
        assert len(history.search("")) == 5

    # ------------------------------------------------------------------
    # last_user_message / last_assistant_message
    # ------------------------------------------------------------------

    def test_last_user_message(self, history):
        msg = history.last_user_message()
        assert msg is not None
        assert msg["role"] == "user"
        assert msg["content"] == "old memory"

    def test_last_assistant_message(self, history):
        msg = history.last_assistant_message()
        assert msg is not None
        assert msg["role"] == "assistant"
        assert msg["content"] == "sunny"

    def test_last_user_message_no_users(self):
        storage = _unique_storage()
        storage.set("items", [
            {"role": "assistant", "content": "hello", "timestamp": _ts(days=0)},
        ])
        h = MemoryHistory(storage)
        assert h.last_user_message() is None
        path = _DATA_DIR / storage.path.name
        if path.exists():
            path.unlink()

    # ------------------------------------------------------------------
    # prune
    # ------------------------------------------------------------------

    def test_prune_removes_old_items(self, history):
        removed = history.prune(ttl_days=50)
        assert removed == 1
        assert len(history.get_all()) == 4

    def test_prune_no_items_to_remove(self, history):
        removed = history.prune(ttl_days=200)
        assert removed == 0
        assert len(history.get_all()) == 5

    def test_prune_removes_all_when_all_old(self):
        storage = _unique_storage()
        storage.set("items", [
            {"role": "user", "content": "old1", "timestamp": _ts(days=100)},
            {"role": "user", "content": "old2", "timestamp": _ts(days=200)},
        ])
        h = MemoryHistory(storage)
        removed = h.prune(ttl_days=30)
        assert removed == 2
        assert h.get_all() == []
        path = _DATA_DIR / storage.path.name
        if path.exists():
            path.unlink()

    def test_prune_empty_storage(self):
        storage = _unique_storage()
        storage.set("items", [])
        h = MemoryHistory(storage)
        assert h.prune(ttl_days=30) == 0
        path = _DATA_DIR / storage.path.name
        if path.exists():
            path.unlink()

    def test_prune_persists_to_disk(self, history):
        history.prune(ttl_days=50)
        h2 = MemoryHistory(history.storage)
        assert len(h2.get_all()) == 4
