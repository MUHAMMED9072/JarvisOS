from __future__ import annotations

import tempfile

from app.agents.types import ToolAgent
from app.governance.policy_engine import PolicyEngine
from app.governance.policy_registry import Policy, PolicyAction, PolicyRule, PolicyScope
from app.knowledge_graph.store import GraphStore
from app.tools.base import Tool, ToolMetadata, ToolParameter, ToolResult, ToolStatus
from app.tools.integration.capability import ToolCapabilityMapper
from app.tools.integration.executor import ToolExecutionRequest, ToolExecutor
from app.tools.integration.lifecycle import ToolLifecycleManager
from app.tools.integration.monitor import ToolMonitor
from app.tools.integration.validator import ToolDependencyValidator
from app.tools.integration.synchronizer import RegistrySynchronizer
from app.tools.registry import ToolRegistry


class _GreetTool(Tool):
    def __init__(self) -> None:
        meta = ToolMetadata(
            name="greet_tool", version="1.0.0", status=ToolStatus.ACTIVE,
            capabilities=["greeting"],
            parameters=[ToolParameter(name="name", type="string", required=True)],
        )
        super().__init__(meta)

    def execute(self, params: dict) -> ToolResult:
        name = params.get("name", "world")
        return ToolResult(success=True, output={"message": f"Hello, {name}!"})


class _CalcTool(Tool):
    def __init__(self) -> None:
        meta = ToolMetadata(
            name="calc_tool", version="1.0.0", status=ToolStatus.ACTIVE,
            capabilities=["calculate"],
            parameters=[
                ToolParameter(name="a", type="number", required=True),
                ToolParameter(name="b", type="number", required=True),
                ToolParameter(name="op", type="string", required=False, default="add"),
            ],
        )
        super().__init__(meta)

    def execute(self, params: dict) -> ToolResult:
        a = params.get("a", 0)
        b = params.get("b", 0)
        op = params.get("op", "add")
        if op == "add":
            return ToolResult(success=True, output={"result": a + b})
        return ToolResult(success=False, error_message=f"Unknown op: {op}")


def _make_store() -> GraphStore:
    return GraphStore(filename=tempfile.mktemp(suffix=".json"))


class TestToolIntegrationE2E:
    def test_full_lifecycle(self) -> None:
        store = _make_store()
        treg = ToolRegistry(store)
        cap_reg = ToolCapabilityMapper(store, treg)
        lifecycle = ToolLifecycleManager(registry=treg)
        del lifecycle

        treg.register(_GreetTool())
        treg.register(_CalcTool())

        assert treg.get_tool_count() == 2

    def test_executor_with_all_components(self) -> None:
        store = _make_store()
        treg = ToolRegistry(store)
        monitor = ToolMonitor()
        engine = PolicyEngine()

        allow_policy = Policy(
            name="allow_tools",
            scope=PolicyScope.GLOBAL,
            rules=[PolicyRule(condition="", action=PolicyAction.ALLOW, reason="OK")],
        )
        engine.registry.register(allow_policy)

        executor = ToolExecutor(
            registry=treg,
            policy_engine=engine,
            monitor=monitor,
            tool_instances={"greet_tool": _GreetTool()},
        )

        req = ToolExecutionRequest(tool_name="greet_tool", params={"name": "JARVIS"})
        result = executor.execute(req)
        assert result.success
        assert result.output == {"message": "Hello, JARVIS!"}

    def test_policy_denies_tool_execution(self) -> None:
        store = _make_store()
        treg = ToolRegistry(store)
        engine = PolicyEngine()
        deny = Policy(
            name="deny_greet",
            scope=PolicyScope.SYSTEM,
            rules=[PolicyRule(condition="tool == greet_tool", action=PolicyAction.DENY, reason="Greeting disabled")],
            priority=100,
        )
        engine.registry.register(deny)

        executor = ToolExecutor(
            registry=treg,
            policy_engine=engine,
            tool_instances={"greet_tool": _GreetTool()},
        )
        req = ToolExecutionRequest(tool_name="greet_tool", params={"name": "test"})
        result = executor.execute(req)
        assert not result.success

    def test_tool_agent_with_executor(self) -> None:
        executor = ToolExecutor(tool_instances={"greet_tool": _GreetTool()})
        agent = ToolAgent(tool_name="greet_tool", executor=executor)
        result = agent.execute({"params": {"name": "Agent"}})
        assert result["success"]
        assert result["output"]["message"] == "Hello, Agent!"

    def test_tool_agent_without_executor_fallback(self) -> None:
        agent = ToolAgent(tool_name="greet_tool")
        result = agent.execute({"params": {"name": "test"}})
        assert result["status"] == "ok"
        assert result["tool"] == "greet_tool"

    def test_registry_sync_and_capability_mapping(self) -> None:
        store = _make_store()
        treg = ToolRegistry(store)
        greeter = _GreetTool()
        treg.register(greeter)

        sync = RegistrySynchronizer(store, treg)
        sync.sync_tool(greeter)

        mapper = ToolCapabilityMapper(store, treg)
        mapper.register_tool_capabilities(greeter)

        status = sync.get_sync_status()
        assert status["tools_in_kg"] >= 1

    def test_end_to_end_monitoring(self) -> None:
        monitor = ToolMonitor()
        executor = ToolExecutor(
            tool_instances={"greet_tool": _GreetTool()},
            monitor=monitor,
        )
        req = ToolExecutionRequest(tool_name="greet_tool", params={"name": "monitor"})
        executor.execute(req)

        metrics = monitor.get_metrics()
        key = "greet_tool:execute"
        assert key in metrics
        assert metrics[key]["count"] == 1

        traces = monitor.get_traces(tool_name="greet_tool")
        assert len(traces) == 1

    def test_dependency_validation_with_registry(self) -> None:
        store = _make_store()
        treg = ToolRegistry(store)

        class _DepTool(Tool):
            def __init__(self) -> None:
                meta = ToolMetadata(name="has_dep", version="1.0.0", status=ToolStatus.ACTIVE, tags=["dep:greet_tool"])
                super().__init__(meta)
            def execute(self, params: dict) -> ToolResult:
                return ToolResult(success=True, output={})

        treg.register(_GreetTool())
        validator = ToolDependencyValidator(registry=treg)
        result = validator.validate_tool(_DepTool())
        assert not result.missing_dependencies

    def test_executor_list_tools(self) -> None:
        executor = ToolExecutor(
            tool_instances={"greet_tool": _GreetTool(), "calc_tool": _CalcTool()},
        )
        tools = executor.list_available_tools()
        assert len(tools) == 2
        names = [t["name"] for t in tools]
        assert "greet_tool" in names
        assert "calc_tool" in names
