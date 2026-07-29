from __future__ import annotations

from typing import Any

import pytest

from app.tools.base import Tool, ToolMetadata, ToolParameter, ToolResult, ToolStatus


# ---------------------------------------------------------------------------
# ToolParameter
# ---------------------------------------------------------------------------

class TestToolParameter:
    def test_defaults(self) -> None:
        p = ToolParameter()
        assert p.name == ""
        assert p.type == "string"
        assert p.required is False

    def test_to_dict(self) -> None:
        p = ToolParameter(name="src", description="Source code", type="string", required=True, default="print(1)")
        d = p.to_dict()
        assert d["name"] == "src"
        assert d["required"] is True
        assert d["default"] == "print(1)"

    def test_from_dict(self) -> None:
        d = {"name": "x", "type": "number", "required": True, "default": 42}
        p = ToolParameter.from_dict(d)
        assert p.name == "x"
        assert p.type == "number"
        assert p.default == 42

    def test_roundtrip(self) -> None:
        p = ToolParameter(name="timeout", type="number", required=False, default=30.0)
        assert ToolParameter.from_dict(p.to_dict()) == p


# ---------------------------------------------------------------------------
# ToolMetadata
# ---------------------------------------------------------------------------

class TestToolMetadata:
    def test_defaults(self) -> None:
        m = ToolMetadata()
        assert m.name == ""
        assert m.version == "1.0.0"
        assert m.status == ToolStatus.DESIGN
        assert m.parameters == []
        assert m.capabilities == []

    def test_to_dict(self) -> None:
        m = ToolMetadata(
            name="test_tool",
            version="2.0.0",
            description="A test",
            capabilities=["execution"],
            parameters=[ToolParameter(name="x", type="string", required=True)],
            permissions_required=["perm.a"],
        )
        d = m.to_dict()
        assert d["name"] == "test_tool"
        assert d["version"] == "2.0.0"
        assert d["capabilities"] == ["execution"]
        assert d["permissions_required"] == ["perm.a"]
        assert len(d["parameters"]) == 1

    def test_from_dict(self) -> None:
        d = {
            "name": "restored",
            "version": "3.0.0",
            "status": "active",
            "capabilities": ["http"],
            "permissions_required": ["network.http"],
            "parameters": [{"name": "url", "type": "string", "required": True}],
        }
        m = ToolMetadata.from_dict(d)
        assert m.name == "restored"
        assert m.version == "3.0.0"
        assert m.status == ToolStatus.ACTIVE
        assert m.capabilities == ["http"]

    def test_roundtrip(self) -> None:
        m = ToolMetadata(
            name="roundtrip",
            version="1.0.0",
            description="test",
            tool_type="builtin",
            status=ToolStatus.ACTIVE,
            parameters=[ToolParameter(name="p1", type="string")],
            permissions_required=["perm.x"],
            capabilities=["cap.y"],
            owner="system",
            tags=["tag1"],
        )
        m2 = ToolMetadata.from_dict(m.to_dict())
        assert m2.name == m.name
        assert m2.version == m.version
        assert m2.status == m.status
        assert m2.parameters[0].name == "p1"
        assert m2.permissions_required == ["perm.x"]
        assert m2.capabilities == ["cap.y"]
        assert m2.owner == "system"
        assert m2.tags == ["tag1"]

    def test_documentation_field(self) -> None:
        m = ToolMetadata(documentation="# Custom Doc")
        assert m.documentation == "# Custom Doc"


# ---------------------------------------------------------------------------
# ToolResult
# ---------------------------------------------------------------------------

class TestToolResult:
    def test_defaults(self) -> None:
        r = ToolResult()
        assert r.success is False
        assert r.output is None
        assert r.execution_time == 0.0

    def test_success_result(self) -> None:
        r = ToolResult(success=True, output={"result": 42}, execution_time=0.5)
        assert r.success
        assert r.output["result"] == 42

    def test_error_result(self) -> None:
        r = ToolResult(success=False, error_message="Something went wrong")
        assert not r.success
        assert "wrong" in r.error_message

    def test_to_dict(self) -> None:
        r = ToolResult(success=True, output="ok", execution_time=1.0, stdout="out", stderr="err")
        d = r.to_dict()
        assert d["success"] is True
        assert d["output"] == "ok"
        assert d["stdout"] == "out"

    def test_from_dict(self) -> None:
        d = {"success": True, "output": "data", "execution_time": 0.1, "stdout": "hello"}
        r = ToolResult.from_dict(d)
        assert r.success
        assert r.output == "data"
        assert r.execution_time == 0.1

    def test_roundtrip(self) -> None:
        r = ToolResult(success=True, output=[1, 2, 3], error_message="", execution_time=0.2, stdout="a", stderr="b")
        r2 = ToolResult.from_dict(r.to_dict())
        assert r2.success == r.success
        assert r2.output == r.output
        assert r2.execution_time == r.execution_time


# ---------------------------------------------------------------------------
# Tool base class
# ---------------------------------------------------------------------------

class _ConcreteTool(Tool):
    def execute(self, params: dict[str, Any]) -> ToolResult:
        return ToolResult(success=True, output=params)


class TestTool:
    def test_abstract_cannot_instantiate(self) -> None:
        with pytest.raises(TypeError):
            Tool(ToolMetadata())  # type: ignore[abstract]

    def test_concrete_instantiation(self) -> None:
        tool = _ConcreteTool(ToolMetadata(name="concrete", version="1.0.0"))
        assert tool.name == "concrete"
        assert tool.version == "1.0.0"

    def test_execute_returns_result(self) -> None:
        tool = _ConcreteTool(ToolMetadata(name="t"))
        result = tool.execute({"a": 1})
        assert result.success
        assert result.output == {"a": 1}

    def test_properties_delegate_to_metadata(self) -> None:
        md = ToolMetadata(name="prop_test", tool_id="id_123", version="2.0.0", status=ToolStatus.ACTIVE)
        tool = _ConcreteTool(md)
        assert tool.tool_id == "id_123"
        assert tool.name == "prop_test"
        assert tool.version == "2.0.0"
        assert tool.status == ToolStatus.ACTIVE

    def test_status_setter(self) -> None:
        tool = _ConcreteTool(ToolMetadata(name="s"))
        tool.status = ToolStatus.ACTIVE
        assert tool.status == ToolStatus.ACTIVE

    def test_validate_params_missing_required(self) -> None:
        md = ToolMetadata(
            name="v",
            parameters=[
                ToolParameter(name="required_param", type="string", required=True),
                ToolParameter(name="optional_param", type="number", required=False),
            ],
        )
        tool = _ConcreteTool(md)
        errors = tool.validate_params({"optional_param": 42})
        assert len(errors) == 1
        assert "required_param" in errors[0]

    def test_validate_params_unknown(self) -> None:
        md = ToolMetadata(name="v2", parameters=[ToolParameter(name="known", type="string")])
        tool = _ConcreteTool(md)
        errors = tool.validate_params({"known": "ok", "unknown": "bad"})
        assert any("unknown" in e for e in errors)

    def test_validate_params_all_valid(self) -> None:
        md = ToolMetadata(
            name="v3",
            parameters=[
                ToolParameter(name="a", type="string", required=True),
                ToolParameter(name="b", type="number", required=False),
            ],
        )
        tool = _ConcreteTool(md)
        errors = tool.validate_params({"a": "hello", "b": 42})
        assert errors == []

    def test_to_dict(self) -> None:
        md = ToolMetadata(name="dict_test", tool_id="d1", version="3.0.0")
        tool = _ConcreteTool(md)
        d = tool.to_dict()
        assert d["name"] == "dict_test"
        assert d["tool_id"] == "d1"

    def test_lifecycle_hooks_noop(self) -> None:
        tool = _ConcreteTool(ToolMetadata(name="lifecycle"))
        tool.on_init()
        tool.on_start()
        tool.on_complete(ToolResult(success=True))
        tool.on_stop()
        tool.on_error(Exception("test"))
        assert True

    def test_documentation_generated(self) -> None:
        md = ToolMetadata(
            name="doc_test",
            description="A documented tool",
            parameters=[ToolParameter(name="param1", type="string", description="A param")],
            capabilities=["cap1"],
            permissions_required=["perm1"],
        )
        tool = _ConcreteTool(md)
        docs = tool.documentation()
        assert "doc_test" in docs
        assert "param1" in docs
        assert "cap1" in docs
        assert "perm1" in docs

    def test_documentation_custom(self) -> None:
        md = ToolMetadata(documentation="# Custom Override")
        tool = _ConcreteTool(md)
        assert tool.documentation() == "# Custom Override"

    def test_validate_params_no_params(self) -> None:
        tool = _ConcreteTool(ToolMetadata(name="no_params"))
        assert tool.validate_params({}) == []
        assert tool.validate_params({"unexpected": 1}) == ["Unknown parameter: 'unexpected'"]

    def test_lock_available(self) -> None:
        tool = _ConcreteTool(ToolMetadata(name="locked"))
        with tool._lock:
            assert True


# ---------------------------------------------------------------------------
# ToolStatus enum
# ---------------------------------------------------------------------------

class TestToolStatus:
    def test_all_values_present(self) -> None:
        values = [s.value for s in ToolStatus]
        expected = [
            "design", "build", "sandbox", "review", "approved",
            "installed", "active", "paused", "retired", "archived", "failed",
        ]
        assert values == expected

    def test_conversion_from_string(self) -> None:
        assert ToolStatus("active") == ToolStatus.ACTIVE
        assert ToolStatus("paused") == ToolStatus.PAUSED
