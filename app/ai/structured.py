from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


class StructuredError(Exception):
    """Base exception for structured output errors."""


class SchemaValidationError(StructuredError):
    """Raised when a schema definition is invalid."""


class OutputValidationError(StructuredError):
    """Raised when a response fails schema validation."""


class OutputParseError(StructuredError):
    """Raised when a response cannot be parsed as valid JSON."""


@dataclass(frozen=True)
class StructuredSchema:
    """A named JSON Schema for structured output.

    ``schema`` must follow the JSON Schema specification and
    describe the expected output structure.
    """
    name: str
    schema: dict
    metadata: dict | None = None


@dataclass(frozen=True)
class StructuredResult:
    """The result of parsing and validating structured output.

    ``data`` holds the parsed JSON value (typically a ``dict``).
    ``valid`` is ``True`` when the output passed all schema checks.
    ``errors`` lists any validation failures.
    ``raw`` is the original response text.
    """
    data: dict | list
    schema_name: str
    valid: bool
    errors: list[str] = field(default_factory=list)
    raw: str = ""


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------


def _validate_json_schema_obj(schema: dict) -> list[str]:
    """Basic sanity checks on a JSON Schema dict.

    Returns a list of error messages (empty = valid).
    """
    errors: list[str] = []
    if not isinstance(schema, dict):
        errors.append("Schema must be a dict")
        return errors
    if "type" not in schema:
        errors.append("Schema must specify 'type'")
    elif schema.get("type") not in ("object", "array", "string", "number", "integer", "boolean"):
        errors.append(f"Schema 'type' must be a valid JSON type, got {schema.get('type')!r}")
    return errors


def validate_structured_schema(schema: StructuredSchema) -> None:
    """Validate *schema*, raising ``SchemaValidationError`` on any issue."""
    if not schema.name or not isinstance(schema.name, str):
        raise SchemaValidationError("Schema name must be a non-empty string")
    if not isinstance(schema.schema, dict):
        raise SchemaValidationError("Schema definition must be a dict")
    obj_errors = _validate_json_schema_obj(schema.schema)
    if obj_errors:
        raise SchemaValidationError(
            f"Invalid schema {schema.name!r}: {'; '.join(obj_errors)}"
        )
    if schema.metadata is not None and not isinstance(schema.metadata, dict):
        raise SchemaValidationError("Schema metadata must be a dict or None")


# ---------------------------------------------------------------------------
# Parsing and validation
# ---------------------------------------------------------------------------


def _validate_value(value: Any, schema: dict, path: str = "") -> list[str]:
    """Recursively validate *value* against a JSON Schema fragment."""
    errors: list[str] = []

    schema_type = schema.get("type")
    if schema_type == "object":
        if not isinstance(value, dict):
            errors.append(f"{path}: expected object, got {type(value).__name__!r}")
            return errors
        required = schema.get("required", [])
        for req in required:
            if req not in value:
                errors.append(f"{path}.{req}: missing required field")
        properties = schema.get("properties", {})
        for key, prop_schema in properties.items():
            if key in value:
                sub_path = f"{path}.{key}" if path else key
                errors.extend(_validate_value(value[key], prop_schema, sub_path))
    elif schema_type == "array":
        if not isinstance(value, list):
            errors.append(f"{path}: expected array, got {type(value).__name__!r}")
            return errors
        items_schema = schema.get("items", {})
        for i, item in enumerate(value):
            errors.extend(_validate_value(item, items_schema, f"{path}[{i}]"))
    elif schema_type in ("string",):
        if not isinstance(value, str):
            errors.append(f"{path}: expected string, got {type(value).__name__!r}")
        enum_vals = schema.get("enum")
        if enum_vals is not None and value not in enum_vals:
            errors.append(f"{path}: must be one of {enum_vals}, got {value!r}")
    elif schema_type in ("number", "integer"):
        if not isinstance(value, (int, float)):
            errors.append(f"{path}: expected {schema_type}, got {type(value).__name__!r}")
        if schema_type == "integer" and isinstance(value, float) and not value.is_integer():
            errors.append(f"{path}: expected integer, got float")
    elif schema_type == "boolean":
        if not isinstance(value, bool):
            errors.append(f"{path}: expected boolean, got {type(value).__name__!r}")

    return errors


def parse_structured_output(
    raw_text: str,
    schema: StructuredSchema,
) -> StructuredResult:
    """Parse *raw_text* as JSON and validate against *schema*.

    Returns a ``StructuredResult``.  When parsing fails the
    ``StructuredResult.data`` is an empty dict and ``errors``
    contains a description.
    """
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        return StructuredResult(
            data={},
            schema_name=schema.name,
            valid=False,
            errors=[f"Invalid JSON: {exc}"],
            raw=raw_text,
        )

    errors = _validate_value(data, schema.schema)
    return StructuredResult(
        data=data,
        schema_name=schema.name,
        valid=len(errors) == 0,
        errors=errors,
        raw=raw_text,
    )
