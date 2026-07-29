from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from app.agents.discovery import AgentDiscovery, DiscoveryResult, Manifest
from app.agents.registry import AgentRegistry
from app.knowledge_graph.store import GraphStore


def _make_store() -> GraphStore:
    return GraphStore(filename=tempfile.mktemp(suffix=".json"))


_VALID_MANIFEST = {
    "name": "test_agent",
    "version": "1.0.0",
    "description": "A test agent",
    "agent_type": "domain",
    "capabilities": [{"name": "greeting", "description": "Says hello"}],
    "dependencies": [],
    "entry_point": "module:TestAgent",
    "tags": ["test"],
    "owner": "system",
}


class TestManifest:
    def test_valid_manifest(self) -> None:
        m = Manifest(_VALID_MANIFEST)
        assert m.name == "test_agent"
        assert m.version == "1.0.0"
        assert m.agent_type == "domain"

    def test_validation_passes(self) -> None:
        m = Manifest(_VALID_MANIFEST)
        assert m.validate() == []

    def test_validation_fails_missing_name(self) -> None:
        m = Manifest({"version": "1.0.0", "agent_type": "domain", "entry_point": "a:b"})
        errors = m.validate()
        assert any("name" in e for e in errors)

    def test_validation_fails_bad_type(self) -> None:
        data = dict(_VALID_MANIFEST)
        data["agent_type"] = "invalid_type"
        m = Manifest(data)
        errors = m.validate()
        assert any("agent_type" in e for e in errors)

    def test_validation_fails_bad_entry_point(self) -> None:
        data = dict(_VALID_MANIFEST)
        data["entry_point"] = "NoColon"
        m = Manifest(data)
        errors = m.validate()
        assert any("entry_point" in e for e in errors)

    def test_to_metadata(self) -> None:
        m = Manifest(_VALID_MANIFEST)
        meta = m.to_metadata()
        assert meta.name == "test_agent"
        assert meta.version == "1.0.0"

    def test_to_dict(self) -> None:
        m = Manifest(_VALID_MANIFEST)
        d = m.to_dict()
        assert d["name"] == "test_agent"


class TestAgentDiscovery:
    def test_scan_empty_directories(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = _make_store()
            reg = AgentRegistry(store)
            discovery = AgentDiscovery(reg, search_dirs=[td])
            result = discovery.scan_once()
            assert len(result.discovered) == 0
            assert len(result.errors) == 0

    def test_scan_discovers_agent(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            manifest_path = Path(td) / "agent.json"
            manifest_path.write_text(json.dumps(_VALID_MANIFEST), encoding="utf-8")

            store = _make_store()
            reg = AgentRegistry(store)
            discovery = AgentDiscovery(reg, search_dirs=[td])
            result = discovery.scan_once()
            assert len(result.discovered) == 1
            assert result.discovered[0]["name"] == "test_agent"

    def test_scan_skips_subdirectory(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            subdir = Path(td) / "subagent"
            subdir.mkdir()
            manifest_path = subdir / "agent.json"
            manifest_path.write_text(json.dumps(_VALID_MANIFEST), encoding="utf-8")

            store = _make_store()
            reg = AgentRegistry(store)
            discovery = AgentDiscovery(reg, search_dirs=[td])
            result = discovery.scan_once()
            assert len(result.discovered) == 1

    def test_invalid_json_reported(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            manifest_path = Path(td) / "agent.json"
            manifest_path.write_text("not valid json", encoding="utf-8")

            store = _make_store()
            reg = AgentRegistry(store)
            discovery = AgentDiscovery(reg, search_dirs=[td])
            result = discovery.scan_once()
            assert len(result.errors) >= 1

    def test_manifest_in_current_dir(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            manifest_path = Path(td) / "manifest.json"
            manifest_path.write_text(json.dumps(_VALID_MANIFEST), encoding="utf-8")

            store = _make_store()
            reg = AgentRegistry(store)
            discovery = AgentDiscovery(reg, search_dirs=[td])
            result = discovery.scan_once()
            assert len(result.discovered) == 1

    def test_health(self) -> None:
        store = _make_store()
        reg = AgentRegistry(store)
        discovery = AgentDiscovery(reg)
        h = discovery.health()
        assert h["alive"]

    def test_watcher_start_stop(self) -> None:
        store = _make_store()
        reg = AgentRegistry(store)
        discovery = AgentDiscovery(reg)
        discovery.start_watcher(interval=0.5)
        assert discovery.health()["watcher_active"]
        discovery.stop_watcher()
        assert not discovery.health()["watcher_active"]

    def test_event_callback_on_discovery(self) -> None:
        events: list[tuple[str, dict]] = []

        def callback(event: str, data: dict) -> None:
            events.append((event, data))

        with tempfile.TemporaryDirectory() as td:
            manifest_path = Path(td) / "agent.json"
            manifest_path.write_text(json.dumps(_VALID_MANIFEST), encoding="utf-8")

            store = _make_store()
            reg = AgentRegistry(store)
            discovery = AgentDiscovery(reg, search_dirs=[td], event_callback=callback)
            discovery.scan_once()
            discovered_events = [e for e in events if e[0] == "agent.discovery.discovered"]
            assert len(discovered_events) == 1
