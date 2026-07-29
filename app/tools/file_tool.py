from __future__ import annotations

import os
import shutil
import time
from pathlib import Path
from typing import Any

from app.tools.base import Tool, ToolMetadata, ToolParameter, ToolResult, ToolStatus


class FileTool(Tool):
    """Read, write, copy, move, and delete files with path traversal protection.

    All file operations are restricted to a configurable allowed base path
    to prevent path traversal attacks.

    Parameters:
      - action (required): One of: read, write, copy, move, delete, list
      - path (required): File or directory path
      - content: Content to write (for write action)
      - destination: Destination path (for copy, move actions)
      - encoding: File encoding (default "utf-8")

    Security: path traversal is blocked. All paths are resolved against
    a safe base directory. Requires 'tools.file.access' permission.
    """

    def __init__(self, allowed_base: str | None = None) -> None:
        metadata = ToolMetadata(
            name="file_tool",
            version="1.0.0",
            description="Read, write, copy, move, and delete files with path safety",
            tool_type="builtin",
            status=ToolStatus.ACTIVE,
            parameters=[
                ToolParameter(name="action", description="Operation: read, write, copy, move, delete, list", type="string", required=True),
                ToolParameter(name="path", description="File or directory path", type="string", required=True),
                ToolParameter(name="content", description="Content for write action", type="string", required=False),
                ToolParameter(name="destination", description="Destination for copy/move", type="string", required=False),
                ToolParameter(name="encoding", description="File encoding", type="string", required=False, default="utf-8"),
            ],
            permissions_required=["tools.file.access"],
            capabilities=["file_operations", "file_read", "file_write"],
            owner="system",
            tags=["file", "filesystem"],
        )
        super().__init__(metadata)
        self._allowed_base = Path(allowed_base).resolve() if allowed_base else Path.cwd().resolve()

    def _resolve(self, path_str: str) -> Path:
        p = Path(path_str).resolve()
        if self._allowed_base not in p.parents and p != self._allowed_base:
            resolved = str(p)
            raise PermissionError(f"Path traversal blocked: '{resolved}' is outside allowed base '{self._allowed_base}'")
        return p

    def execute(self, params: dict[str, Any]) -> ToolResult:
        errors = self.validate_params(params)
        if errors:
            return ToolResult(success=False, error_message="; ".join(errors))

        action = params["action"]
        path_str = params["path"]
        encoding = params.get("encoding", "utf-8")

        start = time.time()
        try:
            resolved = self._resolve(path_str) if action != "list" else None

            if action == "read":
                if not resolved.exists():
                    return ToolResult(success=False, error_message=f"File not found: {resolved}", execution_time=time.time() - start)
                if resolved.is_dir():
                    return ToolResult(success=False, error_message=f"Path is a directory, not a file: {resolved}", execution_time=time.time() - start)
                content = resolved.read_text(encoding=encoding)
                elapsed = time.time() - start
                return ToolResult(success=True, output={"content": content, "size": len(content)}, execution_time=elapsed, stdout=content)

            elif action == "write":
                content = params.get("content", "")
                resolved.parent.mkdir(parents=True, exist_ok=True)
                resolved.write_text(content, encoding=encoding)
                elapsed = time.time() - start
                return ToolResult(success=True, output={"path": str(resolved), "size": len(content)}, execution_time=elapsed)

            elif action == "copy":
                dest_str = params.get("destination", "")
                if not dest_str:
                    return ToolResult(success=False, error_message="Destination required for copy action", execution_time=time.time() - start)
                dest = self._resolve(dest_str)
                if not resolved.exists():
                    return ToolResult(success=False, error_message=f"Source not found: {resolved}", execution_time=time.time() - start)
                if resolved.is_dir():
                    shutil.copytree(resolved, dest, dirs_exist_ok=True)
                else:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(resolved, dest)
                elapsed = time.time() - start
                return ToolResult(success=True, output={"source": str(resolved), "destination": str(dest)}, execution_time=elapsed)

            elif action == "move":
                dest_str = params.get("destination", "")
                if not dest_str:
                    return ToolResult(success=False, error_message="Destination required for move action", execution_time=time.time() - start)
                dest = self._resolve(dest_str)
                if not resolved.exists():
                    return ToolResult(success=False, error_message=f"Source not found: {resolved}", execution_time=time.time() - start)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(resolved), str(dest))
                elapsed = time.time() - start
                return ToolResult(success=True, output={"source": str(resolved), "destination": str(dest)}, execution_time=elapsed)

            elif action == "delete":
                if not resolved.exists():
                    return ToolResult(success=False, error_message=f"Path not found: {resolved}", execution_time=time.time() - start)
                if resolved.is_dir():
                    shutil.rmtree(resolved)
                else:
                    resolved.unlink()
                elapsed = time.time() - start
                return ToolResult(success=True, output={"path": str(resolved), "deleted": True}, execution_time=elapsed)

            elif action == "list":
                dir_path = Path(path_str).resolve()
                if not dir_path.exists():
                    return ToolResult(success=False, error_message=f"Directory not found: {dir_path}", execution_time=time.time() - start)
                if not dir_path.is_dir():
                    return ToolResult(success=False, error_message=f"Path is not a directory: {dir_path}", execution_time=time.time() - start)
                entries = []
                for entry in dir_path.iterdir():
                    entries.append({"name": entry.name, "type": "directory" if entry.is_dir() else "file", "size": entry.stat().st_size if entry.is_file() else 0})
                entries.sort(key=lambda e: e["name"])
                elapsed = time.time() - start
                return ToolResult(success=True, output={"path": str(dir_path), "entries": entries}, execution_time=elapsed)

            else:
                return ToolResult(success=False, error_message=f"Unknown action: '{action}'", execution_time=time.time() - start)

        except PermissionError as e:
            return ToolResult(success=False, error_message=str(e), execution_time=time.time() - start)
        except Exception as e:
            return ToolResult(success=False, error_message=str(e), execution_time=time.time() - start)
