from __future__ import annotations

import threading
from typing import Any

from app.ads.artifact_type import ArtifactType, BUILTIN_ARTIFACT_TYPES


class ArtifactTypeRegistry:
    """Registry for artifact types in the ADS pipeline.

    Thread-safe.  Pre-populated with 10 built-in types.
    Supports runtime registration of new types.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._types: dict[str, ArtifactType] = {}
        self._register_builtins()

    def _register_builtins(self) -> None:
        for name, atype in BUILTIN_ARTIFACT_TYPES.items():
            self._types[name] = atype

    def register(self, artifact_type: ArtifactType) -> None:
        with self._lock:
            self._types[artifact_type.name] = artifact_type

    def get(self, name: str) -> ArtifactType | None:
        with self._lock:
            return self._types.get(name)

    def list_types(self) -> list[str]:
        with self._lock:
            return sorted(self._types.keys())

    def is_valid(self, name: str) -> bool:
        with self._lock:
            return name in self._types

    def get_stages(self, name: str) -> list[str]:
        with self._lock:
            at = self._types.get(name)
            if at is None:
                return []
            return list(at.stages)

    def get_base_class(self, name: str) -> str | None:
        with self._lock:
            at = self._types.get(name)
            if at is None:
                return None
            return at.base_class

    def validate_manifest(self, name: str, manifest: dict[str, Any]) -> list[str]:
        """Validate a manifest against the artifact type's schema.

        Returns list of validation errors (empty = valid).
        """
        atype = self.get(name)
        if atype is None:
            return [f"Unknown artifact type '{name}'"]

        schema = atype.manifest_schema
        if not schema:
            return []

        return self._validate_against_schema(manifest, schema)

    def _validate_against_schema(
        self, manifest: dict[str, Any], schema: dict[str, Any],
    ) -> list[str]:
        errors: list[str] = []
        required = schema.get("required", [])
        for field in required:
            if field not in manifest:
                errors.append(f"Missing required field: '{field}'")

        props = schema.get("properties", {})
        for key, value in manifest.items():
            if key not in props:
                continue
            prop_schema = props[key]
            schema_type = prop_schema.get("type")
            if schema_type == "string" and not isinstance(value, str):
                errors.append(f"Field '{key}' should be string, got {type(value).__name__}")
            elif schema_type == "array" and not isinstance(value, list):
                errors.append(f"Field '{key}' should be array, got {type(value).__name__}")
            elif schema_type == "object" and not isinstance(value, dict):
                errors.append(f"Field '{key}' should be object, got {type(value).__name__}")

            enum_vals = prop_schema.get("enum")
            if enum_vals and value not in enum_vals:
                errors.append(f"Field '{key}' must be one of {enum_vals}, got '{value}'")

            pattern = prop_schema.get("pattern")
            if pattern and isinstance(value, str):
                import re
                if not re.match(pattern, value):
                    errors.append(f"Field '{key}' does not match pattern {pattern}")

        return errors

    def count(self) -> int:
        with self._lock:
            return len(self._types)

    def health(self) -> dict[str, Any]:
        with self._lock:
            return {
                "alive": True,
                "registered_types": self.count(),
                "type_names": self.list_types(),
            }


# Global singleton
ARTIFACT_TYPE_REGISTRY = ArtifactTypeRegistry()
