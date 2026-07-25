from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

import pytest

from app.memory.storage import MemoryStorage

_DATA_DIR = Path("data") / "memory"


def _unique_path() -> str:
    return f"test_{uuid.uuid4().hex}.json"


@pytest.fixture
def storage():
    name = _unique_path()
    s = MemoryStorage(name)
    yield s
    path = _DATA_DIR / name
    if path.exists():
        path.unlink()
    # Also clean up any orphaned temp files
    for p in _DATA_DIR.glob(f".tmp_*{name}"):
        p.unlink()


class TestMemoryStorage:
    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def test_init_creates_file(self):
        name = _unique_path()
        s = MemoryStorage(name)
        assert (_DATA_DIR / name).exists()
        (_DATA_DIR / name).unlink()

    def test_init_creates_valid_json(self):
        name = _unique_path()
        s = MemoryStorage(name)
        with open(_DATA_DIR / name, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data == {}
        (_DATA_DIR / name).unlink()

    def test_init_existing_file_not_overwritten(self, storage):
        storage.set("key", "val")
        s2 = MemoryStorage(storage.path.name)
        assert s2.get("key") == "val"
        # Cleanup s2's path (same file, only clean once)
        s2.path.unlink()

    # ------------------------------------------------------------------
    # Cache: load() is called once, cached thereafter
    # ------------------------------------------------------------------

    def test_cache_returns_same_dict_on_repeated_load(self, storage):
        d1 = storage.load()
        d2 = storage.load()
        assert d1 is d2

    def test_cache_invalidated_after_save(self, storage):
        d1 = storage.load()
        storage.set("a", 1)
        d2 = storage.load()
        assert d2["a"] == 1

    # ------------------------------------------------------------------
    # get
    # ------------------------------------------------------------------

    def test_get_default(self, storage):
        assert storage.get("nonexistent") is None

    def test_get_custom_default(self, storage):
        assert storage.get("nonexistent", 42) == 42

    def test_get_after_set(self, storage):
        storage.set("name", "Jarvis")
        assert storage.get("name") == "Jarvis"

    # ------------------------------------------------------------------
    # set
    # ------------------------------------------------------------------

    def test_set_overwrites(self, storage):
        storage.set("x", 1)
        storage.set("x", 2)
        assert storage.get("x") == 2

    def test_set_persists_to_disk(self, storage):
        storage.set("persist", "yes")
        s2 = MemoryStorage(storage.path.name)
        assert s2.get("persist") == "yes"
        s2.path.unlink()

    # ------------------------------------------------------------------
    # delete
    # ------------------------------------------------------------------

    def test_delete_existing_key(self, storage):
        storage.set("x", 1)
        storage.delete("x")
        assert storage.get("x") is None

    def test_delete_nonexistent_key(self, storage):
        storage.delete("nonexistent")

    def test_delete_removes_from_disk(self, storage):
        storage.set("x", 1)
        storage.delete("x")
        s2 = MemoryStorage(storage.path.name)
        assert s2.get("x") is None
        s2.path.unlink()

    # ------------------------------------------------------------------
    # clear
    # ------------------------------------------------------------------

    def test_clear_empties_data(self, storage):
        storage.set("a", 1)
        storage.set("b", 2)
        storage.clear()
        assert storage.get("a") is None
        assert storage.get("b") is None

    def test_clear_persists_to_disk(self, storage):
        storage.set("a", 1)
        storage.clear()
        s2 = MemoryStorage(storage.path.name)
        assert s2.load() == {}
        s2.path.unlink()

    # ------------------------------------------------------------------
    # Atomic write — temp file removed after successful save
    # ------------------------------------------------------------------

    def test_no_orphan_temp_after_save(self, storage):
        storage.set("a", 1)
        temps = list(Path("data/memory").glob(f".tmp_*{storage.path.name}"))
        assert len(temps) == 0

    def test_save_replaces_content(self, storage):
        storage.set("original", "value")
        storage.save({"replaced": True})
        assert storage.get("original") is None
        assert storage.get("replaced") is True
