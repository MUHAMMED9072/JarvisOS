from __future__ import annotations

from typing import Any

from app.agents.base import Agent, AgentMetadata, AgentStatus


class SystemAgent(Agent):
    """Agent that performs system-level operations."""

    def __init__(self, metadata: AgentMetadata | None = None) -> None:
        if metadata is None:
            metadata = AgentMetadata(agent_id="", name="system_agent", agent_type="system")
        super().__init__(metadata)

    def execute(self, context: dict[str, Any]) -> dict[str, Any]:
        return {"status": "ok", "action": "system_operation", "context_keys": list(context.keys())}


class ToolAgent(Agent):
    """Agent that wraps a specific tool and executes via ToolExecutor."""

    def __init__(
        self,
        tool_name: str = "",
        executor: Any = None,
        metadata: AgentMetadata | None = None,
    ) -> None:
        if metadata is None:
            metadata = AgentMetadata(agent_id="", name=f"tool_{tool_name}", agent_type="tool")
        super().__init__(metadata)
        self.tool_name = tool_name
        self._executor = executor

    def set_executor(self, executor: Any) -> None:
        self._executor = executor

    def execute(self, context: dict[str, Any]) -> dict[str, Any]:
        if self._executor is None:
            return {"status": "ok", "tool": self.tool_name, "input": context}

        from app.tools.integration.executor import ToolExecutionRequest
        req = ToolExecutionRequest(
            tool_name=self.tool_name,
            params=context.get("params", {}),
            context={"agent_id": self.agent_id, **context.get("metadata", {})},
        )
        result = self._executor.execute(req)
        return {
            "status": "ok" if result.success else "error",
            "tool": self.tool_name,
            "success": result.success,
            "output": result.output,
            "error": result.error_message,
            "execution_time": result.execution_time,
            "trace_id": result.trace_id,
        }


class DevelopmentAgent(Agent):
    """Agent that performs development tasks like coding, testing."""

    def __init__(self, language: str = "python", metadata: AgentMetadata | None = None) -> None:
        if metadata is None:
            metadata = AgentMetadata(agent_id="", name="dev_agent", agent_type="development")
        super().__init__(metadata)
        self.language = language

    def execute(self, context: dict[str, Any]) -> dict[str, Any]:
        return {"status": "ok", "language": self.language, "task": context.get("task", "unknown")}


class DomainAgent(Agent):
    """Agent specialized in a specific domain."""

    def __init__(self, domain: str = "general", metadata: AgentMetadata | None = None) -> None:
        if metadata is None:
            metadata = AgentMetadata(agent_id="", name=f"domain_{domain}", agent_type="domain")
        super().__init__(metadata)
        self.domain = domain

    def execute(self, context: dict[str, Any]) -> dict[str, Any]:
        return {"status": "ok", "domain": self.domain, "query": context.get("query", "")}


class CompositeAgent(Agent):
    """Agent that composes multiple sub-agents."""

    def __init__(self, sub_agents: list[Agent] | None = None, metadata: AgentMetadata | None = None) -> None:
        if metadata is None:
            metadata = AgentMetadata(agent_id="", name="composite_agent", agent_type="composite")
        super().__init__(metadata)
        self.sub_agents = sub_agents or []

    def execute(self, context: dict[str, Any]) -> dict[str, Any]:
        results: list[dict[str, Any]] = []
        for agent in self.sub_agents:
            results.append(agent.execute({**context, "sub_agent": agent.agent_id}))
        return {"status": "ok", "sub_results": results, "count": len(results)}
