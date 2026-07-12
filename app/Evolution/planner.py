"""
JARVIS Evolution Engine - Planner
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import json
from pathlib import Path


@dataclass
class UpgradeTask:
    priority: int
    title: str
    description: str
    completed: bool = False


class EvolutionPlanner:
    def __init__(self, file: str = "data/evolution_plan.json") -> None:
        self.path = Path(file)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("[]", encoding="utf-8")

    def _load(self):
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _save(self, data):
        self.path.write_text(json.dumps(data, indent=4), encoding="utf-8")

    def add_task(self, priority: int, title: str, description: str):
        tasks = self._load()
        tasks.append({
            "priority": priority,
            "title": title,
            "description": description,
            "completed": False,
            "created": datetime.now().isoformat(timespec="seconds")
        })
        tasks.sort(key=lambda t: t["priority"])
        self._save(tasks)

    def pending(self):
        return [t for t in self._load() if not t["completed"]]

    def complete(self, title: str):
        tasks = self._load()
        for t in tasks:
            if t["title"] == title:
                t["completed"] = True
        self._save(tasks)


if __name__ == "__main__":
    planner = EvolutionPlanner()
    print(planner.pending())
