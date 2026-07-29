from __future__ import annotations

import time
from typing import Any

from app.ads.sandbox import AdsSandbox, FailureType
from app.tools.base import Tool, ToolMetadata, ToolParameter, ToolResult, ToolStatus


class PythonTool(Tool):
    """Execute Python code in a sandboxed environment.

    Parameters:
      - source (required): Python source code to execute
      - filename: Name to report in tracebacks (default "script.py")
      - timeout: Max execution time in seconds (default 30)

    Security: code is executed via AdsSandbox with timeout and
    resource limits. Security violations are caught and reported.
    Requires 'tools.python.execute' permission.
    """

    def __init__(self, sandbox: AdsSandbox | None = None) -> None:
        metadata = ToolMetadata(
            name="python_tool",
            version="1.0.0",
            description="Execute Python source code in a sandboxed environment",
            tool_type="builtin",
            status=ToolStatus.ACTIVE,
            parameters=[
                ToolParameter(name="source", description="Python source code to execute", type="string", required=True),
                ToolParameter(name="filename", description="Filename for traceback reporting", type="string", required=False, default="script.py"),
                ToolParameter(name="timeout", description="Max execution time in seconds", type="number", required=False, default=30.0),
            ],
            permissions_required=["tools.python.execute"],
            capabilities=["python_execution", "code_execution"],
            owner="system",
            tags=["python", "sandbox", "execution"],
        )
        super().__init__(metadata)
        self._sandbox = sandbox or AdsSandbox()

    def execute(self, params: dict[str, Any]) -> ToolResult:
        errors = self.validate_params(params)
        if errors:
            return ToolResult(success=False, error_message="; ".join(errors))

        source = params["source"]
        filename = params.get("filename", "script.py")
        timeout = float(params.get("timeout", 30.0))

        start = time.time()
        try:
            sandbox = AdsSandbox(timeout=timeout)
            result = sandbox.run_code(source, filename)
            elapsed = time.time() - start

            return ToolResult(
                success=result.success,
                output={"stdout": result.stdout, "stderr": result.stderr, "execution_time": result.execution_time, "cpu_time": result.cpu_time, "peak_ram_bytes": result.peak_ram_bytes},
                error_message=result.error_message if not result.success else "",
                execution_time=elapsed,
                stdout=result.stdout,
                stderr=result.stderr,
            )
        except Exception as e:
            elapsed = time.time() - start
            return ToolResult(
                success=False,
                error_message=str(e),
                execution_time=elapsed,
            )
