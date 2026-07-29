from __future__ import annotations

import io
import json
import shutil
import tarfile
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from app.agents.base import Agent, AgentStatus
from app.agents.registry import AgentRegistry


class ArchivalEvent:
    ARCHIVED = "agent.archival.archived"
    DELETED = "agent.archival.deleted"
    RESTORED = "agent.archival.restored"
    ERROR = "agent.archival.error"


@dataclass
class ArchiveEntry:
    agent_id: str = ""
    name: str = ""
    version: str = ""
    agent_type: str = ""
    description: str = ""
    archived_at: float = 0.0
    file_size: int = 0
    retention_until: float = 0.0
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "version": self.version,
            "agent_type": self.agent_type,
            "description": self.description,
            "archived_at": self.archived_at,
            "file_size": self.file_size,
            "retention_until": self.retention_until,
            "tags": list(self.tags),
        }


class ArchiveManager:
    """Compresses, lists, searches, and manages agent archives with retention."""

    ARCHIVE_EXT = ".tar.gz"

    def __init__(
        self,
        archive_dir: str = "",
        registry: AgentRegistry | None = None,
        event_callback: Callable[[str, dict[str, Any]], None] | None = None,
        default_retention_days: int = 365,
    ) -> None:
        self._archive_dir = Path(archive_dir or "data/agent_archives")
        self._archive_dir.mkdir(parents=True, exist_ok=True)
        self._registry = registry
        self._event_callback = event_callback
        self._default_retention_days = default_retention_days
        self._lock = threading.RLock()
        self._index_file = self._archive_dir / "archive_index.json"
        self._index: dict[str, ArchiveEntry] = {}
        self._load_index()

    def archive_agent(
        self,
        agent: Agent,
        source_dir: str = "",
        retention_days: int = 0,
    ) -> str:
        """Archive an agent into a compressed tar.gz file.

        Returns the archive filename.
        """
        if retention_days <= 0:
            retention_days = self._default_retention_days

        agent_id = agent.agent_id or agent.metadata.name
        now = time.time()
        archive_name = f"{agent_id}_{int(now)}{self.ARCHIVE_EXT}"
        archive_path = self._archive_dir / archive_name

        metadata = {
            "agent_id": agent_id,
            "name": agent.metadata.name,
            "version": agent.metadata.version,
            "agent_type": agent.agent_type,
            "description": agent.metadata.description,
            "capabilities": [c.to_dict() for c in agent.metadata.capabilities],
            "dependencies": list(agent.metadata.dependencies),
            "owner": agent.metadata.owner,
            "tags": list(agent.metadata.tags),
            "archived_at": now,
            "retention_days": retention_days,
        }

        with tarfile.open(archive_path, "w:gz") as tar:
            metadata_bytes = json.dumps(metadata, indent=2).encode("utf-8")
            info = tarfile.TarInfo(name="metadata.json")
            info.size = len(metadata_bytes)
            tar.addfile(info, io.BytesIO(metadata_bytes))

            if source_dir:
                src = Path(source_dir)
                if src.exists():
                    tar.add(str(src), arcname="agent_data", recursive=True)

        file_size = archive_path.stat().st_size

        entry = ArchiveEntry(
            agent_id=agent_id,
            name=agent.metadata.name,
            version=agent.metadata.version,
            agent_type=agent.agent_type,
            description=agent.metadata.description,
            archived_at=now,
            file_size=file_size,
            retention_until=now + retention_days * 86400,
            tags=list(agent.metadata.tags),
        )

        with self._lock:
            self._index[archive_name] = entry
            self._save_index()

        if self._registry:
            try:
                self._registry.update_status(agent_id, AgentStatus.ARCHIVED)
            except Exception:
                pass

        self._publish(ArchivalEvent.ARCHIVED, entry.to_dict())

        return archive_name

    def list_archives(
        self,
        query: str = "",
        agent_type: str = "",
        limit: int = 100,
    ) -> list[ArchiveEntry]:
        with self._lock:
            entries = list(self._index.values())
            if query:
                q = query.lower()
                entries = [
                    e for e in entries
                    if q in e.name.lower() or q in e.description.lower() or q in e.agent_id.lower()
                ]
            if agent_type:
                entries = [e for e in entries if e.agent_type == agent_type]
            entries.sort(key=lambda e: e.archived_at, reverse=True)
            return entries[:limit]

    def search_archives(
        self,
        query: str = "",
        capabilities: list[str] | None = None,
        date_from: float = 0.0,
        date_to: float = 0.0,
    ) -> list[ArchiveEntry]:
        results = self.list_archives(query=query)
        if capabilities:
            results = [
                e for e in results
                if any(c in e.tags for c in capabilities)
            ]
        if date_from > 0:
            results = [e for e in results if e.archived_at >= date_from]
        if date_to > 0:
            results = [e for e in results if e.archived_at <= date_to]
        return results

    def delete_archive(self, archive_name: str) -> bool:
        archive_path = self._archive_dir / archive_name
        with self._lock:
            if archive_name in self._index:
                del self._index[archive_name]
                self._save_index()
            if archive_path.exists():
                archive_path.unlink()
                self._publish(ArchivalEvent.DELETED, {"archive": archive_name})
                return True
        return False

    def apply_retention_policy(self) -> int:
        """Remove archives past their retention date. Returns count removed."""
        now = time.time()
        to_delete: list[str] = []
        with self._lock:
            for name, entry in list(self._index.items()):
                if entry.retention_until > 0 and now > entry.retention_until:
                    to_delete.append(name)
        count = 0
        for name in to_delete:
            if self.delete_archive(name):
                count += 1
        return count

    def get_archive_path(self, archive_name: str) -> Path | None:
        archive_path = self._archive_dir / archive_name
        return archive_path if archive_path.exists() else None

    def _load_index(self) -> None:
        if not self._index_file.exists():
            return
        try:
            data = json.loads(self._index_file.read_text(encoding="utf-8"))
            for entry_data in data.get("archives", []):
                e = ArchiveEntry(**entry_data)
                self._index[entry_data.get("_key", f"{e.agent_id}_{int(e.archived_at)}")] = e
        except Exception:
            pass

    def _save_index(self) -> None:
        try:
            data = {
                "updated_at": time.time(),
                "archives": [
                    {**e.to_dict(), "_key": k}
                    for k, e in self._index.items()
                ],
            }
            self._index_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _publish(self, event: str, data: dict[str, Any]) -> None:
        if self._event_callback:
            try:
                self._event_callback(event, data)
            except Exception:
                pass

    def health(self) -> dict[str, Any]:
        return {
            "alive": True,
            "archive_dir": str(self._archive_dir),
            "archives_count": len(self._index),
            "default_retention_days": self._default_retention_days,
        }



