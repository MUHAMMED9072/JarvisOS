"""JARVIS Evolution Engine - controlled generated-code execution.

The :class:`Sandbox` API intentionally remains small: ``Sandbox().run(source)``.
Internally it creates a disposable workspace, performs a conservative static safety
review, executes the code in its own process group, and records a report.
"""

from __future__ import annotations

import ast
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from app.core.logger import JarvisLogger

try:
    import psutil
except ImportError:  # pragma: no cover - retained for minimal installations
    psutil = None  # type: ignore[assignment]


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REPORT_DIRECTORY = PROJECT_ROOT / "data"


@dataclass
class SandboxResult:
    """Result returned from :meth:`Sandbox.run`.

    The original fields are preserved. The additional fields default to safe values
    so callers that construct this class themselves remain compatible.
    """

    success: bool
    returncode: int
    stdout: str
    stderr: str
    execution_time: float = 0.0
    cpu_time: float = 0.0
    peak_ram_bytes: int = 0
    timed_out: bool = False
    workspace: str | None = None
    security_violations: list[str] = field(default_factory=list)


class WorkspaceManager:
    """Create and reliably remove an isolated workspace for one execution."""

    def __init__(self, prefix: str = "jarvis-sandbox-") -> None:
        self.prefix = prefix
        self._lock = threading.RLock()

    def create_workspace(self) -> Path:
        with self._lock:
            workspace = Path(tempfile.mkdtemp(prefix=self.prefix))
            JarvisLogger.debug("Created sandbox workspace: %s", workspace)
            return workspace

    def cleanup_workspace(self, workspace: Path | None) -> None:
        if workspace is None:
            return
        with self._lock:
            try:
                shutil.rmtree(workspace, ignore_errors=False)
                JarvisLogger.debug("Removed sandbox workspace: %s", workspace)
            except FileNotFoundError:
                return
            except OSError:
                # Windows can temporarily retain a handle after process termination.
                JarvisLogger.warning("Could not fully remove sandbox workspace: %s", workspace, exc_info=True)


class SecurityValidator:
    """Conservative static validation for generated Python before it is run.

    This is a guardrail, not a security boundary. Untrusted code must still be run
    in an operating-system/container sandbox for strong isolation.
    """

    BLOCKED_IMPORTS = frozenset({
        "ctypes", "multiprocessing", "requests", "socket", "subprocess",
        "telnetlib", "urllib", "http", "ftplib", "ssl", "winreg",
    })
    BLOCKED_CALLS = frozenset({
        "breakpoint", "compile", "eval", "exec", "exit", "globals", "input",
        "locals", "__import__", "getattr",
    })
    BLOCKED_ATTRIBUTES = frozenset({
        "os.system", "os.popen", "os.remove", "os.rename", "os.replace",
        "os.rmdir", "os.unlink", "os.walk", "os.chmod", "os.chown",
        "os.environ", "pathlib.Path.unlink", "pathlib.Path.rmdir",
        "pathlib.Path.rename", "pathlib.Path.replace", "shutil.rmtree",
        "shutil.move", "shutil.copy", "sys.exit",
    })

    @staticmethod
    def _name(node: ast.AST) -> str | None:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            base = SecurityValidator._name(node.value)
            return f"{base}.{node.attr}" if base else node.attr
        return None

    @staticmethod
    def _check_path_traversal(node: ast.AST) -> list[str]:
        """Detect path traversal attempts in constant strings."""
        violations: list[str] = []
        for child in ast.walk(node):
            if isinstance(child, ast.Constant) and isinstance(child.value, str):
                val = child.value
                # Detect '..', absolute Unix paths, or Windows drive letters
                if val.startswith("..") or val.startswith("/") or (len(val) > 1 and val[1] == ":"):
                    violations.append(f"Path traversal or absolute path: '{val}'")
        return violations

    def validate(self, source: str) -> list[str]:
        """Return all static policy violations, including syntax errors."""
        try:
            tree = ast.parse(source, filename="sandbox.py")
        except SyntaxError as exc:
            return [f"Invalid Python syntax: {exc.msg} (line {exc.lineno})"]

        violations: list[str] = []
        # Resolve direct import aliases before checking calls. This prevents
        # ``from os import system as run; run(...)`` from evading the policy.
        aliases: dict[str, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    aliases[alias.asname or alias.name.split(".", 1)[0]] = alias.name
            elif isinstance(node, ast.ImportFrom) and node.module:
                for alias in node.names:
                    aliases[alias.asname or alias.name] = f"{node.module}.{alias.name}"

        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [alias.name for alias in node.names]
                if isinstance(node, ast.ImportFrom) and node.module:
                    names.append(node.module)
                for name in names:
                    root = name.split(".", 1)[0]
                    if root in self.BLOCKED_IMPORTS:
                        violations.append(f"Blocked import: {name}")
            elif isinstance(node, ast.Call):
                name = self._name(node.func)
                if name:
                    root, _, rest = name.partition(".")
                    if root in aliases:
                        name = aliases[root] + (f".{rest}" if rest else "")
                if name in self.BLOCKED_CALLS or name in self.BLOCKED_ATTRIBUTES:
                    violations.append(f"Blocked operation: {name}")
            elif isinstance(node, ast.Attribute):
                name = self._name(node)
                if name in self.BLOCKED_ATTRIBUTES:
                    violations.append(f"Blocked operation: {name}")

        violations.extend(self._check_path_traversal(tree))

        # Preserve report readability and prevent duplicate messages from AST walk.
        return list(dict.fromkeys(violations))


class ProcessRunner:
    """Run a Python script, enforce a timeout, and collect process metrics."""

    def __init__(self, timeout: float = 30.0, poll_interval: float = 0.05) -> None:
        self.timeout = timeout
        self.poll_interval = poll_interval

    @staticmethod
    def _kill_process_tree(process: subprocess.Popen[str]) -> None:
        if process.poll() is not None:
            return
        if psutil is not None:
            try:
                parent = psutil.Process(process.pid)
                children = parent.children(recursive=True)
                for child in children:
                    child.kill()
                parent.kill()
                _, alive = psutil.wait_procs(children + [parent], timeout=2)
                for child in alive:
                    child.kill()
                return
            except (psutil.Error, OSError):
                JarvisLogger.debug("psutil process-tree cleanup failed", exc_info=True)
        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    capture_output=True, text=True, timeout=5, check=False,
                )
            else:
                os.killpg(process.pid, signal.SIGKILL)
        except (OSError, subprocess.SubprocessError):
            process.kill()

    def run(self, script: Path, workspace: Path) -> tuple[int, str, str, float, float, int, bool]:
        command = [sys.executable, "-I", str(script)]
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        kwargs: dict[str, Any] = {"cwd": workspace, "stdout": subprocess.PIPE, "stderr": subprocess.PIPE,
                                  "text": True, "creationflags": creationflags}
        if os.name != "nt":
            kwargs["start_new_session"] = True

        started = time.monotonic()
        process = subprocess.Popen(command, **kwargs)
        monitored = psutil.Process(process.pid) if psutil is not None else None
        peak_ram = 0
        cpu_time = 0.0
        timed_out = False

        while process.poll() is None:
            elapsed = time.monotonic() - started
            if elapsed >= self.timeout:
                timed_out = True
                JarvisLogger.warning("Sandbox process %s timed out after %.2fs", process.pid, elapsed)
                self._kill_process_tree(process)
                break
            if monitored is not None:
                try:
                    memory = monitored.memory_info().rss
                    cpu = monitored.cpu_times()
                    peak_ram = max(peak_ram, memory)
                    cpu_time = max(cpu_time, cpu.user + cpu.system)
                except psutil.Error:
                    monitored = None
            time.sleep(self.poll_interval)

        stdout, stderr = process.communicate()
        elapsed = time.monotonic() - started
        if monitored is not None:
            try:
                memory = monitored.memory_info().rss
                cpu = monitored.cpu_times()
                peak_ram = max(peak_ram, memory)
                cpu_time = max(cpu_time, cpu.user + cpu.system)
            except psutil.Error:
                pass
        if timed_out:
            stderr = f"Execution timed out after {self.timeout:.2f} seconds.\n" + stderr
        return process.returncode or 0, stdout, stderr, elapsed, cpu_time, peak_ram, timed_out


class SandboxReporter:
    """Write human-readable and JSON execution reports atomically."""

    def __init__(self, report_directory: Path = DEFAULT_REPORT_DIRECTORY) -> None:
        self.report_directory = report_directory
        self._lock = threading.RLock()

    def write(self, result: SandboxResult) -> None:
        payload = asdict(result)
        payload["reported_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        text = "\n".join((
            "JARVIS OS Sandbox Report",
            f"Success: {result.success}", f"Return code: {result.returncode}",
            f"Timed out: {result.timed_out}", f"Execution time: {result.execution_time:.4f}s",
            f"CPU time: {result.cpu_time:.4f}s", f"Peak RAM: {result.peak_ram_bytes} bytes",
            f"Security violations: {', '.join(result.security_violations) or 'None'}",
            "", "STDOUT:", result.stdout, "", "STDERR:", result.stderr,
        ))
        with self._lock:
            self.report_directory.mkdir(parents=True, exist_ok=True)
            self._atomic_write(self.report_directory / "sandbox_report.txt", text)
            self._atomic_write(self.report_directory / "sandbox_report.json", json.dumps(payload, indent=2, ensure_ascii=False))

    @staticmethod
    def _atomic_write(destination: Path, content: str) -> None:
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(destination)


class Sandbox:
    """Execute generated Python code in an isolated temporary workspace."""

    def __init__(self, timeout: float = 30.0) -> None:
        self.workspace_manager = WorkspaceManager()
        self.security_validator = SecurityValidator()
        self.process_runner = ProcessRunner(timeout=timeout)
        self.reporter = SandboxReporter()
        self._lock = threading.RLock()

    def run(self, source: str) -> SandboxResult:
        """Validate, execute, report, and clean up a generated Python source string."""
        with self._lock:
            violations = self.security_validator.validate(source)
            if violations:
                result = SandboxResult(False, -1, "", "Generated code was blocked by security validation.",
                                       security_violations=violations)
                self.reporter.write(result)
                JarvisLogger.warning("Blocked generated sandbox code: %s", "; ".join(violations))
                return result

            workspace: Path | None = None
            try:
                workspace = self.workspace_manager.create_workspace()
                script = workspace / "sandbox.py"
                script.write_text(source, encoding="utf-8")
                values = self.process_runner.run(script, workspace)
                returncode, stdout, stderr, duration, cpu, ram, timed_out = values
                result = SandboxResult(returncode == 0 and not timed_out, returncode, stdout, stderr,
                                       duration, cpu, ram, timed_out, str(workspace))
                self.reporter.write(result)
                JarvisLogger.info("Sandbox run finished: success=%s returncode=%s duration=%.3fs", result.success, returncode, duration)
                return result
            except (OSError, subprocess.SubprocessError) as exc:
                JarvisLogger.exception("Sandbox execution setup failed")
                result = SandboxResult(False, -1, "", f"Sandbox execution failed: {exc}", workspace=str(workspace) if workspace else None)
                self.reporter.write(result)
                return result
            finally:
                self.workspace_manager.cleanup_workspace(workspace)


if __name__ == "__main__":
    sandbox = Sandbox()
    result = sandbox.run('print("Sandbox OK")')
    print(result)
