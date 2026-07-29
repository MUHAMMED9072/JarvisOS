from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from app.governance.policy_engine import PolicyEngine
from app.tools.base import Tool, ToolResult, ToolStatus
from app.tools.integration.monitor import ToolMonitor
from app.tools.registry import ToolRegistry


@dataclass
class ToolExecutionRequest:
    tool_name: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict)
    trace_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "params": dict(self.params),
            "context": dict(self.context),
            "trace_id": self.trace_id,
        }


@dataclass
class ToolExecutionResult:
    success: bool = False
    output: Any = None
    error_message: str = ""
    execution_time: float = 0.0
    trace_id: str = ""
    policy_decision: dict[str, Any] | None = None
    stdout: str = ""
    stderr: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "output": self.output,
            "error_message": self.error_message,
            "execution_time": round(self.execution_time, 4),
            "trace_id": self.trace_id,
            "policy_decision": self.policy_decision,
        }


class ToolExecutor:
    """Unified execution API for all tools.

    Handles:
      - Tool lookup and instantiation
      - Policy enforcement (Governance integration)
      - Execution metrics and tracing (ToolMonitor integration)
      - Parameter validation
      - Error handling
      - Thread-safe execution

    Usage:
      executor = ToolExecutor(registry, policy_engine, monitor)
      result = executor.execute(ToolExecutionRequest("shell_tool", {"command": "ls"}))
    """

    def __init__(
        self,
        registry: ToolRegistry | None = None,
        policy_engine: PolicyEngine | None = None,
        monitor: ToolMonitor | None = None,
        tool_instances: dict[str, Tool] | None = None,
    ) -> None:
        self._registry = registry
        self._policy_engine = policy_engine
        self._monitor = monitor
        self._tool_instances: dict[str, Tool] = {}

        if tool_instances:
            for name, instance in tool_instances.items():
                self._tool_instances[name] = instance

    def register_tool_instance(self, tool: Tool) -> None:
        self._tool_instances[tool.name] = tool

    def execute(self, request: ToolExecutionRequest) -> ToolExecutionResult:
        start = time.time()

        if request.trace_id and self._monitor:
            self._monitor.add_span(request.trace_id, type("Span", (), {
                "name": f"executor.{request.tool_name}",
                "start_time": start,
                "end_time": 0.0,
                "status": "ok",
                "details": "",
            })())

        tool = self._tool_instances.get(request.tool_name)
        if tool is None and self._registry:
            meta = self._registry.get(request.tool_name)
            if meta is None:
                elapsed = time.time() - start
                return ToolExecutionResult(
                    success=False, error_message=f"Tool '{request.tool_name}' not found",
                    execution_time=elapsed,
                )

        if tool is None:
            elapsed = time.time() - start
            return ToolExecutionResult(
                success=False, error_message=f"Tool '{request.tool_name}' not available",
                execution_time=elapsed,
            )

        if tool.status not in (ToolStatus.ACTIVE, ToolStatus.APPROVED, ToolStatus.INSTALLED):
            elapsed = time.time() - start
            return ToolExecutionResult(
                success=False,
                error_message=f"Tool '{request.tool_name}' is not active (status: {tool.status.value})",
                execution_time=elapsed,
            )

        policy_decision = None
        if self._policy_engine:
            policy_context = {
                "scope": "system",
                "action": f"tool.{request.tool_name}.execute",
                "tool": request.tool_name,
                "params": request.params,
                "context": request.context,
            }
            decision = self._policy_engine.evaluate(policy_context)
            policy_decision = decision.to_dict()
            if decision.denied:
                elapsed = time.time() - start
                return ToolExecutionResult(
                    success=False,
                    error_message=f"Policy denied: {decision.reason}",
                    execution_time=elapsed,
                    trace_id=request.trace_id,
                    policy_decision=policy_decision,
                )

        trace_id = request.trace_id
        if self._monitor and not trace_id:
            trace_id = self._monitor.begin_trace(
                request.tool_name, tool.version,
                request.params.get("action", request.params.get("command", "execute")),
            )

        try:
            result = tool.execute(request.params)
            elapsed = time.time() - start
            exec_result = ToolExecutionResult(
                success=result.success,
                output=result.output,
                error_message=result.error_message,
                execution_time=elapsed,
                trace_id=trace_id or "",
                policy_decision=policy_decision,
                stdout=result.stdout,
                stderr=result.stderr,
            )

            if self._monitor and trace_id:
                self._monitor.end_trace(trace_id, result.success, result.error_message)

            return exec_result

        except Exception as e:
            elapsed = time.time() - start
            if self._monitor and trace_id:
                self._monitor.end_trace(trace_id, False, str(e))
            return ToolExecutionResult(
                success=False,
                error_message=str(e),
                execution_time=elapsed,
                trace_id=trace_id or "",
                policy_decision=policy_decision,
            )

    def list_available_tools(self) -> list[dict[str, Any]]:
        tools: list[dict[str, Any]] = []
        for name, tool in self._tool_instances.items():
            tools.append({
                "name": tool.name,
                "version": tool.version,
                "status": tool.status.value,
                "capabilities": list(tool.metadata.capabilities),
                "permissions_required": list(tool.metadata.permissions_required),
            })
        if self._registry:
            for meta in self._registry.list():
                if meta.name not in self._tool_instances:
                    tools.append({
                        "name": meta.name,
                        "version": meta.version,
                        "status": meta.status.value,
                        "capabilities": list(meta.capabilities),
                        "permissions_required": list(meta.permissions_required),
                    })
        return tools
