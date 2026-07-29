from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.ads.test_generator import GeneratedTests
from app.evolution.sandbox import Sandbox as EvolutionSandbox, SandboxResult


class FailureType:
    COMPILE_ERROR = "compile_error"
    TEST_FAILURE = "test_failure"
    TIMEOUT = "timeout"
    RESOURCE_EXCEEDED = "resource_exceeded"
    SECURITY_VIOLATION = "security_violation"
    UNKNOWN = "unknown"


@dataclass
class ExecutionResult:
    """Result of executing generated artifact code or tests."""

    success: bool = False
    failure_type: str = ""
    stdout: str = ""
    stderr: str = ""
    execution_time: float = 0.0
    cpu_time: float = 0.0
    peak_ram_bytes: int = 0
    tests_passed: int = 0
    tests_failed: int = 0
    total_tests: int = 0
    security_violations: list[str] = field(default_factory=list)
    error_message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "failure_type": self.failure_type,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "execution_time": self.execution_time,
            "cpu_time": self.cpu_time,
            "peak_ram_bytes": self.peak_ram_bytes,
            "tests_passed": self.tests_passed,
            "tests_failed": self.tests_failed,
            "total_tests": self.total_tests,
            "security_violations": list(self.security_violations),
            "error_message": self.error_message,
        }


class AdsSandbox:
    """ADS sandbox executor wrapping the evolution Sandbox.

    Runs generated artifact code and tests in isolation,
    monitors resources, enforces timeouts, and classifies failures.
    """

    def __init__(self, timeout: float = 30.0, max_memory_mb: int = 512) -> None:
        self._sandbox = EvolutionSandbox(timeout=timeout)
        self._timeout = timeout
        self._max_memory_mb = max_memory_mb

    def run_code(self, source: str, filename: str = "artifact.py") -> ExecutionResult:
        """Execute a string of source code in the sandbox."""
        result = self._sandbox.run(source)
        return self._to_execution_result(result)

    def run_file(self, filepath: Path) -> ExecutionResult:
        """Execute a Python file in the sandbox."""
        source = filepath.read_text(encoding="utf-8")
        return self.run_code(source, filepath.name)

    def run_tests(self, tests: GeneratedTests) -> ExecutionResult:
        """Run generated test files and collect results.

        Writes test files to a temp directory and runs pytest.
        """
        import subprocess
        import sys
        import tempfile
        import os

        test_sources = {}
        for fname, code in tests.unit_tests.items():
            test_sources[fname] = code
        for fname, code in tests.integration_tests.items():
            test_sources[fname] = code
        for fname, code in tests.validation_tests.items():
            test_sources[fname] = code

        if not test_sources:
            return ExecutionResult(success=True, total_tests=0)

        tmpdir = tempfile.mkdtemp(prefix="ads_test_")
        try:
            for fname, code in test_sources.items():
                path = os.path.join(tmpdir, fname)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(code)

            start = time.time()
            try:
                proc = subprocess.run(
                    [sys.executable, "-m", "pytest", "--tb=short", "-q", tmpdir],
                    capture_output=True,
                    text=True,
                    timeout=self._timeout,
                )
                elapsed = time.time() - start
                stdout = proc.stdout
                stderr = proc.stderr
                returncode = proc.returncode

                passed = 0
                failed = 0
                import re
                for line in stdout.splitlines():
                    m = re.search(r"(\d+)\s+passed", line)
                    if m:
                        passed = int(m.group(1))
                    m = re.search(r"(\d+)\s+failed", line)
                    if m:
                        failed = int(m.group(1))

                return ExecutionResult(
                    success=returncode == 0,
                    stdout=stdout,
                    stderr=stderr or "",
                    execution_time=elapsed,
                    tests_passed=passed,
                    tests_failed=failed,
                    total_tests=passed + failed,
                    failure_type=FailureType.TEST_FAILURE if returncode != 0 else "",
                )

            except subprocess.TimeoutExpired:
                elapsed = time.time() - start
                return ExecutionResult(
                    success=False,
                    failure_type=FailureType.TIMEOUT,
                    error_message=f"Tests timed out after {self._timeout}s",
                    execution_time=elapsed,
                )
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    def classify_failure(self, result: ExecutionResult) -> str:
        """Classify the type of failure from an execution result."""
        if result.security_violations:
            return FailureType.SECURITY_VIOLATION
        if result.failure_type:
            return result.failure_type
        if not result.success and result.stderr:
            if "SyntaxError" in result.stderr or "ImportError" in result.stderr:
                return FailureType.COMPILE_ERROR
            if "timed out" in result.stderr.lower():
                return FailureType.TIMEOUT
        if result.peak_ram_bytes > self._max_memory_mb * 1024 * 1024:
            return FailureType.RESOURCE_EXCEEDED
        if result.tests_failed > 0:
            return FailureType.TEST_FAILURE
        return FailureType.UNKNOWN

    def _to_execution_result(self, sr: SandboxResult) -> ExecutionResult:
        ft = ""
        if sr.timed_out:
            ft = FailureType.TIMEOUT
        elif sr.security_violations:
            ft = FailureType.SECURITY_VIOLATION
        elif not sr.success:
            ft = FailureType.COMPILE_ERROR

        return ExecutionResult(
            success=sr.success,
            failure_type=ft,
            stdout=sr.stdout,
            stderr=sr.stderr,
            execution_time=sr.execution_time,
            cpu_time=sr.cpu_time,
            peak_ram_bytes=sr.peak_ram_bytes,
            security_violations=list(sr.security_violations),
            error_message=sr.stderr[:500] if sr.stderr else "",
        )

    def health(self) -> dict[str, Any]:
        return {
            "alive": True,
            "timeout": self._timeout,
            "max_memory_mb": self._max_memory_mb,
        }
