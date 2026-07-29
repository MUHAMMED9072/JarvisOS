from __future__ import annotations

import tempfile

from app.knowledge_graph.store import GraphStore
from app.tools.base import Tool, ToolMetadata, ToolResult, ToolStatus
from app.tools.integration.synchronizer import RegistrySynchronizer
from app.tools.registry import ToolRegistry


class _SyncTool(Tool):
    def __init__(self) -> None:
        meta = ToolMetadata(name="sync_tool", version="1.0.0", status=ToolStatus.ACTIVE, capabilities=["test"])
        super().__init__(meta)

    def execute(self, params: dict) -> ToolResult:
        return ToolResult(success=True, output={})


class _ArchiveTool(Tool):
    def __init__(self) -> None:
        meta = ToolMetadata(name="archive_tool", version="1.0.0", status=ToolStatus.ARCHIVED)
        super().__init__(meta)

    def execute(self, params: dict) -> ToolResult:
        return ToolResult(success=True, output={})


def _make_store() -> GraphStore:
    return GraphStore(filename=tempfile.mktemp(suffix=".json"))


class TestRegistrySynchronizer:
    def test_sync_tool_creates_entity(self) -> None:
        store = _make_store()
        treg = ToolRegistry(store)
        sync = RegistrySynchronizer(store, treg)
        tool = _SyncTool()
        result = sync.sync_tool(tool)
        assert result["action"] == "created"
        assert result["name"] == "sync_tool"

    def test_sync_tool_updates_existing(self) -> None:
        store = _make_store()
        treg = ToolRegistry(store)
        tool = _SyncTool()
        treg.register(tool)
        sync = RegistrySynchronizer(store, treg)
        result = sync.sync_tool(tool)
        assert result["action"] == "updated"
        assert result["name"] == "sync_tool"

    def test_sync_all(self) -> None:
        store = _make_store()
        treg = ToolRegistry(store)
        sync = RegistrySynchronizer(store, treg)
        tools = [_SyncTool(), _SyncTool()]
        tools[1].metadata.name = "tool_b"
        result = sync.sync_all(tools)
        assert result["synced"] == 2

    def test_remove_tool(self) -> None:
        store = _make_store()
        treg = ToolRegistry(store)
        sync = RegistrySynchronizer(store, treg)
        treg.register(_SyncTool())
        result = sync.remove_tool("sync_tool")
        assert result["deleted"]

    def test_detect_orphans(self) -> None:
        store = _make_store()
        treg = ToolRegistry(store)
        sync = RegistrySynchronizer(store, treg)
        treg.register(_ArchiveTool())
        orphans = sync.detect_orphans()
        assert "archive_tool" in orphans

    def test_cleanup_orphans(self) -> None:
        store = _make_store()
        treg = ToolRegistry(store)
        sync = RegistrySynchronizer(store, treg)
        treg.register(_ArchiveTool())
        count = sync.cleanup_orphans()
        assert count == 1

    def test_get_sync_status(self) -> None:
        store = _make_store()
        treg = ToolRegistry(store)
        sync = RegistrySynchronizer(store, treg)
        status = sync.get_sync_status()
        assert "last_sync_at" in status
        assert "tools_in_kg" in status

    def test_health(self) -> None:
        store = _make_store()
        treg = ToolRegistry(store)
        sync = RegistrySynchronizer(store, treg)
        h = sync.health()
        assert h["alive"]
