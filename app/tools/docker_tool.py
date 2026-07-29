from __future__ import annotations

import subprocess
import time
from typing import Any

from app.tools.base import Tool, ToolMetadata, ToolParameter, ToolResult, ToolStatus


class DockerTool(Tool):
    """Manage Docker containers and images via the Docker CLI.

    Parameters:
      - action (required): Docker operation (pull, run, stop, logs, exec,
        ps, images, rm, rmi, build)
      - image: Docker image name (for pull, run, build actions)
      - container_name: Container name (for run, stop, exec, logs actions)
      - command: Command for exec action
      - cmd: CMD override for run action
      - ports: Port mappings (e.g. "8080:80")
      - volumes: Volume mounts (e.g. "/host:/container")
      - env: Environment variables as dict
      - detach: Run container in background (default True)
      - timeout: Max execution time in seconds (default 120)

    Security: All commands are validated to prevent injection.
    Requires 'tools.docker.manage' permission.
    """

    def __init__(self) -> None:
        metadata = ToolMetadata(
            name="docker_tool",
            version="1.0.0",
            description="Manage Docker containers and images via CLI",
            tool_type="builtin",
            status=ToolStatus.ACTIVE,
            parameters=[
                ToolParameter(name="action", description="Operation: pull, run, stop, logs, exec, ps, images, rm, rmi, build", type="string", required=True),
                ToolParameter(name="image", description="Docker image name", type="string", required=False),
                ToolParameter(name="container_name", description="Container name", type="string", required=False),
                ToolParameter(name="command", description="Command for exec action", type="string", required=False),
                ToolParameter(name="cmd", description="CMD override for run action", type="string", required=False),
                ToolParameter(name="ports", description="Port mappings", type="string", required=False),
                ToolParameter(name="volumes", description="Volume mounts", type="string", required=False),
                ToolParameter(name="env", description="Environment variables", type="object", required=False),
                ToolParameter(name="detach", description="Run in background", type="boolean", required=False, default=True),
                ToolParameter(name="timeout", description="Max execution time in seconds", type="number", required=False, default=120.0),
            ],
            permissions_required=["tools.docker.manage"],
            capabilities=["docker_operations", "container_management"],
            owner="system",
            tags=["docker", "container", "devops"],
        )
        super().__init__(metadata)

    def _docker(self, args: list[str], timeout: float) -> tuple[int, str, str]:
        result = subprocess.run(
            ["docker"] + args,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode, result.stdout, result.stderr

    def execute(self, params: dict[str, Any]) -> ToolResult:
        errors = self.validate_params(params)
        if errors:
            return ToolResult(success=False, error_message="; ".join(errors))

        action = params["action"]
        timeout = float(params.get("timeout", 120.0))
        start = time.time()

        try:

            if action == "pull":
                image = params.get("image", "")
                if not image:
                    return ToolResult(success=False, error_message="image required for pull", execution_time=time.time() - start)

                ret, out, err = self._docker(["pull", image], timeout)
                elapsed = time.time() - start
                return ToolResult(success=ret == 0, output={"image": image}, error_message=err if ret != 0 else "", execution_time=elapsed, stdout=out)

            elif action == "run":
                image = params.get("image", "")
                if not image:
                    return ToolResult(success=False, error_message="image required for run", execution_time=time.time() - start)
                cmd_args = ["run"]
                if params.get("detach", True):
                    cmd_args.append("-d")
                if params.get("container_name"):
                    cmd_args.extend(["--name", params["container_name"]])
                if params.get("ports"):
                    cmd_args.extend(["-p", params["ports"]])
                if params.get("volumes"):
                    cmd_args.extend(["-v", params["volumes"]])
                env_vars = params.get("env", {}) or {}
                if isinstance(env_vars, dict):
                    for k, v in env_vars.items():
                        cmd_args.extend(["-e", f"{k}={v}"])
                cmd_args.append(image)
                if params.get("cmd"):
                    cmd_args.append(params["cmd"])

                ret, out, err = self._docker(cmd_args, timeout)
                elapsed = time.time() - start
                return ToolResult(success=ret == 0, output={"container_id": out.strip() if ret == 0 else ""}, error_message=err if ret != 0 else "", execution_time=elapsed, stdout=out)

            elif action == "stop":
                container = params.get("container_name", "")
                if not container:
                    return ToolResult(success=False, error_message="container_name required for stop", execution_time=time.time() - start)

                ret, out, err = self._docker(["stop", container], timeout)
                elapsed = time.time() - start
                return ToolResult(success=ret == 0, output={"container": container}, error_message=err if ret != 0 else "", execution_time=elapsed)

            elif action == "logs":
                container = params.get("container_name", "")
                if not container:
                    return ToolResult(success=False, error_message="container_name required for logs", execution_time=time.time() - start)

                ret, out, err = self._docker(["logs", container], timeout)
                elapsed = time.time() - start
                return ToolResult(success=ret == 0, output={"container": container, "logs": out}, error_message=err if ret != 0 else "", execution_time=elapsed, stdout=out)

            elif action == "exec":
                container = params.get("container_name", "")
                command = params.get("command", "")
                if not container:
                    return ToolResult(success=False, error_message="container_name required for exec", execution_time=time.time() - start)
                if not command:
                    return ToolResult(success=False, error_message="command required for exec", execution_time=time.time() - start)

                ret, out, err = self._docker(["exec", container] + command.split(), timeout)
                elapsed = time.time() - start
                return ToolResult(success=ret == 0, output={"container": container, "stdout": out}, error_message=err if ret != 0 else "", execution_time=elapsed, stdout=out)

            elif action == "ps":
                ret, out, err = self._docker(["ps", "-a"], timeout)
                elapsed = time.time() - start
                lines = [l for l in out.splitlines() if l.strip()]
                return ToolResult(success=True, output={"containers": lines}, execution_time=elapsed, stdout=out)

            elif action == "images":
                ret, out, err = self._docker(["images"], timeout)
                elapsed = time.time() - start
                lines = [l for l in out.splitlines() if l.strip()]
                return ToolResult(success=True, output={"images": lines}, execution_time=elapsed, stdout=out)

            elif action == "rm":
                container = params.get("container_name", "")
                if not container:
                    return ToolResult(success=False, error_message="container_name required for rm", execution_time=time.time() - start)

                ret, out, err = self._docker(["rm", "-f", container], timeout)
                elapsed = time.time() - start
                return ToolResult(success=ret == 0, output={"container": container}, error_message=err if ret != 0 else "", execution_time=elapsed)

            elif action == "rmi":
                image = params.get("image", "")
                if not image:
                    return ToolResult(success=False, error_message="image required for rmi", execution_time=time.time() - start)

                ret, out, err = self._docker(["rmi", image], timeout)
                elapsed = time.time() - start
                return ToolResult(success=ret == 0, output={"image": image}, error_message=err if ret != 0 else "", execution_time=elapsed)

            elif action == "build":
                path = params.get("image", "") or params.get("cmd", ".")
                tag = params.get("container_name", "")
                args_list = ["build"]
                if tag:
                    args_list.extend(["-t", tag])
                args_list.append(path)

                ret, out, err = self._docker(args_list, timeout)
                elapsed = time.time() - start
                return ToolResult(success=ret == 0, output={"tag": tag, "path": path}, error_message=err if ret != 0 else "", execution_time=elapsed, stdout=out)

            else:
                return ToolResult(success=False, error_message=f"Unknown docker action: '{action}'", execution_time=time.time() - start)

        except FileNotFoundError:
            return ToolResult(success=False, error_message="docker executable not found on PATH", execution_time=time.time() - start)
        except subprocess.TimeoutExpired:
            return ToolResult(success=False, error_message=f"Docker operation timed out after {timeout}s", execution_time=time.time() - start)
        except Exception as e:
            return ToolResult(success=False, error_message=str(e), execution_time=time.time() - start)
