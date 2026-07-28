from __future__ import annotations

import json
import os
import tempfile
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class ContextManager:
    """Manages conversation and application context with persistence."""

    def __init__(self, filename: str = "context.json") -> None:
        self.path = Path("data") / "memory" / filename
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._context: dict[str, Any] = {
            "current_intent": None,
            "current_skill": None,
            "current_entities": {},
            "recent_applications": [],
            "active_tasks": [],
            "history": [],
        }
        self._history: deque[dict[str, Any]] = deque(maxlen=50)
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._context.update(data.get("context", {}))
            for h in data.get("history", []):
                self._history.append(h)
        except Exception:
            pass

    def save(self) -> None:
        data = {
            "context": self._context,
            "history": list(self._history),
        }
        fd, tmp = tempfile.mkstemp(
            dir=str(self.path.parent), prefix=".tmp_", suffix=".json"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(tmp, str(self.path))
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def set_intent(self, intent: str) -> None:
        self._context["current_intent"] = intent
        self._add_to_history("intent", intent)
        self.save()

    def get_intent(self) -> str | None:
        return self._context.get("current_intent")

    def set_skill(self, skill: str) -> None:
        self._context["current_skill"] = skill
        self._add_to_history("skill", skill)
        self.save()

    def get_skill(self) -> str | None:
        return self._context.get("current_skill")

    def set_entities(self, entities: dict[str, Any]) -> None:
        self._context["current_entities"] = entities
        self._add_to_history("entities", entities)
        self.save()

    def get_entities(self) -> dict[str, Any]:
        return dict(self._context.get("current_entities", {}))

    def track_application(self, app_name: str) -> None:
        recent = self._context.setdefault("recent_applications", [])
        if app_name in recent:
            recent.remove(app_name)
        recent.append(app_name)
        if len(recent) > 20:
            recent[:] = recent[-20:]
        self._add_to_history("application", app_name)
        self.save()

    def get_recent_applications(self, limit: int = 5) -> list[str]:
        return list(self._context.get("recent_applications", []))[-limit:]

    def add_task(self, task: str) -> None:
        tasks = self._context.setdefault("active_tasks", [])
        if task not in tasks:
            tasks.append(task)
            self.save()

    def remove_task(self, task: str) -> bool:
        tasks = self._context.setdefault("active_tasks", [])
        if task in tasks:
            tasks.remove(task)
            self.save()
            return True
        return False

    def get_active_tasks(self) -> list[str]:
        return list(self._context.get("active_tasks", []))

    def _add_to_history(self, key: str, value: Any) -> None:
        self._history.append({
            "key": key,
            "value": value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def get_history(self, limit: int = 10) -> list[dict[str, Any]]:
        return list(self._history)[-limit:]

    def clear(self) -> None:
        self._context = {
            "current_intent": None,
            "current_skill": None,
            "current_entities": {},
            "recent_applications": [],
            "active_tasks": [],
            "history": [],
        }
        self._history.clear()
        self.save()
