from __future__ import annotations

from app.tools.base import Tool, ToolMetadata, ToolResult, ToolStatus
from app.tools.integration.lifecycle import ToolLifecycleManager


class _SampleTool(Tool):
    def __init__(self) -> None:
        meta = ToolMetadata(name="sample_tool", version="1.0.0", status=ToolStatus.ACTIVE, capabilities=["greeting", "echo"])
        super().__init__(meta)

    def execute(self, params: dict) -> ToolResult:
        return ToolResult(success=True, output={"message": f"Hello, {params.get('name', 'world')}"})


class _OtherTool(Tool):
    def __init__(self) -> None:
        meta = ToolMetadata(name="other_tool", version="2.0.0", status=ToolStatus.ACTIVE, capabilities=["other"])
        super().__init__(meta)

    def execute(self, params: dict) -> ToolResult:
        return ToolResult(success=True, output={})


class TestToolLifecycleManager:
    def test_register_and_get_tool(self) -> None:
        mgr = ToolLifecycleManager()
        tool = _SampleTool()
        mgr.register_tool(tool)
        retrieved = mgr.get_tool("sample_tool")
        assert retrieved is not None
        assert retrieved.name == "sample_tool"

    def test_register_multiple_versions(self) -> None:
        mgr = ToolLifecycleManager()
        v1 = _SampleTool()
        v2 = _SampleTool()
        v2.metadata.version = "1.1.0"
        mgr.register_tool(v1, version="1.0.0")
        mgr.register_tool(v2, version="1.1.0")
        assert mgr.get_latest_version("sample_tool") == "1.1.0"

    def test_get_version_history(self) -> None:
        mgr = ToolLifecycleManager()
        mgr.register_tool(_SampleTool())
        mgr.register_tool(_OtherTool())
        history = mgr.get_version_history("sample_tool")
        assert len(history) == 1
        assert history[0]["version"] == "1.0.0"

    def test_transition_status(self) -> None:
        mgr = ToolLifecycleManager()
        tool = _SampleTool()
        mgr.register_tool(tool)
        assert mgr.transition_status("sample_tool", ToolStatus.PAUSED)
        retrieved = mgr.get_tool("sample_tool")
        assert retrieved is not None
        assert retrieved.status == ToolStatus.PAUSED

    def test_transition_nonexistent_tool(self) -> None:
        mgr = ToolLifecycleManager()
        assert not mgr.transition_status("nonexistent", ToolStatus.ACTIVE)

    def test_get_tool_with_version(self) -> None:
        mgr = ToolLifecycleManager()
        v1 = _SampleTool()
        v2 = _SampleTool()
        v2.metadata.version = "1.1.0"
        mgr.register_tool(v1, version="1.0.0")
        mgr.register_tool(v2, version="1.1.0")
        assert mgr.get_tool("sample_tool", version="1.0.0") is not None
        assert mgr.get_tool("sample_tool", version="1.1.0") is not None

    def test_list_tools(self) -> None:
        mgr = ToolLifecycleManager()
        mgr.register_tool(_SampleTool())
        mgr.register_tool(_OtherTool())
        tools = mgr.list_tools()
        names = [t["name"] for t in tools]
        assert "sample_tool" in names
        assert "other_tool" in names

    def test_discover_tools_returns_list(self) -> None:
        mgr = ToolLifecycleManager()
        tools = mgr.discover_tools("app.tools")
        assert isinstance(tools, list)

    def test_health(self) -> None:
        mgr = ToolLifecycleManager()
        h = mgr.health()
        assert h["alive"]
