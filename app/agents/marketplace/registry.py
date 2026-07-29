from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.request import Request, urlopen


class RegistryError(Exception):
    pass


@dataclass
class RemoteRepository:
    url: str = ""
    name: str = ""
    enabled: bool = True
    last_sync: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "name": self.name,
            "enabled": self.enabled,
            "last_sync": self.last_sync,
        }


@dataclass
class MarketplaceEntry:
    package_name: str = ""
    version: str = ""
    description: str = ""
    agent_type: str = ""
    capabilities: list[str] = field(default_factory=list)
    published_at: float = 0.0
    source: str = "local"
    source_url: str = ""
    file_size: int = 0
    checksum: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "package_name": self.package_name,
            "version": self.version,
            "description": self.description,
            "agent_type": self.agent_type,
            "capabilities": list(self.capabilities),
            "published_at": self.published_at,
            "source": self.source,
            "source_url": self.source_url,
            "file_size": self.file_size,
            "checksum": self.checksum,
        }


class MarketplaceRegistry:
    """Local index of available agent packages.

    Maintains entries for both locally exported packages and
    packages fetched from remote repositories.
    """

    def __init__(self, storage_path: str = "") -> None:
        self._lock = threading.RLock()
        self._entries: dict[str, MarketplaceEntry] = {}
        self._repositories: dict[str, RemoteRepository] = {}
        self._storage_path = Path(storage_path or os.path.join("data", "marketplace"))
        self._storage_path.mkdir(parents=True, exist_ok=True)
        self._index_file = self._storage_path / "index.json"
        self._load_index()

    def register(self, entry: MarketplaceEntry) -> str:
        key = f"{entry.package_name}:{entry.version}"
        with self._lock:
            self._entries[key] = entry
            self._save_index()
        return key

    def get(self, package_name: str, version: str = "") -> MarketplaceEntry | None:
        with self._lock:
            if version:
                return self._entries.get(f"{package_name}:{version}")
            candidates = [e for k, e in self._entries.items() if k.startswith(f"{package_name}:")]
            if not candidates:
                return None
            return max(candidates, key=lambda e: (e.published_at, e.version))

    def search(self, query: str = "") -> list[MarketplaceEntry]:
        q = query.lower()
        with self._lock:
            if not q:
                return list(self._entries.values())
            return [
                e for e in self._entries.values()
                if q in e.package_name.lower() or q in e.description.lower()
            ]

    def list_by_type(self, agent_type: str) -> list[MarketplaceEntry]:
        with self._lock:
            return [e for e in self._entries.values() if e.agent_type == agent_type]

    def remove(self, package_name: str, version: str = "") -> bool:
        with self._lock:
            if version:
                key = f"{package_name}:{version}"
                if key in self._entries:
                    del self._entries[key]
                    self._save_index()
                    return True
                return False
            keys = [k for k in self._entries if k.startswith(f"{package_name}:")]
            if not keys:
                return False
            for k in keys:
                del self._entries[k]
            self._save_index()
            return True

    def add_repository(self, repo: RemoteRepository) -> None:
        with self._lock:
            self._repositories[repo.url] = repo

    def remove_repository(self, url: str) -> bool:
        with self._lock:
            if url in self._repositories:
                del self._repositories[url]
                return True
            return False

    def list_repositories(self) -> list[RemoteRepository]:
        with self._lock:
            return list(self._repositories.values())

    def sync_repository(self, url: str) -> int:
        """Fetch package index from a remote repository and update local entries."""
        with self._lock:
            repo = self._repositories.get(url)
            if repo is None:
                raise RegistryError(f"Repository not registered: {url}")

        try:
            req = Request(f"{url.rstrip('/')}/index.json")
            with urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            count = 0
            for entry_data in data.get("packages", []):
                entry = MarketplaceEntry(
                    package_name=entry_data.get("package_name", ""),
                    version=entry_data.get("version", ""),
                    description=entry_data.get("description", ""),
                    agent_type=entry_data.get("agent_type", ""),
                    capabilities=entry_data.get("capabilities", []),
                    published_at=entry_data.get("published_at", time.time()),
                    source="remote",
                    source_url=f"{url}/packages/{entry_data.get('package_name')}.jarvis-agent",
                    file_size=entry_data.get("file_size", 0),
                    checksum=entry_data.get("checksum", ""),
                )
                self.register(entry)
                count += 1

            with self._lock:
                repo.last_sync = time.time()

            return count

        except Exception as e:
            raise RegistryError(f"Failed to sync repository '{url}': {e}") from e

    def count(self) -> int:
        with self._lock:
            return len(self._entries)

    def _load_index(self) -> None:
        if not self._index_file.exists():
            return
        try:
            data = json.loads(self._index_file.read_text(encoding="utf-8"))
            for entry_data in data.get("entries", []):
                e = MarketplaceEntry(**entry_data)
                self._entries[f"{e.package_name}:{e.version}"] = e
        except Exception:
            pass

    def _save_index(self) -> None:
        try:
            data = {
                "updated_at": time.time(),
                "entries": [e.to_dict() for e in self._entries.values()],
            }
            self._index_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass

    def health(self) -> dict[str, Any]:
        with self._lock:
            return {
                "alive": True,
                "entries": len(self._entries),
                "repositories": len(self._repositories),
                "storage_path": str(self._storage_path),
            }
