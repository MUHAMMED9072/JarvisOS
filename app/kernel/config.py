from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Callable, Optional

from app.core.event_bus import EventBus
from app.kernel.security.context import SecurityContextVar


# ---------------------------------------------------------------------------
# Schema types
# ---------------------------------------------------------------------------

class ConfigSchema:
    """Schema definition for a configuration namespace.

    Each field is described by a dict with optional keys:

    ===================  =================================================
    Key                  Description
    ===================  =================================================
    ``type``             Expected Python type (e.g. ``str``, ``int``).
    ``required``         If ``True`` the field must not be ``None``.
    ``default``          Default value when not provided.
    ``enum``             List of allowed values.
    ``min``              Minimum value (for numeric types).
    ``max``              Maximum value (for numeric types).
    ``pattern``          Regex pattern (for ``str`` types).
    ``description``      Human-readable explanation.
    ``validator``        ``Callable[[Any], Optional[str]]`` returning an
                        error message or ``None``.
    ===================  =================================================

    Usage::

        schema = ConfigSchema({
            "provider.default": {"type": str, "enum": ["fast", "reasoning", "coding"]},
            "retry.max_retries": {"type": int, "min": 0, "max": 10, "default": 3},
            "streaming.enabled": {"type": bool, "default": True},
        })
    """

    def __init__(self, fields: dict[str, dict[str, Any]]) -> None:
        self._fields: dict[str, dict[str, Any]] = dict(fields)

    @property
    def fields(self) -> dict[str, dict[str, Any]]:
        return dict(self._fields)

    def validate(self, path: str, value: Any) -> list[str]:
        """Validate a single *path* against the schema.

        Returns a list of error messages (empty = valid).
        """
        if path not in self._fields:
            return [f"Unknown field {path!r}"]
        spec = self._fields[path]
        errors: list[str] = []

        expected = spec.get("type")
        if expected is not None and value is not None and not isinstance(value, expected):
            errors.append(
                f"{path}: expected {expected.__name__}, got {type(value).__name__}"
            )

        if value is None and spec.get("required", False):
            errors.append(f"{path}: required field is missing")

        enum_vals = spec.get("enum")
        if enum_vals is not None and value is not None and value not in enum_vals:
            errors.append(f"{path}: must be one of {enum_vals}")

        min_val = spec.get("min")
        if min_val is not None and isinstance(value, (int, float)) and value < min_val:
            errors.append(f"{path}: {value} is below minimum {min_val}")

        max_val = spec.get("max")
        if max_val is not None and isinstance(value, (int, float)) and value > max_val:
            errors.append(f"{path}: {value} exceeds maximum {max_val}")

        pattern = spec.get("pattern")
        import re
        if pattern is not None and isinstance(value, str) and not re.match(pattern, value):
            errors.append(f"{path}: does not match pattern {pattern!r}")

        validator = spec.get("validator")
        if validator is not None:
            try:
                msg = validator(value)
                if msg is not None:
                    errors.append(f"{path}: {msg}")
            except Exception as exc:
                errors.append(f"{path}: validator raised {exc}")

        return errors

    def validate_all(self, data: dict[str, Any]) -> list[str]:
        """Validate all known fields against *data*.

        Unknown keys in *data* are silently ignored.
        """
        errors: list[str] = []
        for path in self._fields:
            if path in data:
                errors.extend(self.validate(path, data[path]))
            elif self._fields[path].get("required", False):
                errors.append(f"{path}: required field is missing")
        return errors


# ---------------------------------------------------------------------------
# Registry implementation
# ---------------------------------------------------------------------------

ChangeCallback = Callable[[str, Any, Any], None]


class ConfigRegistry:
    """Central configuration registry with hierarchical overrides.

    Resolution order (highest priority first)::

        runtime → environment → file → default

    Write operations check the permission ``config.write`` via the active
    ``SecurityContext``.  Every mutation publishes ``system.config.changed``
    on the injected ``EventBus``.

    Thread-safe.  All public methods are safe for concurrent access.
    """

    def __init__(self, event_bus: EventBus | None = None) -> None:
        self._lock = threading.RLock()
        self._event_bus = event_bus

        # Override layers (flat dot-notation dicts)
        self._defaults: dict[str, Any] = {}
        self._file: dict[str, Any] = {}
        self._env: dict[str, Any] = {}
        self._runtime: dict[str, Any] = {}

        # File source for hot-reload
        self._file_path: Path | None = None
        self._file_namespace: str = ""

        # Registered schemas (namespace → ConfigSchema)
        self._schemas: dict[str, ConfigSchema] = {}

        # Event listeners for config changes
        self._change_listeners: list[ChangeCallback] = []

        # Monotonic generation counter for change tracking
        self._generation: int = 0

    # ------------------------------------------------------------------
    # Layer management
    # ------------------------------------------------------------------

    def set_defaults(self, data: dict[str, Any], namespace: str = "") -> None:
        """Populate the default layer from a (possibly nested) dict.

        Nested dicts are automatically flattened to dot-notation keys.
        Keys are prefixed with *namespace* (dot-separated) if provided.
        """
        with self._lock:
            flat = self._flatten(data)
            self._defaults.update(self._prefix_keys(flat, namespace))

    def load_file(self, path: str | Path, namespace: str = "") -> None:
        """Load the file layer from a JSON file.

        Subsequent calls to ``reload()`` will re-read this file.
        """
        path = Path(path)
        if not path.exists():
            return
        with self._lock:
            with open(path, encoding="utf-8") as f:
                raw: dict[str, Any] = json.load(f)
            self._file = self._prefix_keys(self._flatten(raw), namespace)
            self._file_path = path
            self._file_namespace = namespace

    def load_env(self, prefix: str = "JARVIS_") -> None:
        """Load the environment layer from ``os.environ``.

        Only variables starting with *prefix* are considered.  The prefix
        is stripped and the remainder is lower-cased and split by ``__``
        (double underscore) to form a dotted path.

        Example: ``JARVIS_AI__PROVIDER__DEFAULT=fast`` becomes
        ``ai.provider.default = "fast"``.
        """
        with self._lock:
            for key, value in os.environ.items():
                if not key.startswith(prefix):
                    continue
                stripped = key[len(prefix):].lower()
                path = stripped.replace("__", ".")
                self._env[path] = self._coerce(value)

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def get(self, path: str, default: Any = None) -> Any:
        """Retrieve a value by dotted *path*.

        Resolution order: runtime → environment → file → default.
        """
        with self._lock:
            if path in self._runtime:
                return self._runtime[path]
            if path in self._env:
                return self._env[path]
            if path in self._file:
                return self._file[path]
            if path in self._defaults:
                return self._defaults[path]
            return default

    def set(self, path: str, value: Any) -> None:
        """Set a runtime override.

        Checks ``config.write`` permission via the active
        ``SecurityContext``.  Publishes ``system.config.changed``
        on the event bus.
        """
        self._check_permission("config.write")

        with self._lock:
            old = self._runtime.get(path, self._resolve_no_runtime(path))
            self._runtime[path] = value
            self._generation += 1

        self._publish("system.config.changed", {
            "path": path,
            "old_value": old,
            "new_value": value,
            "generation": self._generation,
        })
        self._notify_listeners(path, old, value)

    def has(self, path: str) -> bool:
        """Return ``True`` if a value exists in any layer for *path*."""
        with self._lock:
            return (
                path in self._runtime
                or path in self._env
                or path in self._file
                or path in self._defaults
            )

    def delete(self, path: str) -> None:
        """Remove a runtime override for *path*.

        The underlying default / file / env value is **not** removed.
        """
        self._check_permission("config.write")

        with self._lock:
            old = self._runtime.pop(path, None)
            if old is not None:
                self._generation += 1
                self._publish("system.config.changed", {
                    "path": path,
                    "old_value": old,
                    "new_value": self._resolve_no_runtime(path),
                    "generation": self._generation,
                })
                self._notify_listeners(path, old, self._resolve_no_runtime(path))

    # ------------------------------------------------------------------
    # Schema validation
    # ------------------------------------------------------------------

    def register_schema(self, namespace: str, schema: ConfigSchema) -> None:
        """Register a ``ConfigSchema`` for a top-level *namespace*."""
        with self._lock:
            self._schemas[namespace] = schema

    def get_schema(self, namespace: str) -> ConfigSchema | None:
        """Return the registered schema for *namespace* or ``None``."""
        with self._lock:
            return self._schemas.get(namespace)

    def validate(self, path: str, value: Any) -> list[str]:
        """Validate a value against the schema for its namespace."""
        namespace = path.split(".")[0]
        schema = self.get_schema(namespace)
        if schema is None:
            return []
        return schema.validate(path, value)

    # ------------------------------------------------------------------
    # Snapshot / reload
    # ------------------------------------------------------------------

    def snapshot(self, include_runtime: bool = True) -> dict[str, Any]:
        """Return a merged snapshot of all layers.

        When *include_runtime* is ``True`` (default), runtime overrides
        take precedence; otherwise only default + file + env are included.
        """
        with self._lock:
            result = dict(self._defaults)
            result.update(self._file)
            result.update(self._env)
            if include_runtime:
                result.update(self._runtime)
            return result

    def reload(self) -> list[dict[str, Any]]:
        """Re-read the file and environment layers.

        Returns a list of change descriptors (each is a dict with
        ``path``, ``old_value``, ``new_value`` keys).

        Publishes ``system.config.reloaded`` on the event bus.
        """
        with self._lock:
            old_file = dict(self._file)
            old_env = dict(self._env)
            self._env.clear()

            # Re-read file
            self._file.clear()
            if self._file_path is not None:
                self.load_file(self._file_path, self._file_namespace)

            # Re-read env
            self.load_env()

            changes: list[dict[str, Any]] = []

            all_keys = set(old_file) | set(self._file) | set(old_env) | set(self._env)
            for key in all_keys:
                old_val = old_file.get(key, old_env.get(key, None))
                new_val = self._file.get(key, self._env.get(key, None))
                if old_val != new_val:
                    changes.append({
                        "path": key,
                        "old_value": old_val,
                        "new_value": new_val,
                    })
                    self._notify_listeners(key, old_val, new_val)

            if changes:
                self._generation += 1

        if changes:
            self._publish("system.config.reloaded", {
                "changes": changes,
                "generation": self._generation,
            })

        return changes

    # ------------------------------------------------------------------
    # Export / Import
    # ------------------------------------------------------------------

    def export(self, namespace: str = "", indent: int = 2) -> str:
        """Export configuration as a JSON string.

        When *namespace* is given, only keys under that namespace are
        included.  The output is a nested dict (not dot-notation).
        """
        with self._lock:
            data = self.snapshot(include_runtime=True)
            if namespace:
                keys_to_keep = {
                    k: v for k, v in data.items()
                    if k == namespace or k.startswith(namespace + ".")
                }
                data = keys_to_keep
            nested = self._nest(data)
            return json.dumps(nested, indent=indent, default=str, ensure_ascii=False)

    def import_config(self, json_str: str, namespace: str = "") -> list[str]:
        """Import configuration from a JSON string.

        Values are set as runtime overrides.  Returns a list of paths
        that were successfully imported (empty list if JSON is invalid).
        """
        self._check_permission("config.write")
        try:
            raw: dict[str, Any] = json.loads(json_str)
        except json.JSONDecodeError as exc:
            return [f"Invalid JSON: {exc}"]

        flat = self._prefix_keys(self._flatten(raw), namespace)
        imported: list[str] = []
        with self._lock:
            for path, value in flat.items():
                old = self._runtime.get(path, self._resolve_no_runtime(path))
                self._runtime[path] = value
                self._generation += 1
                self._publish("system.config.changed", {
                    "path": path,
                    "old_value": old,
                    "new_value": value,
                    "generation": self._generation,
                })
                self._notify_listeners(path, old, value)
                imported.append(path)
        return imported

    # ------------------------------------------------------------------
    # Event helpers
    # ------------------------------------------------------------------

    @property
    def generation(self) -> int:
        with self._lock:
            return self._generation

    def subscribe(self, callback: ChangeCallback) -> Callable[[], None]:
        """Register a listener for every config change.

        The callback is invoked with ``(path, old_value, new_value)``.

        Returns a function to unsubscribe.
        """
        with self._lock:
            self._change_listeners.append(callback)

        def unsubscribe() -> None:
            with self._lock:
                if callback in self._change_listeners:
                    self._change_listeners.remove(callback)

        return unsubscribe

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_no_runtime(self, path: str) -> Any:
        """Resolve *path* ignoring the runtime layer."""
        if path in self._env:
            return self._env[path]
        if path in self._file:
            return self._file[path]
        if path in self._defaults:
            return self._defaults[path]
        return None

    def _check_permission(self, permission: str) -> None:
        ctx = SecurityContextVar.get()
        if ctx is not None:
            ctx.require(permission)

    def _publish(self, event: str, data: dict[str, Any]) -> None:
        if self._event_bus is not None:
            try:
                self._event_bus.publish(event, data)
            except Exception:
                pass

    def _notify_listeners(self, path: str, old: Any, new: Any) -> None:
        for cb in list(self._change_listeners):
            try:
                cb(path, old, new)
            except Exception:
                pass

    @staticmethod
    def _flatten(data: dict[str, Any], parent_key: str = "") -> dict[str, Any]:
        """Recursively flatten a nested dict into dot-notation keys."""
        items: dict[str, Any] = {}
        for key, value in data.items():
            new_key = f"{parent_key}.{key}" if parent_key else key
            if isinstance(value, dict):
                items.update(ConfigRegistry._flatten(value, new_key))
            else:
                items[new_key] = value
        return items

    @staticmethod
    def _prefix_keys(data: dict[str, Any], namespace: str) -> dict[str, Any]:
        """Prefix all keys in *data* with *namespace*."""
        if not namespace:
            return data
        return {f"{namespace}.{k}": v for k, v in data.items()}

    @staticmethod
    def _nest(data: dict[str, Any]) -> dict[str, Any]:
        """Convert dot-notation keys into nested dicts."""
        result: dict[str, Any] = {}
        for key, value in data.items():
            parts = key.split(".")
            target = result
            for part in parts[:-1]:
                target = target.setdefault(part, {})
            target[parts[-1]] = value
        return result

    @staticmethod
    def _coerce(value: str) -> Any:
        """Coerce an environment variable string to a Python value."""
        lower = value.lower()
        if lower in ("true", "1", "yes"):
            return True
        if lower in ("false", "0", "no"):
            return False
        if lower == "none":
            return None
        try:
            return int(value)
        except ValueError:
            pass
        try:
            return float(value)
        except ValueError:
            pass
        return value
