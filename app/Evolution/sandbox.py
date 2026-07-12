"""
JARVIS Evolution Engine - Sandbox
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from dataclasses import dataclass


@dataclass
class SandboxResult:
    success: bool
    returncode: int
    stdout: str
    stderr: str


class Sandbox:
    """Execute generated Python code in an isolated temporary file."""

    def run(self, source: str) -> SandboxResult:
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "sandbox.py"
            script.write_text(source, encoding="utf-8")

            result = subprocess.run(
                ["python", str(script)],
                capture_output=True,
                text=True,
            )

            return SandboxResult(
                success=result.returncode == 0,
                returncode=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
            )


if __name__ == "__main__":
    sandbox = Sandbox()

    test_code = """
print("Sandbox OK")
"""

    result = sandbox.run(test_code)

    print(result)
