from __future__ import annotations

import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class ProjectMemory:
    """Per-project memory storage.

    Each project has a unique ID, name, and associated data (notes,
    files, context, etc.). Data is persisted as a single JSON file.
    """

    def __init__(self, filename: str = "projects.json") -> None:
        self.path = Path("data") / "memory" / filename
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._projects: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                self._projects = json.load(f)
        except Exception:
            self._projects = {}

    def save(self) -> None:
        fd, tmp = tempfile.mkstemp(
            dir=str(self.path.parent), prefix=".tmp_", suffix=".json"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self._projects, f, indent=2, ensure_ascii=False)
            os.replace(tmp, str(self.path))
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def create_project(
        self,
        name: str,
        description: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        pid = uuid.uuid4().hex
        self._projects[pid] = {
            "id": pid,
            "name": name,
            "description": description,
            "metadata": metadata or {},
            "notes": [],
            "files": [],
            "created": datetime.now(timezone.utc).isoformat(),
            "updated": datetime.now(timezone.utc).isoformat(),
        }
        self.save()
        return pid

    def get_project(self, project_id: str) -> dict[str, Any] | None:
        return self._projects.get(project_id)

    def list_projects(self) -> list[dict[str, Any]]:
        return list(self._projects.values())

    def delete_project(self, project_id: str) -> bool:
        if project_id in self._projects:
            del self._projects[project_id]
            self.save()
            return True
        return False

    def update_project(
        self,
        project_id: str,
        name: str | None = None,
        description: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        project = self._projects.get(project_id)
        if project is None:
            return None
        if name is not None:
            project["name"] = name
        if description is not None:
            project["description"] = description
        if metadata is not None:
            project["metadata"].update(metadata)
        project["updated"] = datetime.now(timezone.utc).isoformat()
        self.save()
        return project

    def add_note(self, project_id: str, content: str) -> bool:
        project = self._projects.get(project_id)
        if project is None:
            return False
        project["notes"].append({
            "id": uuid.uuid4().hex,
            "content": content,
            "created": datetime.now(timezone.utc).isoformat(),
        })
        project["updated"] = datetime.now(timezone.utc).isoformat()
        self.save()
        return True

    def add_file_ref(self, project_id: str, filepath: str) -> bool:
        project = self._projects.get(project_id)
        if project is None:
            return False
        project["files"].append({
            "path": filepath,
            "added": datetime.now(timezone.utc).isoformat(),
        })
        project["updated"] = datetime.now(timezone.utc).isoformat()
        self.save()
        return True

    def clear(self) -> None:
        self._projects.clear()
        self.save()
