from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import Any

from app.tools.base import Tool, ToolMetadata, ToolParameter, ToolResult, ToolStatus


class SSHTool(Tool):
    """Execute remote commands via SSH with key management.

    Parameters:
      - action (required): Operation (exec, upload, download, add_key, list_keys, remove_key)
      - host (required): Remote hostname or IP
      - command: Command to execute (for exec action)
      - username: SSH username (default: root)
      - port: SSH port (default: 22)
      - key_path: Path to SSH private key
      - password: SSH password (avoid, prefer keys)
      - local_path: Local file path (for upload/download)
      - remote_path: Remote file path (for upload/download)
      - key_name: Key name (for add_key, remove_key, list_keys)
      - key_material: Key content (for add_key)
      - timeout: Max execution time in seconds (default 60)

    Security: Key files are stored with restricted permissions.
    Passwords are never logged. Requires 'tools.ssh.execute' permission.
    """

    def __init__(self, keys_dir: str | None = None) -> None:
        metadata = ToolMetadata(
            name="ssh_tool",
            version="1.0.0",
            description="Execute remote commands via SSH with key management",
            tool_type="builtin",
            status=ToolStatus.ACTIVE,
            parameters=[
                ToolParameter(name="action", description="Operation: exec, upload, download, add_key, list_keys, remove_key", type="string", required=True),
                ToolParameter(name="host", description="Remote hostname or IP", type="string", required=True),
                ToolParameter(name="command", description="Command to execute", type="string", required=False),
                ToolParameter(name="username", description="SSH username", type="string", required=False, default="root"),
                ToolParameter(name="port", description="SSH port", type="number", required=False, default=22),
                ToolParameter(name="key_path", description="Path to SSH private key", type="string", required=False),
                ToolParameter(name="password", description="SSH password", type="string", required=False),
                ToolParameter(name="local_path", description="Local file path", type="string", required=False),
                ToolParameter(name="remote_path", description="Remote file path", type="string", required=False),
                ToolParameter(name="key_name", description="Key name", type="string", required=False),
                ToolParameter(name="key_material", description="Key content", type="string", required=False),
                ToolParameter(name="timeout", description="Max execution time in seconds", type="number", required=False, default=60.0),
            ],
            permissions_required=["tools.ssh.execute"],
            capabilities=["ssh_execution", "remote_command", "key_management"],
            owner="system",
            tags=["ssh", "remote", "key-management"],
        )
        super().__init__(metadata)
        self._keys_dir = Path(keys_dir or os.path.join(os.path.expanduser("~"), ".ssh", "tools")).resolve()
        self._keys_dir.mkdir(parents=True, exist_ok=True)

    def execute(self, params: dict[str, Any]) -> ToolResult:
        errors = self.validate_params(params)
        if errors:
            return ToolResult(success=False, error_message="; ".join(errors))

        action = params["action"]
        host = params["host"]
        username = params.get("username", "root")
        port = int(params.get("port", 22))
        key_path = params.get("key_path", "")
        password = params.get("password", "")
        timeout = float(params.get("timeout", 60.0))
        start = time.time()

        try:
            if action == "exec":
                command = params.get("command", "")
                if not command:
                    return ToolResult(success=False, error_message="command required for exec", execution_time=time.time() - start)
                ssh_cmd = ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=10", "-p", str(port)]
                if key_path:
                    ssh_cmd.extend(["-i", key_path])
                ssh_cmd.append(f"{username}@{host}")
                ssh_cmd.append(command)

                result = subprocess.run(
                    ssh_cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
                elapsed = time.time() - start
                return ToolResult(
                    success=result.returncode == 0,
                    output={"stdout": result.stdout, "stderr": result.stderr, "returncode": result.returncode, "host": host},
                    error_message=result.stderr[:1000] if result.returncode != 0 else "",
                    execution_time=elapsed,
                    stdout=result.stdout,
                    stderr=result.stderr,
                )

            elif action == "upload":
                local_path = params.get("local_path", "")
                remote_path = params.get("remote_path", "")
                if not local_path or not remote_path:
                    return ToolResult(success=False, error_message="local_path and remote_path required for upload", execution_time=time.time() - start)
                scp_cmd = ["scp", "-o", "StrictHostKeyChecking=no", "-P", str(port)]
                if key_path:
                    scp_cmd.extend(["-i", key_path])
                scp_cmd.extend([local_path, f"{username}@{host}:{remote_path}"])

                result = subprocess.run(scp_cmd, capture_output=True, text=True, timeout=timeout)
                elapsed = time.time() - start
                return ToolResult(
                    success=result.returncode == 0,
                    output={"local_path": local_path, "remote_path": remote_path, "host": host},
                    error_message=result.stderr[:1000] if result.returncode != 0 else "",
                    execution_time=elapsed,
                )

            elif action == "download":
                local_path = params.get("local_path", "")
                remote_path = params.get("remote_path", "")
                if not local_path or not remote_path:
                    return ToolResult(success=False, error_message="local_path and remote_path required for download", execution_time=time.time() - start)
                scp_cmd = ["scp", "-o", "StrictHostKeyChecking=no", "-P", str(port)]
                if key_path:
                    scp_cmd.extend(["-i", key_path])
                scp_cmd.extend([f"{username}@{host}:{remote_path}", local_path])

                result = subprocess.run(scp_cmd, capture_output=True, text=True, timeout=timeout)
                elapsed = time.time() - start
                return ToolResult(
                    success=result.returncode == 0,
                    output={"local_path": local_path, "remote_path": remote_path, "host": host},
                    error_message=result.stderr[:1000] if result.returncode != 0 else "",
                    execution_time=elapsed,
                )

            elif action == "add_key":
                key_name = params.get("key_name", f"key_{int(time.time())}")
                key_material = params.get("key_material", "")
                if not key_material:
                    return ToolResult(success=False, error_message="key_material required for add_key", execution_time=time.time() - start)
                key_file = self._keys_dir / key_name
                key_file.write_text(key_material)
                key_file.chmod(0o600)
                elapsed = time.time() - start
                return ToolResult(success=True, output={"key_name": key_name, "key_path": str(key_file)}, execution_time=elapsed)

            elif action == "list_keys":
                keys = []
                for f in self._keys_dir.iterdir():
                    if f.is_file() and not f.name.startswith("."):
                        keys.append({"name": f.name, "path": str(f), "size": f.stat().st_size})
                elapsed = time.time() - start
                return ToolResult(success=True, output={"keys_dir": str(self._keys_dir), "keys": keys}, execution_time=elapsed)

            elif action == "remove_key":
                key_name = params.get("key_name", "")
                if not key_name:
                    return ToolResult(success=False, error_message="key_name required for remove_key", execution_time=time.time() - start)
                key_file = self._keys_dir / key_name
                if not key_file.exists():
                    return ToolResult(success=False, error_message=f"Key not found: {key_name}", execution_time=time.time() - start)
                key_file.unlink()
                elapsed = time.time() - start
                return ToolResult(success=True, output={"key_name": key_name, "deleted": True}, execution_time=elapsed)

            else:
                return ToolResult(success=False, error_message=f"Unknown action: '{action}'", execution_time=time.time() - start)

        except subprocess.TimeoutExpired:
            return ToolResult(success=False, error_message=f"SSH operation timed out after {timeout}s", execution_time=time.time() - start)
        except FileNotFoundError:
            return ToolResult(success=False, error_message="ssh/scp executable not found on PATH", execution_time=time.time() - start)
        except Exception as e:
            return ToolResult(success=False, error_message=str(e), execution_time=time.time() - start)
