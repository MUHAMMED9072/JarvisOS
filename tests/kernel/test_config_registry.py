from __future__ import annotations

import json
import os
import threading
from pathlib import Path

import pytest

from app.kernel.config import ConfigRegistry, ConfigSchema
from app.core.event_bus import EventBus
from app.kernel.security.context import SecurityContext, SecurityContextVar


# ======================================================================
# Helpers
# ======================================================================

@pytest.fixture
def bus() -> EventBus:
    return EventBus()


@pytest.fixture
def registry(bus: EventBus) -> ConfigRegistry:
    return ConfigRegistry(event_bus=bus)


# ======================================================================
# ConfigSchema tests
# ======================================================================

class TestConfigSchema:
    def test_type_validation_passes(self):
        schema = ConfigSchema({"timeout": {"type": int}})
        assert schema.validate("timeout", 30) == []

    def test_type_validation_fails(self):
        schema = ConfigSchema({"timeout": {"type": int}})
        errors = schema.validate("timeout", "30")
        assert len(errors) == 1
        assert "expected int, got str" in errors[0]

    def test_required_field_present(self):
        schema = ConfigSchema({"name": {"type": str, "required": True}})
        assert schema.validate("name", "hello") == []

    def test_required_field_missing(self):
        schema = ConfigSchema({"name": {"type": str, "required": True}})
        errors = schema.validate("name", None)
        assert any("required" in e for e in errors)

    def test_enum_validation_passes(self):
        schema = ConfigSchema({"mode": {"enum": ["fast", "deep"]}})
        assert schema.validate("mode", "fast") == []

    def test_enum_validation_fails(self):
        schema = ConfigSchema({"mode": {"enum": ["fast", "deep"]}})
        errors = schema.validate("mode", "auto")
        assert any("must be one of" in e for e in errors)

    def test_min_max_validation(self):
        schema = ConfigSchema({"retries": {"type": int, "min": 0, "max": 10}})
        assert schema.validate("retries", 5) == []
        assert schema.validate("retries", -1) != []
        assert schema.validate("retries", 11) != []

    def test_pattern_validation(self):
        schema = ConfigSchema({"host": {"type": str, "pattern": r"^\w+\.\w+$"}})
        assert schema.validate("host", "example.com") == []
        assert schema.validate("host", "bad") != []

    def test_custom_validator(self):
        def must_be_positive(val):
            if val is not None and val <= 0:
                return "must be positive"
            return None

        schema = ConfigSchema({"count": {"validator": must_be_positive}})
        assert schema.validate("count", 5) == []
        assert schema.validate("count", -1) != []

    def test_unknown_field(self):
        schema = ConfigSchema({"known": {"type": str}})
        errors = schema.validate("unknown", "x")
        assert any("Unknown field" in e for e in errors)

    def test_validate_all(self):
        schema = ConfigSchema({
            "name": {"type": str, "required": True},
            "count": {"type": int, "default": 0},
        })
        errors = schema.validate_all({"name": "hello", "count": 42})
        assert errors == []

    def test_validate_all_missing_required(self):
        schema = ConfigSchema({
            "name": {"type": str, "required": True},
        })
        errors = schema.validate_all({})
        assert any("required" in e for e in errors)

    def test_fields_property(self):
        schema = ConfigSchema({"a": {"type": int}, "b": {"type": str}})
        assert set(schema.fields) == {"a", "b"}


# ======================================================================
# ConfigRegistry tests
# ======================================================================

class TestConfigRegistryDefaults:
    def test_get_default_value(self, registry: ConfigRegistry):
        registry.set_defaults({"app.name": "JARVIS OS", "app.version": "0.4.0"})
        assert registry.get("app.name") == "JARVIS OS"
        assert registry.get("app.version") == "0.4.0"

    def test_get_with_namespace(self, registry: ConfigRegistry):
        registry.set_defaults({"name": "JARVIS OS"}, namespace="app")
        assert registry.get("app.name") == "JARVIS OS"

    def test_get_missing_returns_default(self, registry: ConfigRegistry):
        assert registry.get("nonexistent", "fallback") == "fallback"

    def test_get_missing_no_default(self, registry: ConfigRegistry):
        assert registry.get("nonexistent") is None

    def test_has_returns_true(self, registry: ConfigRegistry):
        registry.set_defaults({"key": "val"})
        assert registry.has("key") is True

    def test_has_returns_false(self, registry: ConfigRegistry):
        assert registry.has("missing") is False


class TestConfigRegistryFileLayer:
    def test_load_file(self, registry: ConfigRegistry, tmp_path: Path):
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({"app": {"name": "From File"}}))
        registry.load_file(config_file)
        assert registry.get("app.name") == "From File"

    def test_load_file_with_namespace(self, registry: ConfigRegistry, tmp_path: Path):
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({"name": "From Namespace"}))
        registry.load_file(config_file, namespace="app")
        assert registry.get("app.name") == "From Namespace"

    def test_load_file_missing(self, registry: ConfigRegistry):
        registry.load_file("/nonexistent/config.json")
        # Should not raise

    def test_file_layer_below_runtime(self, registry: ConfigRegistry, tmp_path: Path):
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({"key": "file"}))
        registry.load_file(config_file)
        registry.set("key", "runtime")
        assert registry.get("key") == "runtime"


class TestConfigRegistryEnvLayer:
    def test_load_env(self, registry: ConfigRegistry):
        os.environ["JARVIS_TEST__KEY"] = "env_value"
        try:
            registry.load_env("JARVIS_")
            assert registry.get("test.key") == "env_value"
        finally:
            del os.environ["JARVIS_TEST__KEY"]

    def test_load_env_namespace_separator(self, registry: ConfigRegistry):
        os.environ["JARVIS_AI__PROVIDER__DEFAULT"] = "deepseek"
        try:
            registry.load_env("JARVIS_")
            assert registry.get("ai.provider.default") == "deepseek"
        finally:
            del os.environ["JARVIS_AI__PROVIDER__DEFAULT"]

    def test_load_env_coercion_bool(self, registry: ConfigRegistry):
        os.environ["JARVIS_FLAG"] = "true"
        try:
            registry.load_env("JARVIS_")
            assert registry.get("flag") is True
        finally:
            del os.environ["JARVIS_FLAG"]

    def test_load_env_coercion_int(self, registry: ConfigRegistry):
        os.environ["JARVIS_COUNT"] = "42"
        try:
            registry.load_env("JARVIS_")
            assert registry.get("count") == 42
        finally:
            del os.environ["JARVIS_COUNT"]

    def test_env_below_runtime(self, registry: ConfigRegistry):
        os.environ["JARVIS_SOME__KEY"] = "env"
        try:
            registry.load_env("JARVIS_")
            registry.set("some.key", "runtime")
            assert registry.get("some.key") == "runtime"
        finally:
            del os.environ["JARVIS_SOME__KEY"]


class TestConfigRegistryResolutionOrder:
    def test_resolution_runtime_wins(self, registry: ConfigRegistry):
        registry.set_defaults({"x": "default"})
        registry.set("x", "runtime")
        assert registry.get("x") == "runtime"

    def test_resolution_env_over_file(self, registry: ConfigRegistry, tmp_path: Path):
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({"x": "file"}))
        registry.load_file(config_file)
        os.environ["JARVIS_X"] = "env"
        try:
            registry.load_env("JARVIS_")
            assert registry.get("x") == "env"
        finally:
            del os.environ["JARVIS_X"]

    def test_resolution_file_over_default(self, registry: ConfigRegistry, tmp_path: Path):
        registry.set_defaults({"x": "default"})
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({"x": "file"}))
        registry.load_file(config_file)
        assert registry.get("x") == "file"


class TestConfigRegistrySetDelete:
    def test_set_adds_value(self, registry: ConfigRegistry):
        registry.set("key", "value")
        assert registry.get("key") == "value"

    def test_set_overwrites(self, registry: ConfigRegistry):
        registry.set("key", "old")
        registry.set("key", "new")
        assert registry.get("key") == "new"

    def test_set_publishes_event(self, registry: ConfigRegistry, bus: EventBus):
        events: list[str] = []
        bus.subscribe("system.config.changed", lambda data: events.append(data))
        registry.set("key", "value")
        assert len(events) == 1
        assert events[0]["path"] == "key"
        assert events[0]["new_value"] == "value"

    def test_set_publishes_old_value(self, registry: ConfigRegistry, bus: EventBus):
        registry.set_defaults({"key": "default"})
        events: list[dict] = []
        bus.subscribe("system.config.changed", events.append)
        registry.set("key", "override")
        assert events[0]["old_value"] == "default"

    def test_delete_removes_runtime(self, registry: ConfigRegistry):
        registry.set_defaults({"key": "default"})
        registry.set("key", "runtime")
        registry.delete("key")
        assert registry.get("key") == "default"

    def test_delete_publishes_event(self, registry: ConfigRegistry, bus: EventBus):
        registry.set("key", "val")
        events: list[dict] = []
        bus.subscribe("system.config.changed", events.append)
        registry.delete("key")
        assert len(events) == 1
        assert events[0]["path"] == "key"

    def test_delete_missing_does_not_publish(self, registry: ConfigRegistry, bus: EventBus):
        events: list = []
        bus.subscribe("system.config.changed", events.append)
        registry.delete("missing")
        assert len(events) == 0


class TestConfigRegistryPermissionCheck:
    def test_set_with_permission_passes(self, registry: ConfigRegistry):
        ctx = SecurityContext(actor="admin", granted={"config.write"})
        SecurityContextVar.set(ctx)
        try:
            registry.set("key", "val")
            assert registry.get("key") == "val"
        finally:
            SecurityContextVar.reset()

    def test_set_without_permission_raises(self, registry: ConfigRegistry):
        ctx = SecurityContext(actor="user", granted={"config.read"})
        SecurityContextVar.set(ctx)
        try:
            with pytest.raises(PermissionError):
                registry.set("key", "val")
        finally:
            SecurityContextVar.reset()

    def test_set_no_context_skips_check(self, registry: ConfigRegistry):
        SecurityContextVar.reset()
        registry.set("key", "val")
        assert registry.get("key") == "val"

    def test_delete_with_permission_passes(self, registry: ConfigRegistry):
        registry.set("key", "val")
        ctx = SecurityContext(actor="admin", granted={"config.write"})
        SecurityContextVar.set(ctx)
        try:
            registry.delete("key")
            assert registry.get("key") is None
        finally:
            SecurityContextVar.reset()

    def test_delete_without_permission_raises(self, registry: ConfigRegistry):
        registry.set("key", "val")
        ctx = SecurityContext(actor="user", granted={"config.read"})
        SecurityContextVar.set(ctx)
        try:
            with pytest.raises(PermissionError):
                registry.delete("key")
        finally:
            SecurityContextVar.reset()


class TestConfigRegistrySchema:
    def test_register_and_get_schema(self, registry: ConfigRegistry):
        schema = ConfigSchema({"name": {"type": str}})
        registry.register_schema("test", schema)
        assert registry.get_schema("test") is schema

    def test_validate_against_schema(self, registry: ConfigRegistry):
        schema = ConfigSchema({"timeout": {"type": int}})
        registry.register_schema("app", schema)
        errors = registry.validate("app.timeout", "bad")
        assert len(errors) == 1

    def test_validate_no_schema_returns_empty(self, registry: ConfigRegistry):
        assert registry.validate("unknown.key", "val") == []


class TestConfigRegistrySnapshot:
    def test_snapshot_includes_defaults(self, registry: ConfigRegistry):
        registry.set_defaults({"a": 1, "b": 2})
        snap = registry.snapshot()
        assert snap["a"] == 1
        assert snap["b"] == 2

    def test_snapshot_includes_runtime(self, registry: ConfigRegistry):
        registry.set_defaults({"a": 1})
        registry.set("a", 99)
        assert registry.snapshot()["a"] == 99

    def test_snapshot_exclude_runtime(self, registry: ConfigRegistry):
        registry.set_defaults({"a": 1})
        registry.set("a", 99)
        assert registry.snapshot(include_runtime=False)["a"] == 1


class TestConfigRegistryReload:
    def test_reload_detects_file_changes(self, registry: ConfigRegistry, tmp_path: Path):
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({"key": "v1"}))
        registry.load_file(config_file)
        assert registry.get("key") == "v1"

        config_file.write_text(json.dumps({"key": "v2"}))
        changes = registry.reload()
        assert registry.get("key") == "v2"
        assert any(c["path"] == "key" and c["new_value"] == "v2" for c in changes)

    def test_reload_publishes_event(self, registry: ConfigRegistry, bus: EventBus, tmp_path: Path):
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({"key": "v1"}))
        registry.load_file(config_file)

        events: list[dict] = []
        bus.subscribe("system.config.reloaded", events.append)
        config_file.write_text(json.dumps({"key": "v2"}))
        registry.reload()
        assert len(events) == 1

    def test_reload_no_changes_no_event(self, registry: ConfigRegistry, bus: EventBus, tmp_path: Path):
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({"key": "val"}))
        registry.load_file(config_file)

        events: list = []
        bus.subscribe("system.config.reloaded", events.append)
        registry.reload()
        assert len(events) == 0


class TestConfigRegistryExportImport:
    def test_export_returns_json(self, registry: ConfigRegistry):
        registry.set_defaults({"app.name": "JARVIS"})
        exported = registry.export()
        assert isinstance(exported, str)
        data = json.loads(exported)
        assert data["app"]["name"] == "JARVIS"

    def test_export_with_namespace(self, registry: ConfigRegistry):
        registry.set_defaults({"app.name": "JARVIS", "ai.provider": "deepseek"})
        exported = registry.export(namespace="app")
        data = json.loads(exported)
        assert "app" in data
        assert "ai" not in data

    def test_import_restores_values(self, registry: ConfigRegistry):
        registry.set_defaults({"key": "old"})
        json_str = json.dumps({"key": "new"})
        imported = registry.import_config(json_str)
        assert registry.get("key") == "new"
        assert "key" in imported

    def test_import_with_namespace(self, registry: ConfigRegistry):
        json_str = json.dumps({"name": "Test"})
        registry.import_config(json_str, namespace="app")
        assert registry.get("app.name") == "Test"

    def test_import_invalid_json(self, registry: ConfigRegistry):
        result = registry.import_config("not json")
        assert isinstance(result, list)
        assert len(result) == 1
        assert "Invalid JSON" in str(result[0])

    def test_import_publishes_events(self, registry: ConfigRegistry, bus: EventBus):
        events: list = []
        bus.subscribe("system.config.changed", events.append)
        registry.import_config(json.dumps({"a": 1, "b": 2}))
        assert len(events) == 2


class TestConfigRegistrySubscribe:
    def test_subscribe_notified_on_set(self, registry: ConfigRegistry):
        notifications: list = []
        registry.subscribe(lambda p, o, n: notifications.append((p, o, n)))
        registry.set("key", "val")
        assert len(notifications) == 1
        assert notifications[0] == ("key", None, "val")

    def test_subscribe_notified_on_delete(self, registry: ConfigRegistry):
        registry.set("key", "val")
        notifications: list = []
        registry.subscribe(lambda p, o, n: notifications.append((p, o, n)))
        registry.delete("key")
        assert len(notifications) == 1

    def test_unsubscribe_stops_notifications(self, registry: ConfigRegistry):
        notifications: list = []
        unsub = registry.subscribe(lambda p, o, n: notifications.append(p))
        unsub()
        registry.set("key", "val")
        assert len(notifications) == 0

    def test_subscribe_notified_on_reload(self, registry: ConfigRegistry, tmp_path: Path):
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({"k": "v1"}))
        registry.load_file(config_file)

        notifications: list = []
        registry.subscribe(lambda p, o, n: notifications.append((p, o, n)))
        config_file.write_text(json.dumps({"k": "v2"}))
        registry.reload()
        assert any(n[0] == "k" for n in notifications)


class TestConfigRegistryGeneration:
    def test_generation_starts_at_zero(self, registry: ConfigRegistry):
        assert registry.generation == 0

    def test_generation_increments_on_set(self, registry: ConfigRegistry):
        registry.set("k", "v")
        assert registry.generation == 1

    def test_generation_increments_on_delete(self, registry: ConfigRegistry):
        registry.set("k", "v")
        registry.delete("k")
        assert registry.generation == 2

    def test_generation_increments_on_import(self, registry: ConfigRegistry):
        registry.import_config(json.dumps({"a": 1, "b": 2}))
        assert registry.generation == 2

    def test_generation_increments_on_reload(self, registry: ConfigRegistry, tmp_path: Path):
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({"k": "v1"}))
        registry.load_file(config_file)
        config_file.write_text(json.dumps({"k": "v2"}))
        registry.reload()
        assert registry.generation == 1


class TestConfigRegistryThreadSafety:
    def test_concurrent_set(self, registry: ConfigRegistry):
        errors: list[Exception] = []

        def worker(key: str, value: str) -> None:
            try:
                for _ in range(100):
                    registry.set(key, value)
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=worker, args=("k1", "v1")),
            threading.Thread(target=worker, args=("k2", "v2")),
            threading.Thread(target=worker, args=("k3", "v3")),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert registry.get("k1") == "v1"
        assert registry.get("k2") == "v2"
        assert registry.get("k3") == "v3"

    def test_concurrent_get_and_set(self, registry: ConfigRegistry):
        errors: list[Exception] = []
        stop = threading.Event()

        def writer() -> None:
            while not stop.is_set():
                try:
                    registry.set("k", "w")
                except Exception as e:
                    errors.append(e)
                    break

        def reader() -> None:
            while not stop.is_set():
                try:
                    registry.get("k")
                except Exception as e:
                    errors.append(e)
                    break

        threads = [threading.Thread(target=writer)]
        threads += [threading.Thread(target=reader) for _ in range(4)]
        for t in threads:
            t.start()
        import time
        time.sleep(0.2)
        stop.set()
        for t in threads:
            t.join()

        assert len(errors) == 0


class TestConfigRegistryEventBus:
    def test_no_event_bus_set_does_not_raise(self, registry: ConfigRegistry):
        reg = ConfigRegistry(event_bus=None)
        reg.set("k", "v")
        reg.delete("k")
        reg.import_config(json.dumps({"a": 1}))

    def test_event_on_set(self, registry: ConfigRegistry, bus: EventBus):
        events: list = []
        bus.subscribe("system.config.changed", events.append)
        registry.set("k", "v")
        assert len(events) == 1
        assert events[0]["path"] == "k"

    def test_event_on_delete(self, registry: ConfigRegistry, bus: EventBus):
        registry.set("k", "v")
        events: list = []
        bus.subscribe("system.config.changed", events.append)
        registry.delete("k")
        assert len(events) == 1

    def test_event_on_reload(self, registry: ConfigRegistry, bus: EventBus, tmp_path: Path):
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({"k": "v1"}))
        registry.load_file(config_file)

        events: list = []
        bus.subscribe("system.config.reloaded", events.append)
        config_file.write_text(json.dumps({"k": "v2"}))
        registry.reload()
        assert len(events) == 1

    def test_event_on_import(self, registry: ConfigRegistry, bus: EventBus):
        events: list = []
        bus.subscribe("system.config.changed", events.append)
        registry.import_config(json.dumps({"k": "v"}))
        assert len(events) == 1


class TestConfigRegistryEdgeCases:
    def test_empty_defaults(self, registry: ConfigRegistry):
        registry.set_defaults({})
        assert registry.get("anything") is None

    def test_nested_defaults(self, registry: ConfigRegistry):
        registry.set_defaults({"app": {"name": "JARVIS", "version": "1.0"}})
        assert registry.get("app.name") == "JARVIS"
        assert registry.get("app.version") == "1.0"

    def test_round_trip_export_import(self, registry: ConfigRegistry):
        registry.set_defaults({"a.b": 1, "c": "hello"})
        exported = registry.export()
        imported_registry = ConfigRegistry()
        imported_registry.import_config(exported)
        assert imported_registry.get("a.b") == 1
        assert imported_registry.get("c") == "hello"

    def test_coerce_none(self):
        from app.kernel.config import ConfigRegistry as R
        assert R._coerce("none") is None

    def test_coerce_float(self):
        from app.kernel.config import ConfigRegistry as R
        assert R._coerce("3.14") == 3.14

    def test_coerce_string(self):
        from app.kernel.config import ConfigRegistry as R
        assert R._coerce("hello") == "hello"
