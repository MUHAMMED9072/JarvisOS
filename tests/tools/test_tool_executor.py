from __future__ import annotations

from app.governance.policy_engine import PolicyEngine
from app.governance.policy_registry import Policy, PolicyAction, PolicyRule, PolicyScope
from app.tools.base import Tool, ToolMetadata, ToolParameter, ToolResult, ToolStatus
from app.tools.integration.executor import ToolExecutionRequest, ToolExecutor
from app.tools.integration.monitor import ToolMonitor


class _EchoTool(Tool):
    def __init__(self) -> None:
        meta = ToolMetadata(name="echo_tool", version="1.0.0", status=ToolStatus.ACTIVE)
        super().__init__(meta)

    def execute(self, params: dict) -> ToolResult:
        return ToolResult(success=True, output=params)


class _FailTool(Tool):
    def __init__(self) -> None:
        meta = ToolMetadata(name="fail_tool", version="1.0.0", status=ToolStatus.ACTIVE)
        super().__init__(meta)

    def execute(self, params: dict) -> ToolResult:
        return ToolResult(success=False, error_message="intentional failure")


class _InactiveTool(Tool):
    def __init__(self) -> None:
        meta = ToolMetadata(name="inactive_tool", version="1.0.0", status=ToolStatus.DESIGN)
        super().__init__(meta)

    def execute(self, params: dict) -> ToolResult:
        return ToolResult(success=True, output={})


class TestToolExecutor:
    def test_execute_echo_tool(self) -> None:
        executor = ToolExecutor(tool_instances={"echo_tool": _EchoTool()})
        req = ToolExecutionRequest(tool_name="echo_tool", params={"msg": "hello"})
        result = executor.execute(req)
        assert result.success
        assert result.output == {"msg": "hello"}

    def test_execute_tool_not_found(self) -> None:
        executor = ToolExecutor()
        req = ToolExecutionRequest(tool_name="nonexistent")
        result = executor.execute(req)
        assert not result.success
        assert "not available" in result.error_message

    def test_execute_inactive_tool(self) -> None:
        executor = ToolExecutor(tool_instances={"inactive_tool": _InactiveTool()})
        req = ToolExecutionRequest(tool_name="inactive_tool")
        result = executor.execute(req)
        assert not result.success
        assert "not active" in result.error_message

    def test_execute_failing_tool(self) -> None:
        executor = ToolExecutor(tool_instances={"fail_tool": _FailTool()})
        req = ToolExecutionRequest(tool_name="fail_tool")
        result = executor.execute(req)
        assert not result.success
        assert "intentional failure" in result.error_message

    def test_execution_time_set(self) -> None:
        executor = ToolExecutor(tool_instances={"echo_tool": _EchoTool()})
        req = ToolExecutionRequest(tool_name="echo_tool")
        result = executor.execute(req)
        assert result.execution_time >= 0

    def test_executor_with_monitor(self) -> None:
        monitor = ToolMonitor()
        executor = ToolExecutor(tool_instances={"echo_tool": _EchoTool()}, monitor=monitor)
        req = ToolExecutionRequest(tool_name="echo_tool", params={"x": 1})
        result = executor.execute(req)
        assert result.success
        assert monitor.health()["alive"]

    def test_executor_policy_deny(self) -> None:
        engine = PolicyEngine()
        deny_policy = Policy(
            name="deny_all_tools",
            scope=PolicyScope.SYSTEM,
            rules=[PolicyRule(condition="", action=PolicyAction.DENY, reason="No tools allowed")],
            priority=100,
        )
        engine.registry.register(deny_policy)
        executor = ToolExecutor(
            tool_instances={"echo_tool": _EchoTool()},
            policy_engine=engine,
        )
        req = ToolExecutionRequest(tool_name="echo_tool")
        result = executor.execute(req)
        assert not result.success
        assert "Policy denied" in result.error_message
        assert result.policy_decision is not None

    def test_policy_allows_execution(self) -> None:
        engine = PolicyEngine()
        allow_policy = Policy(
            name="allow_all",
            scope=PolicyScope.GLOBAL,
            rules=[PolicyRule(condition="", action=PolicyAction.ALLOW, reason="Allowed")],
        )
        engine.registry.register(allow_policy)
        executor = ToolExecutor(
            tool_instances={"echo_tool": _EchoTool()},
            policy_engine=engine,
        )
        req = ToolExecutionRequest(tool_name="echo_tool", params={"data": "ok"})
        result = executor.execute(req)
        assert result.success

    def test_list_available_tools(self) -> None:
        executor = ToolExecutor(tool_instances={"echo_tool": _EchoTool()})
        tools = executor.list_available_tools()
        assert any(t["name"] == "echo_tool" for t in tools)

    def test_register_tool_instance(self) -> None:
        executor = ToolExecutor()
        executor.register_tool_instance(_EchoTool())
        tools = executor.list_available_tools()
        assert any(t["name"] == "echo_tool" for t in tools)

    def test_trace_id_propagation(self) -> None:
        executor = ToolExecutor(tool_instances={"echo_tool": _EchoTool()})
        req = ToolExecutionRequest(tool_name="echo_tool", trace_id="custom-trace-123")
        result = executor.execute(req)
        assert result.trace_id == "custom-trace-123"

    def test_to_dict_result(self) -> None:
        executor = ToolExecutor(tool_instances={"echo_tool": _EchoTool()})
        req = ToolExecutionRequest(tool_name="echo_tool", params={"a": 1})
        result = executor.execute(req)
        d = result.to_dict()
        assert d["success"] is True
        assert d["output"] == {"a": 1}
