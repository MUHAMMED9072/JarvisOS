from __future__ import annotations

import enum
import json
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


class ToolStatus(enum.Enum):
    DESIGN = "design"
    BUILD = "build"
    SANDBOX = "sandbox"
    REVIEW = "review"
    APPROVED = "approved"
    INSTALLED = "installed"
    ACTIVE = "active"
    PAUSED = "paused"
    RETIRED = "retired"
    ARCHIVED = "archived"
    FAILED = "failed"


@dataclass
class ToolParameter:
    name: str = ""
    description: str = ""
    type: str = "string"
    required: bool = False
    default: Any = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "type": self.type,
            "required": self.required,
            "default": self.default,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ToolParameter:
        return cls(
            name=data.get("name", ""),
            description=data.get("description", ""),
            type=data.get("type", "string"),
            required=data.get("required", False),
            default=data.get("default"),
        )


@dataclass
class ToolMetadata:
    tool_id: str = ""
    name: str = ""
    version: str = "1.0.0"
    description: str = ""
    tool_type: str = "builtin"
    status: ToolStatus = ToolStatus.DESIGN
    parameters: list[ToolParameter] = field(default_factory=list)
    permissions_required: list[str] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)
    owner: str = ""
    tags: list[str] = field(default_factory=list)
    documentation: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_id": self.tool_id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "tool_type": self.tool_type,
            "status": self.status.value,
            "parameters": [p.to_dict() for p in self.parameters],
            "permissions_required": list(self.permissions_required),
            "capabilities": list(self.capabilities),
            "owner": self.owner,
            "tags": list(self.tags),
            "documentation": self.documentation,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ToolMetadata:
        params = [ToolParameter.from_dict(p) if isinstance(p, dict) else p for p in data.get("parameters", [])]
        status = ToolStatus(data["status"]) if "status" in data else ToolStatus.DESIGN
        return cls(
            tool_id=data.get("tool_id", ""),
            name=data.get("name", ""),
            version=data.get("version", "1.0.0"),
            description=data.get("description", ""),
            tool_type=data.get("tool_type", "builtin"),
            status=status,
            parameters=params,
            permissions_required=list(data.get("permissions_required", [])),
            capabilities=list(data.get("capabilities", [])),
            owner=data.get("owner", ""),
            tags=list(data.get("tags", [])),
            documentation=data.get("documentation", ""),
        )


@dataclass
class ToolResult:
    success: bool = False
    output: Any = None
    error_message: str = ""
    execution_time: float = 0.0
    stdout: str = ""
    stderr: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "output": self.output,
            "error_message": self.error_message,
            "execution_time": self.execution_time,
            "stdout": self.stdout,
            "stderr": self.stderr,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ToolResult:
        return cls(
            success=data.get("success", False),
            output=data.get("output"),
            error_message=data.get("error_message", ""),
            execution_time=data.get("execution_time", 0.0),
            stdout=data.get("stdout", ""),
            stderr=data.get("stderr", ""),
        )


class Tool(ABC):
    """Abstract base class for all tools in the JARVIS system.

    Lifecycle hooks are called in order:
      on_init -> on_start -> execute -> on_complete -> on_stop
    """

    def __init__(self, metadata: ToolMetadata) -> None:
        self.metadata = metadata
        self._lock = threading.RLock()

    @abstractmethod
    def execute(self, params: dict[str, Any]) -> ToolResult:
        ...

    @property
    def tool_id(self) -> str:
        return self.metadata.tool_id

    @property
    def name(self) -> str:
        return self.metadata.name

    @property
    def version(self) -> str:
        return self.metadata.version

    @property
    def status(self) -> ToolStatus:
        return self.metadata.status

    @status.setter
    def status(self, value: ToolStatus) -> None:
        self.metadata.status = value

    def validate_params(self, params: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        for param in self.metadata.parameters:
            if param.required and param.name not in params:
                errors.append(f"Missing required parameter: '{param.name}'")
        for key in params:
            found = any(p.name == key for p in self.metadata.parameters)
            if not found:
                errors.append(f"Unknown parameter: '{key}'")
        return errors

    def to_dict(self) -> dict[str, Any]:
        return self.metadata.to_dict()

    def documentation(self) -> str:
        md = self.metadata.documentation
        if not md:
            md = f"# {self.metadata.name}\n\n{self.metadata.description}\n\n"
            if self.metadata.parameters:
                md += "## Parameters\n\n| Name | Type | Required | Default | Description |\n"
                md += "|------|------|----------|---------|-------------|\n"
                for p in self.metadata.parameters:
                    md += f"| {p.name} | {p.type} | {p.required} | {p.default} | {p.description} |\n"
            if self.metadata.capabilities:
                md += f"\n**Capabilities**: {', '.join(self.metadata.capabilities)}\n"
            if self.metadata.permissions_required:
                md += f"\n**Permissions required**: {', '.join(self.metadata.permissions_required)}\n"
        return md

    def on_init(self) -> None:
        ...

    def on_start(self) -> None:
        ...

    def on_complete(self, result: ToolResult) -> None:
        ...

    def on_stop(self) -> None:
        ...

    def on_error(self, error: Exception) -> None:
        ...
