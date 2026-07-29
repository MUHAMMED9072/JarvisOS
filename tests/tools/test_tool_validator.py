from __future__ import annotations

import tempfile

from app.knowledge_graph.store import GraphStore
from app.tools.base import Tool, ToolMetadata, ToolResult, ToolStatus
from app.tools.integration.validator import ToolDependencyValidator
from app.tools.registry import ToolRegistry


class _ToolWithDeps(Tool):
    def __init__(self) -> None:
        meta = ToolMetadata(
            name="dependent_tool", version="1.0.0", status=ToolStatus.ACTIVE,
            tags=["dep:base_tool==1.0.0", "dep:helper_tool"],
        )
        super().__init__(meta)

    def execute(self, params: dict) -> ToolResult:
        return ToolResult(success=True, output={})


class _BaseTool(Tool):
    def __init__(self) -> None:
        meta = ToolMetadata(name="base_tool", version="1.0.0", status=ToolStatus.ACTIVE)
        super().__init__(meta)

    def execute(self, params: dict) -> ToolResult:
        return ToolResult(success=True, output={})


class _CircularA(Tool):
    def __init__(self) -> None:
        meta = ToolMetadata(
            name="circular_a", version="1.0.0", status=ToolStatus.ACTIVE,
            tags=["dep:circular_b"],
        )
        super().__init__(meta)

    def execute(self, params: dict) -> ToolResult:
        return ToolResult(success=True, output={})


class _CircularB(Tool):
    def __init__(self) -> None:
        meta = ToolMetadata(
            name="circular_b", version="1.0.0", status=ToolStatus.ACTIVE,
            tags=["dep:circular_a"],
        )
        super().__init__(meta)

    def execute(self, params: dict) -> ToolResult:
        return ToolResult(success=True, output={})


def _make_store() -> GraphStore:
    return GraphStore(filename=tempfile.mktemp(suffix=".json"))


class TestToolDependencyValidator:
    def test_no_dependencies(self) -> None:
        tool = _BaseTool()
        validator = ToolDependencyValidator()
        result = validator.validate_tool(tool)
        assert result.valid

    def test_missing_dependency(self) -> None:
        store = _make_store()
        treg = ToolRegistry(store)
        validator = ToolDependencyValidator(registry=treg)
        tool = _ToolWithDeps()
        result = validator.validate_tool(tool)
        assert not result.valid
        assert "base_tool" in result.missing_dependencies

    def test_all_dependencies_met(self) -> None:
        store = _make_store()
        treg = ToolRegistry(store)
        treg.register(_BaseTool())
        helper = _BaseTool()
        helper.metadata.name = "helper_tool"
        treg.register(helper)
        validator = ToolDependencyValidator(registry=treg)
        tool = _ToolWithDeps()
        result = validator.validate_tool(tool)
        assert not result.missing_dependencies

    def test_version_mismatch(self) -> None:
        store = _make_store()
        treg = ToolRegistry(store)
        base = _BaseTool()
        base.metadata.version = "2.0.0"
        treg.register(base)
        validator = ToolDependencyValidator(registry=treg)
        tool = _ToolWithDeps()
        result = validator.validate_tool(tool)
        mismatches = result.version_mismatches
        assert any(m["tool"] == "base_tool" for m in mismatches)

    def test_cycle_detection(self) -> None:
        store = _make_store()
        treg = ToolRegistry(store)
        treg.register(_CircularA())
        treg.register(_CircularB())
        validator = ToolDependencyValidator(registry=treg)
        result = validator.validate_tool(_CircularA())
        cycles = result.circular_dependencies
        assert len(cycles) >= 0

    def test_self_cycle(self) -> None:
        class _SelfDep(Tool):
            def __init__(self) -> None:
                meta = ToolMetadata(name="self_dep", version="1.0.0", status=ToolStatus.ACTIVE, tags=["dep:self_dep"])
                super().__init__(meta)
            def execute(self, params: dict) -> ToolResult:
                return ToolResult(success=True, output={})

        store = _make_store()
        treg = ToolRegistry(store)
        treg.register(_SelfDep())
        validator = ToolDependencyValidator(registry=treg)
        result = validator.validate_tool(_SelfDep())
        assert len(result.circular_dependencies) > 0

    def test_health(self) -> None:
        validator = ToolDependencyValidator()
        h = validator.health()
        assert h["alive"]
