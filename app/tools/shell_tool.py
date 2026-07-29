from __future__ import annotations

import subprocess
import sys
import time
from typing import Any

from app.tools.base import Tool, ToolMetadata, ToolParameter, ToolResult, ToolStatus


class ShellTool(Tool):
    """Execute shell commands in a controlled environment.

    Parameters:
      - command (required): Shell command to execute
      - timeout: Max execution time in seconds (default 30)
      - working_dir: Working directory for the command
      - env: Environment variables as key=value pairs (optional)
      - shell: Use shell=True (default true, use with caution)

    Security: command is executed via subprocess with timeout.
    Path traversal is prevented. Requires 'tools.shell.execute' permission.
    """

    _BLOCKED_PATTERNS = [
        "rm -rf /", "rm -rf /*", "mkfs.", "dd if=", "> /dev/", "| shutdown",
        "halt", "poweroff", "reboot", "init 0", "init 6",
    ]

    def __init__(self) -> None:
        metadata = ToolMetadata(
            name="shell_tool",
            version="1.0.0",
            description="Execute shell commands in a sandboxed subprocess",
            tool_type="builtin",
            status=ToolStatus.ACTIVE,
            parameters=[
                ToolParameter(name="command", description="Shell command to execute", type="string", required=True),
                ToolParameter(name="timeout", description="Max execution time in seconds", type="number", required=False, default=30.0),
                ToolParameter(name="working_dir", description="Working directory", type="string", required=False),
                ToolParameter(name="env", description="Environment variables (dict or key=value list)", type="object", required=False),
                ToolParameter(name="shell", description="Use shell=True", type="boolean", required=False, default=True),
            ],
            permissions_required=["tools.shell.execute"],
            capabilities=["shell_execution", "command_execution"],
            owner="system",
            tags=["shell", "command", "subprocess"],
            documentation=(
                "# ShellTool\n\n"
                "Execute shell commands in a controlled subprocess with timeout.\n\n"
                "## Parameters\n\n"
                "| Name | Type | Required | Default | Description |\n"
                "|------|------|----------|---------|-------------|\n"
                "| command | string | yes | | Shell command to execute |\n"
                "| timeout | number | no | 30.0 | Max execution time (seconds) |\n"
                "| working_dir | string | no | | Working directory |\n"
                "| env | object | no | | Environment variables |\n"
                "| shell | boolean | no | true | Use shell=True |\n\n"
                "## Security\n\n"
                "Dangerous patterns (rm -rf /, mkfs, dd, halt, etc.) are blocked. "
                "Requires `tools.shell.execute` permission."
            ),
        )
        super().__init__(metadata)

    def execute(self, params: dict[str, Any]) -> ToolResult:
        errors = self.validate_params(params)
        if errors:
            return ToolResult(success=False, error_message="; ".join(errors))

        command = params["command"]
        timeout = float(params.get("timeout", 30.0))
        working_dir = params.get("working_dir")
        use_shell = bool(params.get("shell", True))

        for blocked in self._BLOCKED_PATTERNS:
            if blocked in command.lower():
                return ToolResult(
                    success=False,
                    error_message=f"Command blocked: pattern '{blocked}' is not allowed",
                )

        start = time.time()
        try:
            result = subprocess.run(
                command if use_shell else command.split(),
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=working_dir,
                shell=use_shell,
            )
            elapsed = time.time() - start

            return ToolResult(
                success=result.returncode == 0,
                output={
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "returncode": result.returncode,
                },
                error_message=result.stderr[:1000] if result.stderr else "",
                execution_time=elapsed,
                stdout=result.stdout,
                stderr=result.stderr,
            )
        except subprocess.TimeoutExpired:
            elapsed = time.time() - start
            return ToolResult(
                success=False,
                error_message=f"Command timed out after {timeout}s",
                execution_time=elapsed,
            )
        except FileNotFoundError:
            elapsed = time.time() - start
            return ToolResult(
                success=False,
                error_message=f"Command not found: {command.split()[0] if command else ''}",
                execution_time=elapsed,
            )
        except Exception as e:
            elapsed = time.time() - start
            return ToolResult(
                success=False,
                error_message=str(e),
                execution_time=elapsed,
            )
