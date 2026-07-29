from __future__ import annotations

import pytest

from app.tools.shell_tool import ShellTool


class TestShellTool:
    def test_name_and_version(self) -> None:
        tool = ShellTool()
        assert tool.name == "shell_tool"
        assert tool.version == "1.0.0"

    def test_parameters_defined(self) -> None:
        tool = ShellTool()
        names = [p.name for p in tool.metadata.parameters]
        assert "command" in names
        assert "timeout" in names
        assert "working_dir" in names

    def test_required_params(self) -> None:
        tool = ShellTool()
        cmd_param = [p for p in tool.metadata.parameters if p.name == "command"][0]
        assert cmd_param.required is True

    def test_permissions(self) -> None:
        tool = ShellTool()
        assert "tools.shell.execute" in tool.metadata.permissions_required

    def test_capabilities(self) -> None:
        tool = ShellTool()
        assert "shell_execution" in tool.metadata.capabilities

    def test_validate_missing_command(self) -> None:
        tool = ShellTool()
        errors = tool.validate_params({})
        assert any("command" in e for e in errors)

    def test_validate_with_command(self) -> None:
        tool = ShellTool()
        errors = tool.validate_params({"command": "echo hello"})
        assert errors == []

    def test_execute_missing_command_returns_error(self) -> None:
        tool = ShellTool()
        result = tool.execute({})
        assert not result.success
        assert "command" in (result.error_message or "")

    def test_execute_simple_command(self) -> None:
        tool = ShellTool()
        result = tool.execute({"command": "echo hello", "timeout": 5.0})
        assert result.success
        assert "hello" in (result.stdout or "")

    def test_execute_failing_command(self) -> None:
        tool = ShellTool()
        result = tool.execute({"command": "exit 42", "timeout": 5.0})
        assert not result.success
        assert result.output.get("returncode") == 42

    def test_execute_returns_stdout_and_stderr(self) -> None:
        tool = ShellTool()
        result = tool.execute({"command": "echo out && >&2 echo err", "timeout": 5.0, "shell": True})
        assert "out" in result.stdout

    def test_blocked_patterns(self) -> None:
        tool = ShellTool()
        result = tool.execute({"command": "rm -rf /some/path", "timeout": 5.0})
        assert not result.success
        assert "blocked" in (result.error_message or "").lower()

    def test_blocked_pattern_halt(self) -> None:
        tool = ShellTool()
        result = tool.execute({"command": "halt", "timeout": 5.0})
        assert not result.success
        assert "blocked" in (result.error_message or "").lower()

    def test_blocked_pattern_mkfs(self) -> None:
        tool = ShellTool()
        result = tool.execute({"command": "mkfs.ext4 /dev/sda1", "timeout": 5.0})
        assert not result.success
        assert "blocked" in (result.error_message or "").lower()

    def test_timeout_returns_error(self) -> None:
        tool = ShellTool()
        result = tool.execute({"command": "powershell Start-Sleep -Seconds 10", "timeout": 1.0})
        assert not result.success

    def test_execution_time_positive(self) -> None:
        tool = ShellTool()
        result = tool.execute({"command": "echo test", "timeout": 5.0})
        assert result.execution_time > 0

    def test_command_not_found(self) -> None:
        tool = ShellTool()
        result = tool.execute({"command": "nonexistent_command_xyz123", "timeout": 5.0})
        assert not result.success

    def test_to_dict(self) -> None:
        tool = ShellTool()
        d = tool.to_dict()
        assert d["name"] == "shell_tool"

    def test_documentation(self) -> None:
        tool = ShellTool()
        docs = tool.documentation()
        assert "ShellTool" in docs
        assert "command" in docs

    def test_custom_working_dir(self) -> None:
        import tempfile, os
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = ShellTool()
            result = tool.execute({"command": "cmd /c echo %cd%" if os.name == "nt" else "pwd", "timeout": 5.0, "working_dir": tmpdir})
            assert result.success
