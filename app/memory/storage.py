from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


class MemoryStorage:
    """JSON file-backed persistent key-value store.

    Implements an in-memory write-through cache so that repeated
    ``get()`` / ``set()`` calls in the same process avoid re-reading
    the file from disk.  Writes use an atomic temp-file + rename
    pattern to prevent corruption on crash.
    """

    def __init__(self, filename: str) -> None:
        self.path = Path("data") / "memory" / filename
        self.path.parent.mkdir(parents=True, exist_ok=True)

        self._cache: dict | None = None

        if not self.path.exists():
            self.save({})

    # ------------------------------------------------------------------
    # Load / save
    # ------------------------------------------------------------------

    def load(self) -> dict:
        if self._cache is not None:
            return self._cache
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                self._cache = json.load(f)
        except Exception:
            self._cache = {}
        return self._cache

    def save(self, data: dict) -> None:
        self._cache = data
        fd, tmp_path = tempfile.mkstemp(
            dir=str(self.path.parent),
            prefix=".tmp_",
            suffix=".json",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            os.replace(tmp_path, str(self.path))
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    # ------------------------------------------------------------------
    # Dict-like API
    # ------------------------------------------------------------------

    def get(self, key: str, default=None):
        return self.load().get(key, default)

    def set(self, key: str, value) -> None:
        data = self.load()
        data[key] = value
        self.save(data)

    def delete(self, key: str) -> None:
        data = self.load()
        if key in data:
            del data[key]
            self.save(data)

    def clear(self) -> None:
        self.save({})
