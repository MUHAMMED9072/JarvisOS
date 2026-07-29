from __future__ import annotations

from app.tools.python_tool import PythonTool


class TestPythonTool:
    def test_name_and_version(self) -> None:
        tool = PythonTool()
        assert tool.name == "python_tool"
        assert tool.version == "1.0.0"

    def test_status_active(self) -> None:
        tool = PythonTool()
        assert tool.status.value == "active"

    def test_parameters_defined(self) -> None:
        tool = PythonTool()
        assert len(tool.metadata.parameters) == 3
        names = [p.name for p in tool.metadata.parameters]
        assert "source" in names
        assert "filename" in names
        assert "timeout" in names

    def test_required_parameters(self) -> None:
        tool = PythonTool()
        source_param = [p for p in tool.metadata.parameters if p.name == "source"][0]
        assert source_param.required is True

    def test_permissions(self) -> None:
        tool = PythonTool()
        assert "tools.python.execute" in tool.metadata.permissions_required

    def test_capabilities(self) -> None:
        tool = PythonTool()
        assert "python_execution" in tool.metadata.capabilities
        assert "code_execution" in tool.metadata.capabilities

    def test_validate_missing_source(self) -> None:
        tool = PythonTool()
        errors = tool.validate_params({})
        assert any("source" in e for e in errors)

    def test_validate_unknown_param(self) -> None:
        tool = PythonTool()
        errors = tool.validate_params({"source": "print(1)", "unknown_param": True})
        assert any("unknown_param" in e for e in errors)

    def test_validate_all_correct(self) -> None:
        tool = PythonTool()
        errors = tool.validate_params({"source": "print(1)", "filename": "test.py", "timeout": 10.0})
        assert errors == []

    def test_execute_missing_source_returns_error(self) -> None:
        tool = PythonTool()
        result = tool.execute({})
        assert not result.success
        assert "source" in (result.error_message or "")

    def test_execute_simple_code(self) -> None:
        tool = PythonTool()
        result = tool.execute({"source": "print('hello')", "timeout": 5.0})
        assert result.success
        assert result.stdout is not None

    def test_execute_returns_stdout(self) -> None:
        tool = PythonTool()
        result = tool.execute({"source": "print('hello world')", "timeout": 5.0})
        assert result.success
        assert "hello world" in result.stdout

    def test_execute_syntax_error(self) -> None:
        tool = PythonTool()
        result = tool.execute({"source": "print(1/0)", "timeout": 5.0})
        assert not result.success

    def test_execute_math(self) -> None:
        tool = PythonTool()
        result = tool.execute({"source": "print(2 + 2)", "timeout": 5.0})
        assert result.success
        assert "4" in result.stdout

    def test_execute_multiline(self) -> None:
        tool = PythonTool()
        code = """
for i in range(3):
    print(f"line {i}")
"""
        result = tool.execute({"source": code, "timeout": 5.0})
        assert result.success
        for i in range(3):
            assert f"line {i}" in result.stdout

    def test_execution_time_positive(self) -> None:
        tool = PythonTool()
        result = tool.execute({"source": "print('timing')", "timeout": 5.0})
        assert result.execution_time > 0

    def test_to_dict(self) -> None:
        tool = PythonTool()
        d = tool.to_dict()
        assert d["name"] == "python_tool"
        assert d["tool_type"] == "builtin"

    def test_documentation(self) -> None:
        tool = PythonTool()
        docs = tool.documentation()
        assert "python_tool" in docs
        assert "source" in docs
        assert "filename" in docs

    def test_owner(self) -> None:
        tool = PythonTool()
        assert tool.metadata.owner == "system"

    def test_tags(self) -> None:
        tool = PythonTool()
        assert "python" in tool.metadata.tags
