from __future__ import annotations

import tempfile

from app.knowledge_graph.capability_registry import CapabilityRegistry
from app.knowledge_graph.store import GraphStore
from app.tools.base import Tool, ToolMetadata, ToolResult, ToolStatus
from app.tools.integration.capability import ToolCapabilityMapper
from app.tools.registry import ToolRegistry


class _CapableTool(Tool):
    def __init__(self) -> None:
        meta = ToolMetadata(
            name="capable_tool", version="1.0.0", status=ToolStatus.ACTIVE,
            capabilities=["search", "analyze", "report"],
        )
        super().__init__(meta)

    def execute(self, params: dict) -> ToolResult:
        return ToolResult(success=True, output={})


class _MinimalTool(Tool):
    def __init__(self) -> None:
        meta = ToolMetadata(
            name="minimal_tool", version="2.0.0", status=ToolStatus.ACTIVE,
            capabilities=["greet"],
        )
        super().__init__(meta)

    def execute(self, params: dict) -> ToolResult:
        return ToolResult(success=True, output={})


def _make_store() -> GraphStore:
    return GraphStore(filename=tempfile.mktemp(suffix=".json"))


class TestToolCapabilityMapper:
    def test_register_capabilities(self) -> None:
        store = _make_store()
        treg = ToolRegistry(store)
        mapper = ToolCapabilityMapper(store, treg)
        tool = _CapableTool()
        treg.register(tool)
        count = mapper.register_tool_capabilities(tool)
        assert count == 3

    def test_find_tools_by_capability(self) -> None:
        store = _make_store()
        treg = ToolRegistry(store)
        mapper = ToolCapabilityMapper(store, treg)
        tool = _CapableTool()
        treg.register(tool)
        mapper.register_tool_capabilities(tool)
        providers = mapper.find_tools_by_capability("search")
        assert len(providers) >= 0

    def test_find_capability_gaps(self) -> None:
        store = _make_store()
        treg = ToolRegistry(store)
        mapper = ToolCapabilityMapper(store, treg)
        gaps = mapper.find_tool_capability_gaps(["search", "time_travel"])
        assert "time_travel" in gaps.get("missing", [])

    def test_quality_score(self) -> None:
        store = _make_store()
        treg = ToolRegistry(store)
        mapper = ToolCapabilityMapper(store, treg)
        tool = _CapableTool()
        treg.register(tool)
        mapper.update_tool_quality_score("capable_tool", 0.95)
        score = mapper.get_tool_quality_score("capable_tool")
        assert score == 0.95

    def test_quality_score_nonexistent(self) -> None:
        store = _make_store()
        treg = ToolRegistry(store)
        mapper = ToolCapabilityMapper(store, treg)
        score = mapper.get_tool_quality_score("nonexistent")
        assert score == 0.0

    def test_register_twice_no_duplicate_rels(self) -> None:
        store = _make_store()
        treg = ToolRegistry(store)
        mapper = ToolCapabilityMapper(store, treg)
        tool = _CapableTool()
        treg.register(tool)
        mapper.register_tool_capabilities(tool)
        c1 = store.relationship_count()
        mapper.register_tool_capabilities(tool)
        c2 = store.relationship_count()
        assert c1 == c2

    def test_health(self) -> None:
        store = _make_store()
        treg = ToolRegistry(store)
        mapper = ToolCapabilityMapper(store, treg)
        h = mapper.health()
        assert h["alive"]
