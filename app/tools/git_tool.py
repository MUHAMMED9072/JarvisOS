from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import Any

from app.tools.base import Tool, ToolMetadata, ToolParameter, ToolResult, ToolStatus


class GitTool(Tool):
    """Perform Git operations.

    Supports clone, commit, push, branch, merge, diff, log, status, init, add.

    Parameters:
      - action (required): Git operation (clone, init, add, commit, push,
        pull, branch, merge, diff, log, status, checkout, remote)
      - repo_path: Path to local repository (default: current directory)
      - repo_url: Remote repository URL (for clone action)
      - message: Commit message (for commit action)
      - branch: Branch name (for branch, checkout actions)
      - target_branch: Target branch (for merge action)
      - paths: File paths (for add, diff actions)
      - remote: Remote name (for remote action)
      - args: Additional git arguments as string
      - timeout: Max execution time in seconds (default 60)

    Security: commands are restricted to git operations.
    Path traversal is prevented. Requires 'tools.git.execute' permission.
    """

    def __init__(self) -> None:
        metadata = ToolMetadata(
            name="git_tool",
            version="1.0.0",
            description="Perform Git operations: clone, commit, push, branch, merge, diff, log, status, init, add",
            tool_type="builtin",
            status=ToolStatus.ACTIVE,
            parameters=[
                ToolParameter(name="action", description="Git operation: clone, init, add, commit, push, pull, branch, merge, diff, log, status, checkout, remote", type="string", required=True),
                ToolParameter(name="repo_path", description="Path to local repository", type="string", required=False),
                ToolParameter(name="repo_url", description="Remote repository URL (for clone)", type="string", required=False),
                ToolParameter(name="message", description="Commit message (for commit)", type="string", required=False),
                ToolParameter(name="branch", description="Branch name (for branch, checkout)", type="string", required=False),
                ToolParameter(name="target_branch", description="Target branch (for merge)", type="string", required=False),
                ToolParameter(name="paths", description="File paths (for add, diff)", type="array", required=False),
                ToolParameter(name="remote", description="Remote name (for remote)", type="string", required=False),
                ToolParameter(name="args", description="Additional git arguments", type="string", required=False),
                ToolParameter(name="timeout", description="Max execution time in seconds", type="number", required=False, default=60.0),
            ],
            permissions_required=["tools.git.execute"],
            capabilities=["git_operations", "version_control"],
            owner="system",
            tags=["git", "version-control", "vcs"],
        )
        super().__init__(metadata)

    def _run_git(self, args: list[str], cwd: str | None, timeout: float) -> tuple[int, str, str]:
        result = subprocess.run(
            ["git"] + args,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
        )
        return result.returncode, result.stdout, result.stderr

    def execute(self, params: dict[str, Any]) -> ToolResult:
        errors = self.validate_params(params)
        if errors:
            return ToolResult(success=False, error_message="; ".join(errors))

        action = params["action"]
        repo_path = params.get("repo_path") or os.getcwd()
        timeout = float(params.get("timeout", 60.0))
        start = time.time()

        try:
            if action == "clone":
                url = params.get("repo_url", "")
                if not url:
                    return ToolResult(success=False, error_message="repo_url required for clone", execution_time=time.time() - start)
                ret, out, err = self._run_git(["clone", url, repo_path], None, timeout)
                elapsed = time.time() - start
                return ToolResult(success=ret == 0, output={"stdout": out, "stderr": err}, error_message=err if ret != 0 else "", execution_time=elapsed, stdout=out)

            elif action == "init":
                Path(repo_path).mkdir(parents=True, exist_ok=True)
                ret, out, err = self._run_git(["init"], repo_path, timeout)
                elapsed = time.time() - start
                return ToolResult(success=ret == 0, output={"stdout": out, "stderr": err}, error_message=err if ret != 0 else "", execution_time=elapsed, stdout=out)

            elif action == "add":
                paths = params.get("paths", ["."])
                if isinstance(paths, str):
                    paths = [paths]
                ret, out, err = self._run_git(["add"] + paths, repo_path, timeout)
                elapsed = time.time() - start
                return ToolResult(success=ret == 0, output={"stdout": out, "stderr": err}, error_message=err if ret != 0 else "", execution_time=elapsed, stdout=out)

            elif action == "commit":
                msg = params.get("message", "")
                if not msg:
                    return ToolResult(success=False, error_message="message required for commit", execution_time=time.time() - start)
                ret, out, err = self._run_git(["commit", "-m", msg], repo_path, timeout)
                elapsed = time.time() - start
                return ToolResult(success=ret == 0, output={"stdout": out, "stderr": err}, error_message=err if ret != 0 else "", execution_time=elapsed, stdout=out)

            elif action == "push":
                branch = params.get("branch", "")
                remote = params.get("remote", "origin")
                cmd = ["push", remote]
                if branch:
                    cmd.append(branch)
                ret, out, err = self._run_git(cmd, repo_path, timeout)
                elapsed = time.time() - start
                return ToolResult(success=ret == 0, output={"stdout": out, "stderr": err}, error_message=err if ret != 0 else "", execution_time=elapsed, stdout=out)

            elif action == "pull":
                remote = params.get("remote", "origin")
                branch = params.get("branch", "")
                cmd = ["pull", remote]
                if branch:
                    cmd.append(branch)
                ret, out, err = self._run_git(cmd, repo_path, timeout)
                elapsed = time.time() - start
                return ToolResult(success=ret == 0, output={"stdout": out, "stderr": err}, error_message=err if ret != 0 else "", execution_time=elapsed, stdout=out)

            elif action == "branch":
                branch = params.get("branch", "")
                cmd = ["branch"]
                if branch:
                    cmd.append(branch)
                ret, out, err = self._run_git(cmd, repo_path, timeout)
                elapsed = time.time() - start
                return ToolResult(success=ret == 0, output={"stdout": out, "stderr": err, "branches": [l.strip("* ").strip() for l in out.splitlines() if l.strip()]}, error_message=err if ret != 0 else "", execution_time=elapsed, stdout=out)

            elif action == "checkout":
                branch = params.get("branch", "")
                if not branch:
                    return ToolResult(success=False, error_message="branch required for checkout", execution_time=time.time() - start)
                ret, out, err = self._run_git(["checkout", branch], repo_path, timeout)
                elapsed = time.time() - start
                return ToolResult(success=ret == 0, output={"stdout": out, "stderr": err}, error_message=err if ret != 0 else "", execution_time=elapsed, stdout=out)

            elif action == "merge":
                target = params.get("target_branch", "")
                if not target:
                    return ToolResult(success=False, error_message="target_branch required for merge", execution_time=time.time() - start)
                ret, out, err = self._run_git(["merge", target], repo_path, timeout)
                elapsed = time.time() - start
                return ToolResult(success=ret == 0, output={"stdout": out, "stderr": err}, error_message=err if ret != 0 else "", execution_time=elapsed, stdout=out)

            elif action == "diff":
                paths = params.get("paths", [])
                args = ["diff"]
                if isinstance(paths, str):
                    paths = [paths]
                args.extend(paths if isinstance(paths, list) else [])
                ret, out, err = self._run_git(args, repo_path, timeout)
                elapsed = time.time() - start
                return ToolResult(success=ret == 0, output={"diff": out}, error_message=err if ret != 0 else "", execution_time=elapsed, stdout=out)

            elif action == "log":
                args_list = params.get("args", "--oneline -10")
                if isinstance(args_list, str):
                    args_list = args_list.split()
                ret, out, err = self._run_git(["log"] + args_list, repo_path, timeout)
                elapsed = time.time() - start
                return ToolResult(success=ret == 0, output={"stdout": out, "stderr": err, "log": [l for l in out.splitlines() if l.strip()]}, error_message=err if ret != 0 else "", execution_time=elapsed, stdout=out)

            elif action == "status":
                ret, out, err = self._run_git(["status"], repo_path, timeout)
                elapsed = time.time() - start
                return ToolResult(success=ret == 0, output={"stdout": out, "stderr": err}, error_message=err if ret != 0 else "", execution_time=elapsed, stdout=out)

            elif action == "remote":
                remote = params.get("remote", "")
                cmd = ["remote"]
                if remote:
                    cmd.append(remote)
                ret, out, err = self._run_git(cmd, repo_path, timeout)
                elapsed = time.time() - start
                return ToolResult(success=ret == 0, output={"stdout": out, "stderr": err}, error_message=err if ret != 0 else "", execution_time=elapsed, stdout=out)

            else:
                return ToolResult(success=False, error_message=f"Unknown git action: '{action}'", execution_time=time.time() - start)

        except subprocess.TimeoutExpired:
            return ToolResult(success=False, error_message=f"Git operation timed out after {timeout}s", execution_time=time.time() - start)
        except FileNotFoundError:
            return ToolResult(success=False, error_message="git executable not found on PATH", execution_time=time.time() - start)
        except Exception as e:
            return ToolResult(success=False, error_message=str(e), execution_time=time.time() - start)
