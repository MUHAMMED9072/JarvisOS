from __future__ import annotations

import json
from dataclasses import dataclass, field
from threading import Lock
from typing import Any


class ToolError(Exception):
    """Base exception for tool-related errors."""


class ToolValidationError(ToolError):
    """Raised when a tool definition fails validation."""


class DuplicateToolError(ToolError):
    """Raised when registering a tool with a name that already exists."""


class ToolNotFoundError(ToolError):
    """Raised when looking up a tool that does not exist."""


@dataclass(frozen=True)
class ToolDefinition:
    """Provider-independent definition of a callable tool.

    ``parameters`` must follow the JSON Schema specification
    (https://json-schema.org/) and describe the tool's input
    arguments.
    """
    name: str
    description: str
    parameters: dict  # JSON Schema object
    metadata: dict | None = None


@dataclass(frozen=True)
class ToolCall:
    """A tool invocation requested by an AI provider.

    ``arguments`` is a parsed dict of the tool's input parameters
    as returned by the provider SDK.
    """
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ToolResult:
    """The outcome of executing a single tool call.

    ``content`` holds the result payload (typically a string).
    ``error`` is ``None`` on success, or a human-readable
    description on failure.
    """
    id: str
    name: str
    content: str
    error: str | None = None


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _validate_json_schema(schema: dict) -> list[str]:
    """Basic sanity checks on a JSON Schema dict.

    Returns a list of error messages (empty = valid).
    """
    errors: list[str] = []
    if not isinstance(schema, dict):
        errors.append("parameters must be a dict (JSON Schema)")
        return errors
    if "type" not in schema:
        errors.append("parameters must specify 'type'")
    if schema.get("type") not in ("object",):
        errors.append("parameters 'type' should be 'object'")
    if "properties" not in schema:
        errors.append("parameters must specify 'properties'")
    elif not isinstance(schema["properties"], dict):
        errors.append("parameters 'properties' must be a dict")
    return errors


def validate_tool_definition(tool: ToolDefinition) -> None:
    """Validate *tool*, raising ``ToolValidationError`` on any issue."""
    if not tool.name or not isinstance(tool.name, str):
        raise ToolValidationError("Tool name must be a non-empty string")
    if not tool.description or not isinstance(tool.description, str):
        raise ToolValidationError("Tool description must be a non-empty string")
    if not isinstance(tool.parameters, dict):
        raise ToolValidationError("Tool parameters must be a dict (JSON Schema)")

    schema_errors = _validate_json_schema(tool.parameters)
    if schema_errors:
        raise ToolValidationError(
            f"Invalid JSON Schema for tool {tool.name!r}: "
            f"{'; '.join(schema_errors)}"
        )

    if tool.metadata is not None and not isinstance(tool.metadata, dict):
        raise ToolValidationError("Tool metadata must be a dict or None")


def validate_tool_call_arguments(tool: ToolDefinition, arguments: dict) -> list[str]:
    """Validate *arguments* against *tool*'s parameter schema.

    Returns a list of error messages (empty = valid).  Does **not**
    raise.
    """
    errors: list[str] = []
    properties = tool.parameters.get("properties", {})
    required = tool.parameters.get("required", [])

    for req in required:
        if req not in arguments:
            errors.append(f"Missing required parameter: {req!r}")

    for key, value in arguments.items():
        if key not in properties:
            continue
        prop = properties[key]
        expected_type = _json_type_to_python(prop.get("type", ""))
        if expected_type and not isinstance(value, expected_type):
            errors.append(
                f"Parameter {key!r} expected type "
                f"{prop.get('type', 'unknown')!r}, "
                f"got {type(value).__name__!r}"
            )
        enum_vals = prop.get("enum")
        if enum_vals is not None and value not in enum_vals:
            errors.append(
                f"Parameter {key!r} must be one of {enum_vals}, "
                f"got {value!r}"
            )

    return errors


def _json_type_to_python(json_type: str) -> type | None:
    mapping: dict[str, type] = {
        "string": str,
        "integer": int,
        "number": float | int,
        "boolean": bool,
        "array": list,
        "object": dict,
    }
    return mapping.get(json_type)


# ---------------------------------------------------------------------------
# Tool Registry
# ---------------------------------------------------------------------------


class ToolRegistry:
    """A thread-safe registry for ``ToolDefinition`` instances."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}
        self._lock = Lock()

    def register(self, tool: ToolDefinition) -> None:
        """Register *tool*.

        Raises ``DuplicateToolError`` if a tool with the same
        ``name`` is already registered.
        """
        validate_tool_definition(tool)
        with self._lock:
            if tool.name in self._tools:
                raise DuplicateToolError(
                    f"A tool named {tool.name!r} is already registered"
                )
            self._tools[tool.name] = tool

    def unregister(self, name: str) -> bool:
        """Remove the tool identified by *name*.

        Returns ``True`` if the tool was removed, ``False`` if
        it was not found.
        """
        with self._lock:
            return self._tools.pop(name, None) is not None

    def get(self, name: str) -> ToolDefinition | None:
        """Return the tool with *name*, or ``None``."""
        with self._lock:
            return self._tools.get(name)

    def has(self, name: str) -> bool:
        """Return ``True`` if a tool named *name* is registered."""
        with self._lock:
            return name in self._tools

    def list(self) -> list[ToolDefinition]:
        """Return every registered tool (ordered by registration)."""
        with self._lock:
            return list(self._tools.values())

    @property
    def count(self) -> int:
        """Return the number of registered tools."""
        with self._lock:
            return len(self._tools)
