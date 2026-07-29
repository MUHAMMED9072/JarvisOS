from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Callable

from app.agents.base import Agent, AgentCapability, AgentMetadata, AgentStatus
from app.agents.factory import AgentFactory
from app.agents.registry import AgentRegistry


class AgentDiscoveryEvent:
    DISCOVERED = "agent.discovery.discovered"
    REGISTERED = "agent.discovery.registered"
    REMOVED = "agent.discovery.removed"
    ERROR = "agent.discovery.error"


class DiscoveryResult:
    def __init__(
        self,
        discovered: list[dict[str, Any]] | None = None,
        registered: list[dict[str, Any]] | None = None,
        errors: list[str] | None = None,
    ) -> None:
        self.discovered = discovered or []
        self.registered = registered or []
        self.errors = errors or []

    def to_dict(self) -> dict[str, Any]:
        return {
            "discovered": list(self.discovered),
            "registered": list(self.registered),
            "errors": list(self.errors),
        }


class Manifest:
    """Agent manifest schema for discovery.

    Expected format (JSON):
      {
        "name": "agent_name",
        "version": "1.0.0",
        "description": "...",
        "agent_type": "domain",
        "capabilities": [{"name": "cap", "description": "..."}],
        "dependencies": ["dep1"],
        "entry_point": "module:ClassName",
        "tags": ["tag1"],
        "owner": "system"
      }
    """

    REQUIRED_FIELDS = ["name", "version", "agent_type", "entry_point"]

    def __init__(self, data: dict[str, Any], source_path: str = "") -> None:
        self._data = data
        self.source_path = source_path

    @property
    def name(self) -> str:
        return self._data.get("name", "")

    @property
    def version(self) -> str:
        return self._data.get("version", "1.0.0")

    @property
    def description(self) -> str:
        return self._data.get("description", "")

    @property
    def agent_type(self) -> str:
        return self._data.get("agent_type", "system")

    @property
    def capabilities(self) -> list[dict[str, Any]]:
        return self._data.get("capabilities", [])

    @property
    def dependencies(self) -> list[str]:
        return self._data.get("dependencies", [])

    @property
    def entry_point(self) -> str:
        return self._data.get("entry_point", "")

    @property
    def tags(self) -> list[str]:
        return self._data.get("tags", [])

    @property
    def owner(self) -> str:
        return self._data.get("owner", "")

    def validate(self) -> list[str]:
        errors: list[str] = []
        for field in self.REQUIRED_FIELDS:
            if not self._data.get(field):
                errors.append(f"Missing required field: '{field}'")
        if self.agent_type not in ("system", "tool", "development", "domain", "composite"):
            errors.append(f"Invalid agent_type: '{self.agent_type}'")
        if self.entry_point and ":" not in self.entry_point:
            errors.append("entry_point must be in format 'module:ClassName'")
        return errors

    def to_metadata(self) -> AgentMetadata:
        caps = [AgentCapability(name=c.get("name", ""), description=c.get("description", "")) for c in self.capabilities]
        return AgentMetadata(
            name=self.name,
            version=self.version,
            description=self.description,
            agent_type=self.agent_type,
            status=AgentStatus.DESIGN,
            capabilities=caps,
            dependencies=list(self.dependencies),
            owner=self.owner,
            tags=list(self.tags),
        )

    def to_dict(self) -> dict[str, Any]:
        return dict(self._data)


class AgentDiscovery:
    """Filesystem-based agent discovery and registration.

    Scans standard directories for agent manifests, validates them,
    and registers discovered agents in the Knowledge Graph via
    AgentRegistry.
    """

    MANIFEST_FILENAMES = ["agent.json", "manifest.json", ".agent.json"]

    def __init__(
        self,
        registry: AgentRegistry,
        search_dirs: list[str] | None = None,
        event_callback: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> None:
        self._registry = registry
        self._search_dirs = [Path(d).resolve() for d in (search_dirs or [
            os.path.join("app", "agents", "builtin"),
            os.path.join("data", "agents"),
        ])]
        self._event_callback = event_callback
        self._lock = threading.RLock()
        self._watcher_active = False
        self._watcher_thread: threading.Thread | None = None
        self._watcher_interval: float = 5.0
        self._stop_event = threading.Event()
        self._known_manifests: dict[str, float] = {}

    def scan_once(self) -> DiscoveryResult:
        """Scan all search directories once and return results."""
        result = DiscoveryResult()

        for search_dir in self._search_dirs:
            if not search_dir.is_dir():
                continue

            for manifest_path in self._find_manifests(search_dir):
                try:
                    data = json.loads(manifest_path.read_text(encoding="utf-8"))
                    manifest = Manifest(data, source_path=str(manifest_path))
                    errors = manifest.validate()
                    if errors:
                        result.errors.append(f"{manifest_path}: {'; '.join(errors)}")
                        self._publish(AgentDiscoveryEvent.ERROR, {
                            "path": str(manifest_path), "errors": errors,
                        })
                        continue

                    agent_meta = manifest.to_metadata()
                    agent = self._create_agent(manifest)
                    if agent is None:
                        result.errors.append(f"{manifest_path}: failed to create agent instance")
                        continue

                    registration = self._registry.register(agent)
                    result.discovered.append(manifest.to_dict())
                    result.registered.append({
                        "agent_id": registration.agent_id,
                        "name": manifest.name,
                        "status": registration.status.value,
                    })
                    self._publish(AgentDiscoveryEvent.DISCOVERED, {
                        "name": manifest.name,
                        "path": str(manifest_path),
                        "agent_id": registration.agent_id,
                    })
                    self._known_manifests[str(manifest_path)] = os.path.getmtime(str(manifest_path))

                except json.JSONDecodeError as e:
                    result.errors.append(f"{manifest_path}: invalid JSON - {e}")
                except Exception as e:
                    result.errors.append(f"{manifest_path}: {e}")

        return result

    def start_watcher(self, interval: float = 5.0) -> None:
        """Start continuous filesystem watching in a background thread."""
        with self._lock:
            if self._watcher_active:
                return
            self._watcher_active = True
            self._watcher_interval = interval
            self._stop_event.clear()
            self._watcher_thread = threading.Thread(
                target=self._watcher_loop,
                daemon=True,
                name="agent-discovery-watcher",
            )
            self._watcher_thread.start()

    def stop_watcher(self) -> None:
        """Stop the background filesystem watcher."""
        with self._lock:
            self._watcher_active = False
            self._stop_event.set()
            if self._watcher_thread:
                self._watcher_thread.join(timeout=10)
                self._watcher_thread = None

    def _watcher_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._check_for_new_agents()
            except Exception:
                pass
            self._stop_event.wait(self._watcher_interval)

    def _check_for_new_agents(self) -> None:
        for search_dir in self._search_dirs:
            if not search_dir.is_dir():
                continue
            for manifest_path in self._find_manifests(search_dir):
                path_str = str(manifest_path)
                mtime = os.path.getmtime(path_str)
                last_mtime = self._known_manifests.get(path_str)
                if last_mtime is None or mtime > last_mtime:
                    try:
                        data = json.loads(manifest_path.read_text(encoding="utf-8"))
                        manifest = Manifest(data, source_path=path_str)
                        if not manifest.validate():
                            continue
                        agent = self._create_agent(manifest)
                        if agent is None:
                            continue
                        self._registry.register(agent)
                        self._known_manifests[path_str] = mtime
                        self._publish(AgentDiscoveryEvent.DISCOVERED, {
                            "name": manifest.name,
                            "path": path_str,
                        })
                    except Exception:
                        pass

    def _find_manifests(self, directory: Path) -> list[Path]:
        manifests: list[Path] = []
        for fname in self.MANIFEST_FILENAMES:
            candidate = directory / fname
            if candidate.is_file():
                manifests.append(candidate)
        for item in directory.iterdir():
            if item.is_dir():
                for fname in self.MANIFEST_FILENAMES:
                    candidate = item / fname
                    if candidate.is_file():
                        manifests.append(candidate)
        return manifests

    def _create_agent(self, manifest: Manifest) -> Agent | None:
        try:
            return AgentFactory.create(
                agent_type=manifest.agent_type,
                name=manifest.name,
                version=manifest.version,
                description=manifest.description,
                capabilities=[c.to_dict() if isinstance(c, AgentCapability) else c for c in manifest.capabilities],
                dependencies=manifest.dependencies,
                owner=manifest.owner,
            )
        except Exception:
            return None

    def _publish(self, event: str, data: dict[str, Any]) -> None:
        if self._event_callback:
            try:
                self._event_callback(event, data)
            except Exception:
                pass

    def health(self) -> dict[str, Any]:
        return {
            "alive": True,
            "search_directories": [str(d) for d in self._search_dirs],
            "watcher_active": self._watcher_active,
            "known_manifests": len(self._known_manifests),
        }
