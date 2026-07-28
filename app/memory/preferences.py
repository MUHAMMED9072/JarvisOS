from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


class UserPreferences:
    """User preference storage with JSON persistence."""

    def __init__(self, filename: str = "preferences.json") -> None:
        self.path = Path("data") / "memory" / filename
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._prefs: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                self._prefs = json.load(f)
        except Exception:
            self._prefs = {}

    def save(self) -> None:
        fd, tmp = tempfile.mkstemp(
            dir=str(self.path.parent), prefix=".tmp_", suffix=".json"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self._prefs, f, indent=2, ensure_ascii=False)
            os.replace(tmp, str(self.path))
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def get(self, key: str, default: Any = None) -> Any:
        return self._prefs.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._prefs[key] = value
        self.save()

    def delete(self, key: str) -> bool:
        if key in self._prefs:
            del self._prefs[key]
            self.save()
            return True
        return False

    def all(self) -> dict[str, Any]:
        return dict(self._prefs)

    def clear(self) -> None:
        self._prefs.clear()
        self.save()
