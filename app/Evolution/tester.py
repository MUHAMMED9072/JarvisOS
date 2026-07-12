"""
JARVIS Evolution Engine - Tester
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass


@dataclass
class TestResult:
    success: bool
    returncode: int
    stdout: str
    stderr: str


class TestRunner:
    """Run the project's pytest suite."""

    def run(self, target: str = "tests") -> TestResult:
        result = subprocess.run(
            ["python", "-m", "pytest", target],
            capture_output=True,
            text=True,
        )

        return TestResult(
            success=result.returncode == 0,
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
        )


if __name__ == "__main__":
    runner = TestRunner()
    result = runner.run()

    print("SUCCESS :", result.success)
    print(result.stdout)
    if result.stderr:
        print(result.stderr)
