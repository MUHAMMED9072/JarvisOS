from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from app.memory.preferences import UserPreferences

_DATA_DIR = Path("data") / "memory"


@pytest.fixture
def prefs():
    name = f"test_prefs_{uuid.uuid4().hex}.json"
    p = UserPreferences(filename=name)
    yield p
    path = _DATA_DIR / name
    if path.exists():
        path.unlink()


class TestUserPreferences:
    def test_get_default(self, prefs):
        assert prefs.get("nonexistent") is None

    def test_get_default_value(self, prefs):
        assert prefs.get("nonexistent", "default") == "default"

    def test_set_and_get(self, prefs):
        prefs.set("theme", "dark")
        assert prefs.get("theme") == "dark"

    def test_set_overwrites(self, prefs):
        prefs.set("key", "old")
        prefs.set("key", "new")
        assert prefs.get("key") == "new"

    def test_delete_existing(self, prefs):
        prefs.set("key", "value")
        assert prefs.delete("key") is True
        assert prefs.get("key") is None

    def test_delete_missing(self, prefs):
        assert prefs.delete("nonexistent") is False

    def test_all(self, prefs):
        prefs.set("a", 1)
        prefs.set("b", 2)
        all_prefs = prefs.all()
        assert all_prefs == {"a": 1, "b": 2}

    def test_all_is_copy(self, prefs):
        prefs.set("a", 1)
        all_prefs = prefs.all()
        all_prefs["a"] = 99
        assert prefs.get("a") == 1

    def test_clear(self, prefs):
        prefs.set("a", 1)
        prefs.set("b", 2)
        prefs.clear()
        assert prefs.all() == {}

    def test_persistence(self, prefs):
        prefs.set("theme", "dark")
        p2 = UserPreferences(filename=prefs.path.name)
        assert p2.get("theme") == "dark"

    def test_stores_various_types(self, prefs):
        prefs.set("string", "value")
        prefs.set("int", 42)
        prefs.set("float", 3.14)
        prefs.set("list", [1, 2, 3])
        prefs.set("dict", {"a": 1})
        assert prefs.get("string") == "value"
        assert prefs.get("int") == 42
        assert prefs.get("float") == 3.14
        assert prefs.get("list") == [1, 2, 3]
        assert prefs.get("dict") == {"a": 1}
