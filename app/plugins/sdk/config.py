from __future__ import annotations

import json
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.core.logger import JarvisLogger

_PLUGIN_CONFIG_EVENT_PREFIX = "plugin.config"


class PluginConfig:
    """Isolated, persistent configuration for a single plugin.

    Thread-safe.  Every mutating operation optionally persists to a JSON
    file and publishes an event on the EventBus.  Schema validation is
    performed when a schema is set via *set_schema()* or
    *PluginManifest.config_schema*.
    """

    def __init__(
        self,
        plugin_name: str,
        *,
        config_dir: str | Path | None = None,
        event_bus: Any = None,
        schema: dict[str, Any] | None = None,
        auto_save: bool = True,
    ) -> None:
        self._plugin_name = plugin_name
        self._lock = threading.Lock()
        self._data: dict[str, Any] = {}
        self._defaults: dict[str, Any] = {}
        self._schema: dict[str, Any] | None = None
        self._event_bus: Any = event_bus
        self._auto_save = auto_save
        self._config_path: Path | None = None
        self._loaded = False
        self._permission_checker: Callable[[str], bool] | None = None

        if config_dir is not None:
            self._config_path = Path(config_dir) / "config.json"

        if schema is not None:
            self.set_schema(schema)

    def _set_permission_checker(
        self, checker: Callable[[str], bool] | None,
    ) -> None:
        self._permission_checker = checker

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    @property
    def schema(self) -> dict[str, Any] | None:
        return self._schema

    def set_schema(self, schema: dict[str, Any] | None) -> None:
        self._schema = schema
        self._defaults = self._extract_defaults(schema) if schema else {}

    @staticmethod
    def _extract_defaults(schema: dict[str, Any]) -> dict[str, Any]:
        defaults: dict[str, Any] = {}
        properties = schema.get("properties", {})
        for key, prop in properties.items():
            if isinstance(prop, dict) and "default" in prop:
                defaults[key] = prop["default"]
        return defaults

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    @property
    def config_path(self) -> Path | None:
        return self._config_path

    @property
    def loaded(self) -> bool:
        return self._loaded

    def load(self) -> None:
        if self._config_path is None:
            return
        try:
            self._config_path.parent.mkdir(parents=True, exist_ok=True)
            if self._config_path.is_file():
                raw = self._config_path.read_text(encoding="utf-8")
                with self._lock:
                    self._data = json.loads(raw)
            else:
                with self._lock:
                    self._data = {}
            self._ensure_defaults()
            self._loaded = True
            self._publish("loaded", {"path": str(self._config_path)})
        except Exception as exc:
            JarvisLogger.exception(
                "PluginConfig: failed to load config for %r: %s",
                self._plugin_name, exc,
            )
            self._loaded = True

    def save(self) -> None:
        if self._permission_checker and not self._permission_checker("config"):
            return
        if self._config_path is None:
            return
        try:
            self._config_path.parent.mkdir(parents=True, exist_ok=True)
            with self._lock:
                raw = json.dumps(self._data, indent=2, ensure_ascii=False)
            self._config_path.write_text(raw, encoding="utf-8")
            self._publish("saved", {"path": str(self._config_path)})
        except Exception as exc:
            JarvisLogger.exception(
                "PluginConfig: failed to save config for %r: %s",
                self._plugin_name, exc,
            )

    def reload(self) -> None:
        if self._config_path is None:
            return
        try:
            if self._config_path.is_file():
                raw = self._config_path.read_text(encoding="utf-8")
                with self._lock:
                    self._data = json.loads(raw)
            self._ensure_defaults()
            self._publish("reloaded", {"path": str(self._config_path)})
        except Exception as exc:
            JarvisLogger.exception(
                "PluginConfig: failed to reload config for %r: %s",
                self._plugin_name, exc,
            )

    def _ensure_defaults(self) -> None:
        for key, value in self._defaults.items():
            if key not in self._data:
                self._data[key] = value

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(
        self, data: dict[str, Any] | None = None,
    ) -> list[str]:
        errors: list[str] = []
        if self._schema is None:
            return errors
        target = data if data is not None else self._data
        properties = self._schema.get("properties", {})
        required = self._schema.get("required", [])

        for field in required:
            if field not in target or target[field] is None:
                errors.append(f"Missing required field: {field!r}")

        for field, value in target.items():
            prop = properties.get(field)
            if prop is None:
                continue
            expected_type = prop.get("type")
            if expected_type and value is not None:
                if not self._type_match(value, expected_type):
                    errors.append(
                        f"Field {field!r}: expected {expected_type}, "
                        f"got {type(value).__name__}",
                    )

        if errors:
            self._publish(
                "validation_error",
                {"errors": errors, "plugin": self._plugin_name},
            )
        return errors

    @staticmethod
    def _type_match(value: Any, expected: str) -> bool:
        mapping: dict[str, type] = {
            "string": str,
            "number": (int, float),
            "integer": int,
            "boolean": bool,
            "object": dict,
            "array": list,
        }
        py_type = mapping.get(expected)
        if py_type is None:
            return True
        return isinstance(value, py_type)

    # ------------------------------------------------------------------
    # Read / Write (backward-compatible API)
    # ------------------------------------------------------------------

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        if self._permission_checker and not self._permission_checker("config"):
            return
        with self._lock:
            self._data[key] = value
        if self._auto_save:
            self.save()
        self._publish("changed", {key: value})

    def all(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._data)

    def clear(self) -> None:
        if self._permission_checker and not self._permission_checker("config"):
            return
        with self._lock:
            self._data.clear()
        if self._auto_save:
            self.save()
        self._publish("changed", {})

    def update(self, data: dict[str, Any]) -> None:
        if self._permission_checker and not self._permission_checker("config"):
            return
        with self._lock:
            self._data.update(data)
        if self._auto_save:
            self.save()
        self._publish("changed", dict(data))

    # ------------------------------------------------------------------
    # Defaults
    # ------------------------------------------------------------------

    def set_defaults(self) -> None:
        if self._permission_checker and not self._permission_checker("config"):
            return
        with self._lock:
            self._ensure_defaults()
        if self._auto_save:
            self.save()

    @property
    def defaults(self) -> dict[str, Any]:
        return dict(self._defaults)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _publish(self, action: str, payload: dict[str, Any]) -> None:
        if self._event_bus is None:
            return
        try:
            event = f"{_PLUGIN_CONFIG_EVENT_PREFIX}.{action}"
            data = {"plugin": self._plugin_name, **payload}
            self._event_bus.publish(event, data)
        except Exception:
            pass
