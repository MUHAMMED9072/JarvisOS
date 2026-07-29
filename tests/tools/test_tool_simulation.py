from __future__ import annotations

from app.tools.base import Tool, ToolMetadata, ToolResult, ToolStatus
from app.tools.integration.simulation import ToolSimulationIntegrator


class _SimTool(Tool):
    def __init__(self) -> None:
        meta = ToolMetadata(
            name="sim_tool", version="1.0.0", status=ToolStatus.ACTIVE,
            capabilities=["test"],
            permissions_required=["tools.test.execute"],
        )
        super().__init__(meta)

    def execute(self, params: dict) -> ToolResult:
        return ToolResult(success=True, output={})


class TestToolSimulationIntegrator:
    def test_simulate_without_pipeline(self) -> None:
        integ = ToolSimulationIntegrator()
        tool = _SimTool()
        result = integ.simulate_tool(tool)
        assert result["status"] == "skipped"
        assert "No simulation pipeline" in result["reason"]

    def test_health(self) -> None:
        integ = ToolSimulationIntegrator()
        h = integ.health()
        assert h["alive"]
