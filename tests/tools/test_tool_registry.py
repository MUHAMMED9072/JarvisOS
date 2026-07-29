from __future__ import annotations

from typing import Any

from app.knowledge_graph.store import GraphStore
from app.tools.base import Tool, ToolMetadata, ToolResult
from app.tools.registry import ToolRegistry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _graph() -> GraphStore:
    return GraphStore()


def _registry() -> ToolRegistry:
    return ToolRegistry(_graph())


class _TestTool(Tool):
    def execute(self, params: dict[str, Any]) -> ToolResult:
        return ToolResult(success=True, output=params)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

class TestRegister:
    def test_register_tool(self) -> None:
        registry = _registry()
        tool = _TestTool(ToolMetadata(name="test_tool", version="1.0.0", capabilities=["exec"]))
        meta = registry.register(tool)
        assert meta.name == "test_tool"
        assert meta.tool_id != ""

    def test_register_duplicate_updates(self) -> None:
        registry = _registry()
        t1 = _TestTool(ToolMetadata(name="dup", version="1.0.0"))
        registry.register(t1)
        t2 = _TestTool(ToolMetadata(name="dup", version="2.0.0"))
        meta = registry.register(t2)
        assert meta.version == "2.0.0"

    def test_register_stores_capabilities(self) -> None:
        graph = _graph()
        registry = ToolRegistry(graph)
        graph.create_entity(type="capability", name="python_exec")
        tool = _TestTool(ToolMetadata(name="cap_test", version="1.0.0", capabilities=["python_exec"]))
        registry.register(tool)
        matches = registry.get_by_capability("python_exec")
        assert any(m.name == "cap_test" for m in matches)

    def test_register_no_capabilities(self) -> None:
        registry = _registry()
        tool = _TestTool(ToolMetadata(name="no_cap", version="1.0.0"))
        meta = registry.register(tool)
        assert meta.capabilities == []

    def test_register_with_permissions(self) -> None:
        registry = _registry()
        tool = _TestTool(ToolMetadata(name="perm_tool", version="1.0.0", permissions_required=["tools.python.execute"]))
        registry.register(tool)
        meta = registry.list()
        assert any(m.permissions_required == ["tools.python.execute"] for m in meta)


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------

class TestGet:
    def test_get_by_name(self) -> None:
        registry = _registry()
        tool = _TestTool(ToolMetadata(name="get_tool", version="1.0.0"))
        registry.register(tool)
        meta = registry.get("get_tool")
        assert meta is not None
        assert meta.name == "get_tool"

    def test_get_nonexistent(self) -> None:
        registry = _registry()
        assert registry.get("nonexistent") is None

    def test_get_by_id(self) -> None:
        registry = _registry()
        tool = _TestTool(ToolMetadata(name="id_tool", version="1.0.0"))
        meta = registry.register(tool)
        retrieved = registry.get_by_id(meta.tool_id)
        assert retrieved is not None
        assert retrieved.name == "id_tool"

    def test_get_by_id_nonexistent(self) -> None:
        registry = _registry()
        assert registry.get_by_id("bad_id") is None

    def test_get_returns_metadata(self) -> None:
        registry = _registry()
        tool = _TestTool(ToolMetadata(name="meta_tool", version="1.0.0"))
        registry.register(tool)
        result = registry.get("meta_tool")
        assert isinstance(result, ToolMetadata)


# ---------------------------------------------------------------------------
# Listing and searching
# ---------------------------------------------------------------------------

class TestListAndSearch:
    def test_list_empty(self) -> None:
        registry = _registry()
        assert registry.list() == []

    def test_list_multiple(self) -> None:
        registry = _registry()
        for i in range(3):
            tool = _TestTool(ToolMetadata(name=f"tool_{i}", version="1.0.0"))
            registry.register(tool)
        assert len(registry.list()) == 3

    def test_search_by_name(self) -> None:
        registry = _registry()
        tool = _TestTool(ToolMetadata(name="searchable_tool", version="1.0.0"))
        registry.register(tool)
        results = registry.search("searchable")
        assert len(results) >= 1

    def test_search_no_results(self) -> None:
        registry = _registry()
        assert registry.search("zzz_nonexistent") == []

    def test_get_by_capability(self) -> None:
        graph = _graph()
        registry = ToolRegistry(graph)
        graph.create_entity(type="capability", name="http_client")
        tool = _TestTool(ToolMetadata(name="http_tool", version="1.0.0", capabilities=["http_client"]))
        registry.register(tool)
        results = registry.get_by_capability("http_client")
        assert len(results) == 1
        assert results[0].name == "http_tool"

    def test_get_by_capability_no_match(self) -> None:
        registry = _registry()
        assert registry.get_by_capability("nonexistent") == []

    def test_get_by_capability_multiple(self) -> None:
        graph = _graph()
        registry = ToolRegistry(graph)
        graph.create_entity(type="capability", name="file_ops")
        for name in ["a", "b"]:
            t = _TestTool(ToolMetadata(name=name, version="1.0.0", capabilities=["file_ops"]))
            registry.register(t)
        results = registry.get_by_capability("file_ops")
        assert len(results) == 2


# ---------------------------------------------------------------------------
# Unregistration / Deletion
# ---------------------------------------------------------------------------

class TestUnregister:
    def test_unregister(self) -> None:
        registry = _registry()
        tool = _TestTool(ToolMetadata(name="remove_me", version="1.0.0"))
        registry.register(tool)
        assert registry.get("remove_me") is not None
        assert registry.unregister("remove_me") is True
        assert registry.get("remove_me") is None

    def test_unregister_nonexistent(self) -> None:
        registry = _registry()
        assert registry.unregister("nonexistent") is False

    def test_delete_by_id(self) -> None:
        registry = _registry()
        tool = _TestTool(ToolMetadata(name="del_tool", version="1.0.0"))
        meta = registry.register(tool)
        assert registry.delete(meta.tool_id) is True
        assert registry.get("del_tool") is None

    def test_delete_nonexistent(self) -> None:
        registry = _registry()
        assert registry.delete("bad_id") is False


# ---------------------------------------------------------------------------
# Health & count
# ---------------------------------------------------------------------------

class TestHealth:
    def test_tool_count(self) -> None:
        registry = _registry()
        assert registry.get_tool_count() == 0
        tool = _TestTool(ToolMetadata(name="count_test", version="1.0.0"))
        registry.register(tool)
        assert registry.get_tool_count() == 1

    def test_health(self) -> None:
        registry = _registry()
        h = registry.health()
        assert h["alive"] is True
        assert h["tool_count"] == 0


# ---------------------------------------------------------------------------
# Shared graph store
# ---------------------------------------------------------------------------

class TestSharedGraph:
    def test_same_graph_store(self) -> None:
        graph = _graph()
        r1 = ToolRegistry(graph)
        r2 = ToolRegistry(graph)
        t = _TestTool(ToolMetadata(name="shared", version="1.0.0"))
        r1.register(t)
        meta = r2.get("shared")
        assert meta is not None
        assert meta.name == "shared"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_register_with_tags(self) -> None:
        registry = _registry()
        tool = _TestTool(ToolMetadata(name="tagged", version="1.0.0", tags=["alpha", "beta"]))
        registry.register(tool)
        meta = registry.list()
        assert any(m.tags == ["alpha", "beta"] for m in meta)

    def test_list_returns_metadata(self) -> None:
        registry = _registry()
        tool = _TestTool(ToolMetadata(name="list_test", version="1.0.0"))
        registry.register(tool)
        lst = registry.list()
        assert all(isinstance(m, ToolMetadata) for m in lst)

    def test_search_returns_metadata(self) -> None:
        registry = _registry()
        tool = _TestTool(ToolMetadata(name="search_meta", version="1.0.0"))
        registry.register(tool)
        results = registry.search("search_meta")
        assert all(isinstance(m, ToolMetadata) for m in results)

    def test_get_by_capability_returns_metadata(self) -> None:
        graph = _graph()
        registry = ToolRegistry(graph)
        graph.create_entity(type="capability", name="test_cap")
        tool = _TestTool(ToolMetadata(name="cap_meta", version="1.0.0", capabilities=["test_cap"]))
        registry.register(tool)
        results = registry.get_by_capability("test_cap")
        assert all(isinstance(m, ToolMetadata) for m in results)
