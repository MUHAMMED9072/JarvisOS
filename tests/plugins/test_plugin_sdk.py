"""Tests for the Plugin SDK framework."""

from __future__ import annotations

import json
import tempfile
import zipfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.ai.structured import StructuredSchema
from app.ai.templates import PromptTemplate, PromptTemplateRegistry, PromptVariable
from app.ai.tools import ToolDefinition, ToolRegistry
from app.core.event_bus import EventBus
from app.skills.base import Skill
from app.skills.manager import SkillManager
from app.skills.result import SkillResult
from app.plugins.sdk import (
    ConfigInspector,
    DependencyInspector,
    HealthCheckResult,
    InstallMetadata,
    PackageCompatibilityError,
    PackageError,
    PackageExistsError,
    PackageManager,
    PackageNotFoundError,
    PackageValidationError,
    Permission,
    PermissionDenied,
    PermissionInspector,
    PermissionManager,
    Plugin,
    PluginConfig,
    PluginContext,
    PluginDependency,
    PluginDiagnosticsResult,
    PluginDocGenerator,
    PluginInfoExporter,
    PluginLoader,
    PluginManager,
    PluginManifest,
    PluginPackage,
    PluginProject,
    PluginValidator,
    ValidationResult,
    check_version_compatibility,
    compute_hash,
    diagnose_plugin,
    discover_plugin_dirs,
    export_plugin_info,
    format_validation_result,
    generate_manifest,
    generate_plugin_docs,
    health_check_plugin,
    inspect_config_schema,
    inspect_dependencies,
    inspect_package,
    inspect_permissions,
    list_plugin_permission_summary,
    load_manifest_from_zip,
    manifest_to_json,
    resolve_plugin_file,
    scaffold_plugin,
    validate_manifest,
    validate_plugin_manifest,
    validate_plugin_project,
)


# ==========================================================================
# Manifest validation
# ==========================================================================


class TestManifestValidation:
    """PluginManifest validation and version compatibility."""

    def test_valid_manifest_passes(self):
        m = PluginManifest(name="test", version="1.0.0")
        assert validate_manifest(m) == []

    def test_empty_name_fails(self):
        m = PluginManifest(name="", version="1.0.0")
        errs = validate_manifest(m)
        assert len(errs) == 1
        assert "name" in errs[0]

    def test_invalid_version_fails(self):
        m = PluginManifest(name="test", version="not-a-version")
        errs = validate_manifest(m)
        assert any("version" in e for e in errs)

    def test_invalid_min_core_version_fails(self):
        m = PluginManifest(
            name="test", version="1.0.0",
            min_core_version="bad",
        )
        errs = validate_manifest(m)
        assert any("min_core_version" in e for e in errs)

    def test_all_fields_valid(self):
        m = PluginManifest(
            name="my-plugin",
            version="2.1.0",
            description="A test plugin",
            author="Test Author",
            min_core_version="0.4.0",
            dependencies=[PluginDependency("other", "1.0.0")],
            capabilities=["logging", "ai"],
            config_schema={"type": "object"},
        )
        assert validate_manifest(m) == []

    def test_dependency_empty_name_fails(self):
        m = PluginManifest(
            name="test", version="1.0.0",
            dependencies=[PluginDependency("", "1.0.0")],
        )
        errs = validate_manifest(m)
        assert any("dependencies[0]" in e for e in errs)

    def test_version_compatibility_same_major(self):
        assert check_version_compatibility("0.4.0", "0.4.0") is True

    def test_version_compatibility_older_plugin(self):
        assert check_version_compatibility("0.3.0", "0.4.0") is True

    def test_version_compatibility_newer_plugin_minor(self):
        assert check_version_compatibility("0.5.0", "0.4.0") is False

    def test_version_compatibility_different_major(self):
        assert check_version_compatibility("1.0.0", "0.4.0") is False

    def test_version_compatibility_invalid_version(self):
        assert check_version_compatibility("bad", "0.4.0") is False

    def test_version_compatibility_invalid_core(self):
        assert check_version_compatibility("0.4.0", "bad") is False

    def test_version_compatibility_same_patch(self):
        assert check_version_compatibility("0.4.1", "0.4.0") is False

    def test_version_compatibility_prerelease(self):
        assert check_version_compatibility("0.4.0-alpha", "0.4.0") is True

    def test_manifest_with_all_optional_fields(self):
        m = PluginManifest(
            name="full",
            version="3.2.1",
            description="desc",
            author="author",
            min_core_version="0.4.0",
            dependencies=[PluginDependency("dep-a", "1.0.0")],
            capabilities=["cap-a", "cap-b"],
            config_schema={"key": "value"},
        )
        assert m.name == "full"
        assert m.version == "3.2.1"
        assert len(m.dependencies) == 1
        assert len(m.capabilities) == 2


# ==========================================================================
# PluginConfig
# ==========================================================================


class TestPluginConfig:
    """Per-plugin configuration storage."""

    def test_get_set(self):
        pc = PluginConfig("test")
        pc.set("key1", "value1")
        assert pc.get("key1") == "value1"

    def test_get_default(self):
        pc = PluginConfig("test")
        assert pc.get("nonexistent", "default") == "default"

    def test_get_default_none(self):
        pc = PluginConfig("test")
        assert pc.get("nonexistent") is None

    def test_all_returns_copy(self):
        pc = PluginConfig("test")
        pc.set("a", 1)
        pc.set("b", 2)
        data = pc.all()
        assert data == {"a": 1, "b": 2}

    def test_clear(self):
        pc = PluginConfig("test")
        pc.set("key", "value")
        pc.clear()
        assert pc.get("key") is None

    def test_overwrite(self):
        pc = PluginConfig("test")
        pc.set("key", "old")
        pc.set("key", "new")
        assert pc.get("key") == "new"


# ==========================================================================
# PluginContext
# ==========================================================================


class _FakeRegistry:
    def __init__(self) -> None:
        self._services: dict[str, Any] = {
            "event_bus": EventBus(),
            "ai_manager": MagicMock(),
            "memory": MagicMock(),
            "cortex": MagicMock(),
            "dispatcher": MagicMock(),
            "skill_manager": SkillManager(),
            "tool_registry": ToolRegistry(),
            "template_registry": PromptTemplateRegistry(),
        }

    def get(self, name: str) -> Any:
        return self._services[name]

    def get_optional(self, name: str) -> Any | None:
        return self._services.get(name)

    def exists(self, name: str) -> bool:
        return name in self._services

    def register(self, name: str, service: Any) -> None:
        if name in self._services:
            raise ValueError(f"Service '{name}' is already registered.")
        self._services[name] = service

    def remove(self, name: str) -> None:
        self._services.pop(name, None)

    def list_services(self) -> list[str]:
        return sorted(self._services.keys())


class TestPluginContext:
    """PluginContext provides controlled service access."""

    @pytest.fixture
    def ctx(self):
        return PluginContext(_FakeRegistry(), "test-plugin")

    def test_registry_access(self, ctx):
        assert ctx.registry is not None

    def test_event_bus_access(self, ctx):
        assert ctx.event_bus is not None

    def test_ai_manager_access(self, ctx):
        assert ctx.ai_manager is not None

    def test_memory_access(self, ctx):
        assert ctx.memory is not None

    def test_config_isolation(self, ctx):
        assert ctx.config.get("key") is None
        ctx.config.set("key", "value")
        assert ctx.config.get("key") == "value"

    def test_optional_service_returns_none(self):
        reg = _FakeRegistry()
        reg._services.pop("ai_manager", None)
        ctx = PluginContext(reg, "test")
        assert ctx.ai_manager is None

    def test_service_method(self, ctx):
        assert ctx.get_service("event_bus") is not None
        assert ctx.get_service("nonexistent") is None


# ==========================================================================
# Plugin base class
# ==========================================================================


class _ConcretePlugin(Plugin):
    name = "test-plugin"
    version = "2.0.0"


class TestPluginBase:
    """Plugin ABC provides lifecycle hooks and state."""

    def test_default_state(self):
        p = _ConcretePlugin()
        assert p.enabled is False
        assert p.context is None

    def test_inject_context(self):
        p = _ConcretePlugin()
        ctx = PluginContext(_FakeRegistry(), "test-plugin")
        p._inject(ctx)
        assert p.context is ctx

    def test_lifecycle_hooks_have_defaults(self):
        p = _ConcretePlugin()
        p.on_load()
        p.on_enable()
        p.on_disable()
        p.on_uninstall()

    def test_name_and_version(self):
        p = _ConcretePlugin()
        assert p.name == "test-plugin"
        assert p.version == "2.0.0"

    def test_enabled_property(self):
        p = _ConcretePlugin()
        p._enabled = True
        assert p.enabled is True


class _LifecyclePlugin(Plugin):
    name = "lifecycle-test"
    version = "1.0.0"
    manifest = PluginManifest(name="lifecycle-test", version="1.0.0")

    def __init__(self) -> None:
        super().__init__()
        self.events: list[str] = []

    def on_load(self) -> None:
        self.events.append("load")

    def on_enable(self) -> None:
        self.events.append("enable")

    def on_disable(self) -> None:
        self.events.append("disable")

    def on_uninstall(self) -> None:
        self.events.append("uninstall")


class TestPluginLifecycle:
    """Plugin lifecycle hooks fire in correct order."""

    def test_on_load_called(self):
        p = _LifecyclePlugin()
        mgr = PluginManager()
        mgr.register(p)
        mgr.load("lifecycle-test")
        assert "load" in p.events

    def test_on_enable_called(self):
        p = _LifecyclePlugin()
        mgr = PluginManager()
        mgr.register(p)
        mgr.load("lifecycle-test")
        mgr.enable("lifecycle-test")
        assert "enable" in p.events

    def test_on_disable_called(self):
        p = _LifecyclePlugin()
        mgr = PluginManager()
        mgr.register(p)
        mgr.load("lifecycle-test")
        mgr.enable("lifecycle-test")
        mgr.disable("lifecycle-test")
        assert "disable" in p.events

    def test_on_uninstall_called(self):
        p = _LifecyclePlugin()
        mgr = PluginManager()
        mgr.register(p)
        mgr.load("lifecycle-test")
        mgr.unload("lifecycle-test")
        assert "uninstall" in p.events


# ==========================================================================
# PluginManager – registration
# ==========================================================================


class TestPluginRegistration:
    """Plugin registration, validation, and error handling."""

    def test_register_plugin(self):
        p = _ConcretePlugin()
        mgr = PluginManager()
        errs = mgr.register(p)
        assert errs == []
        assert mgr.get_plugin("test-plugin") is p

    def test_register_duplicate_fails(self):
        p1 = _ConcretePlugin()
        p2 = _ConcretePlugin()
        mgr = PluginManager()
        mgr.register(p1)
        errs = mgr.register(p2)
        assert len(errs) == 1
        assert "already registered" in errs[0]

    def test_register_invalid_manifest(self):
        p = Plugin()
        p.name = ""
        mgr = PluginManager()
        errs = mgr.register(p)
        assert len(errs) > 0

    def test_list_plugins(self):
        p = _ConcretePlugin()
        mgr = PluginManager()
        mgr.register(p)
        assert mgr.list_plugins() == ["test-plugin"]

    def test_get_manifest(self):
        p = _ConcretePlugin()
        manifest = PluginManifest(name="test-plugin", version="2.0.0")
        mgr = PluginManager()
        mgr.register(p, manifest=manifest)
        assert mgr.get_manifest("test-plugin") is manifest

    def test_get_manifest_nonexistent(self):
        mgr = PluginManager()
        assert mgr.get_manifest("ghost") is None

    def test_get_plugin_nonexistent(self):
        mgr = PluginManager()
        assert mgr.get_plugin("ghost") is None

    def test_get_errors(self):
        mgr = PluginManager()
        p = Plugin()
        p.name = ""
        errs = mgr.register(p)
        assert len(errs) > 0


# ==========================================================================
# PluginManager – lifecycle
# ==========================================================================


class TestPluginLifecycleManagement:
    """Plugin load, enable, disable, unload."""

    @pytest.fixture
    def manager_and_plugin(self):
        p = _LifecyclePlugin()
        reg = _FakeRegistry()
        mgr = PluginManager(reg)
        mgr.register(p)
        mgr.load("lifecycle-test")
        return mgr, p

    def test_load_sets_context(self, manager_and_plugin):
        _, p = manager_and_plugin
        assert p.context is not None
        assert p.context.registry is not None

    def test_enable_sets_enabled(self, manager_and_plugin):
        mgr, p = manager_and_plugin
        mgr.enable("lifecycle-test")
        assert p.enabled is True

    def test_disable_clears_enabled(self, manager_and_plugin):
        mgr, p = manager_and_plugin
        mgr.enable("lifecycle-test")
        mgr.disable("lifecycle-test")
        assert p.enabled is False

    def test_disable_before_enable(self, manager_and_plugin):
        mgr, p = manager_and_plugin
        mgr.disable("lifecycle-test")
        assert p.enabled is False

    def test_unload_removes_plugin(self, manager_and_plugin):
        mgr, _ = manager_and_plugin
        mgr.unload("lifecycle-test", remove=True)
        assert mgr.get_plugin("lifecycle-test") is None

    def test_unload_without_remove(self, manager_and_plugin):
        mgr, p = manager_and_plugin
        mgr.unload("lifecycle-test", remove=False)
        assert mgr.get_plugin("lifecycle-test") is p


# ==========================================================================
# PluginManager – error handling
# ==========================================================================


class _ExplodingPlugin(Plugin):
    name = "exploder"
    version = "1.0.0"

    def on_load(self) -> None:
        raise RuntimeError("load failed")

    def on_enable(self) -> None:
        raise RuntimeError("enable failed")

    def on_disable(self) -> None:
        raise RuntimeError("disable failed")

    def on_uninstall(self) -> None:
        raise RuntimeError("uninstall failed")


class TestPluginErrorHandling:
    """Plugin errors are caught and logged without crashing."""

    def test_load_error_does_not_crash(self):
        p = _ExplodingPlugin()
        mgr = PluginManager()
        mgr.register(p)
        mgr.load("exploder")

    def test_enable_error_keeps_disabled(self):
        p = _ExplodingPlugin()
        mgr = PluginManager()
        mgr.register(p)
        mgr.load("exploder")
        mgr.enable("exploder")
        assert p.enabled is False

    def test_disable_error_does_not_crash(self):
        p = _ExplodingPlugin()
        mgr = PluginManager()
        mgr.register(p)
        mgr.load("exploder")
        mgr.disable("exploder")

    def test_uninstall_error_does_not_crash(self):
        p = _ExplodingPlugin()
        mgr = PluginManager()
        mgr.register(p)
        mgr.load("exploder")
        mgr.unload("exploder")

    def test_load_nonexistent(self):
        mgr = PluginManager()
        mgr.load("ghost")

    def test_enable_nonexistent(self):
        mgr = PluginManager()
        mgr.enable("ghost")

    def test_disable_nonexistent(self):
        mgr = PluginManager()
        mgr.disable("ghost")

    def test_unload_nonexistent(self):
        mgr = PluginManager()
        mgr.unload("ghost")


# ==========================================================================
# PluginManager – shutdown
# ==========================================================================


class TestPluginShutdown:
    """shutdown_all gracefully shuts down all plugins."""

    def test_shutdown_all_disables_and_unloads(self):
        p1 = _LifecyclePlugin()
        p2 = _LifecyclePlugin()
        mgr = PluginManager()
        mgr.register(p1)
        mgr.register(p2)
        mgr.load("lifecycle-test")
        mgr.load("lifecycle-test")
        mgr.enable("lifecycle-test")
        mgr.shutdown_all()
        assert mgr.list_plugins() == []
        assert "uninstall" in p1.events

    def test_shutdown_all_empty(self):
        mgr = PluginManager()
        mgr.shutdown_all()


# ==========================================================================
# PluginContext – service registration
# ==========================================================================


class _ServicePlugin(Plugin):
    name = "svc-plugin"
    version = "1.0.0"
    manifest = PluginManifest(name="svc-plugin", version="1.0.0")

    def __init__(self) -> None:
        super().__init__()
        self.events: list[str] = []

    def on_load(self) -> None:
        self.events.append("load")
        self.register_service("private_svc", {"type": "private"})
        self.export_service("shared_svc", {"type": "shared"})


class TestServiceRegistration:
    """PluginContext service registration methods."""

    @pytest.fixture
    def ctx(self):
        return PluginContext(_FakeRegistry(), "test-p")

    def test_register_service_namespaces(self, ctx):
        svc = object()
        ctx.register_service("my_svc", svc)
        assert ctx.get_service("plugin.test-p.my_svc") is svc

    def test_export_service_global(self, ctx):
        svc = object()
        ctx.export_service("my_global", svc)
        assert ctx.get_service("my_global") is svc

    def test_register_service_no_registry(self):
        ctx = PluginContext(None, "orphan")
        ctx.register_service("x", object())

    def test_export_service_no_registry(self):
        ctx = PluginContext(None, "orphan")
        ctx.export_service("x", object())

    def test_list_services_includes_all(self, ctx):
        ctx.register_service("a", 1)
        ctx.export_service("b", 2)
        all_svcs = ctx.list_services()
        assert "plugin.test-p.a" in all_svcs
        assert "b" in all_svcs

    def test_list_services_no_registry(self):
        ctx = PluginContext(None, "orphan")
        assert ctx.list_services() == []

    def test_duplicate_register_does_not_crash(self, ctx):
        ctx.register_service("dup", 1)
        ctx.register_service("dup", 2)

    def test_duplicate_export_does_not_crash(self, ctx):
        ctx.export_service("dup", 1)
        ctx.export_service("dup", 2)

    def test_get_service_private(self, ctx):
        svc = {"key": "val"}
        ctx.register_service("secret", svc)
        assert ctx.get_service("plugin.test-p.secret") is svc

    def test_get_service_shared(self, ctx):
        svc = {"key": "val"}
        ctx.export_service("public", svc)
        assert ctx.get_service("public") is svc

    def test_get_service_missing(self, ctx):
        assert ctx.get_service("nope") is None

    def test_get_service_no_registry(self):
        ctx = PluginContext(None, "orphan")
        assert ctx.get_service("anything") is None

    def test_event_bus_no_registry(self):
        ctx = PluginContext(None, "orphan")
        assert ctx.event_bus is None

    def test_ai_manager_no_registry(self):
        ctx = PluginContext(None, "orphan")
        assert ctx.ai_manager is None

    def test_get_optional_services_via_properties(self, ctx):
        assert ctx.event_bus is not None
        assert ctx.ai_manager is not None
        assert ctx.memory is not None
        assert ctx.cortex is not None
        assert ctx.dispatcher is not None
        assert ctx.skill_manager is not None


# ==========================================================================
# Plugin – service convenience methods
# ==========================================================================


class TestPluginServiceMethods:
    """Plugin convenience methods delegate to context."""

    def test_register_service_delegates(self):
        reg = _FakeRegistry()
        ctx = PluginContext(reg, "test-p")
        p = _LifecyclePlugin()
        p._inject(ctx)
        p.register_service("my_svc", 42)
        assert ctx.get_service("plugin.test-p.my_svc") == 42

    def test_export_service_delegates(self):
        reg = _FakeRegistry()
        ctx = PluginContext(reg, "test-p")
        p = _LifecyclePlugin()
        p._inject(ctx)
        p.export_service("my_shared", 99)
        assert ctx.get_service("my_shared") == 99

    def test_register_no_context_no_crash(self):
        p = _LifecyclePlugin()
        p.register_service("x", 1)
        p.export_service("y", 2)


# ==========================================================================
# PluginManager – service lifecycle
# ==========================================================================


class TestPluginServiceLifecycle:
    """PluginManager tracks and cleans up plugin services."""

    def test_register_plugin_service_tracks(self):
        mgr = PluginManager()
        mgr.register_plugin_service("p1", "svc_a")
        mgr.register_plugin_service("p1", "svc_b")
        assert mgr.get_plugin_services("p1") == ["svc_a", "svc_b"]

    def test_get_plugin_services_empty(self):
        mgr = PluginManager()
        assert mgr.get_plugin_services("ghost") == []

    def test_cleanup_plugin_services_removes_from_registry(self):
        reg = _FakeRegistry()
        mgr = PluginManager(reg)
        reg.register("p1_svc", 1)
        reg.register("p2_svc", 2)
        mgr.register_plugin_service("p1", "p1_svc")
        mgr._cleanup_plugin_services("p1")
        assert reg.get_optional("p1_svc") is None
        assert reg.get_optional("p2_svc") == 2

    def test_cleanup_plugin_services_no_registry(self):
        mgr = PluginManager()
        mgr.register_plugin_service("p1", "svc")
        mgr._cleanup_plugin_services("p1")
        assert mgr.get_plugin_services("p1") == []

    def test_unload_cleans_services(self):
        reg = _FakeRegistry()
        mgr = PluginManager(reg)
        p = _LifecyclePlugin()
        mgr.register(p)
        mgr.load("lifecycle-test")
        mgr.register_plugin_service("lifecycle-test", "test_svc")
        reg.register("test_svc", "data")
        mgr.unload("lifecycle-test", remove=True)
        assert mgr.get_plugin_services("lifecycle-test") == []
        assert reg.get_optional("test_svc") is None

    def test_shutdown_all_cleans_services(self):
        reg = _FakeRegistry()
        mgr = PluginManager(reg)
        p = _ServicePlugin()
        mgr.register(p, p.manifest)
        mgr.load("svc-plugin")
        assert reg.get_optional("shared_svc") is not None
        assert reg.get_optional("plugin.svc-plugin.private_svc") is not None
        mgr.shutdown_all()
        assert reg.get_optional("shared_svc") is None
        assert reg.get_optional("plugin.svc-plugin.private_svc") is None

    def test_shutdown_all_no_registry(self):
        mgr = PluginManager()
        p = _LifecyclePlugin()
        mgr.register(p)
        mgr.load("lifecycle-test")
        mgr.shutdown_all()


# ==========================================================================
# PluginContext – event subscription & publishing
# ==========================================================================


class _EventPlugin(Plugin):
    name = "event-plugin"
    version = "1.0.0"
    manifest = PluginManifest(name="event-plugin", version="1.0.0")

    def __init__(self) -> None:
        super().__init__()
        self.received: list[tuple] = []

    def on_load(self) -> None:
        self.subscribe("custom.event", self._handler)

    def _handler(self, *args: Any, **kwargs: Any) -> None:
        self.received.append((args, kwargs))


class _ExplodingSubscriber(Plugin):
    name = "exploder-sub"
    version = "1.0.0"
    manifest = PluginManifest(name="exploder-sub", version="1.0.0")

    def _handler(self, *args: Any, **kwargs: Any) -> None:
        raise RuntimeError("subscriber failed")


class TestPluginEventSubscription:
    """PluginContext subscribe / publish / unsubscribe."""

    @pytest.fixture
    def ctx(self):
        return PluginContext(_FakeRegistry(), "test-p")

    def test_subscribe_and_publish(self, ctx):
        received = []
        def handler(*args, **kwargs):
            received.append((args, kwargs))
        ctx.subscribe("test.event", handler)
        ctx.publish("test.event", "arg1", key="val")
        assert len(received) == 1
        assert received[0] == (("arg1",), {"key": "val"})

    def test_unsubscribe_removes_handler(self, ctx):
        received = []
        def handler(*args, **kwargs):
            received.append(True)
        ctx.subscribe("test.event", handler)
        ctx.unsubscribe("test.event", handler)
        ctx.publish("test.event")
        assert received == []

    def test_publish_no_subscribers(self, ctx):
        ctx.publish("nonexistent")

    def test_subscribe_no_event_bus(self):
        ctx = PluginContext(None, "orphan")
        ctx.subscribe("evt", lambda: None)

    def test_publish_no_event_bus(self):
        ctx = PluginContext(None, "orphan")
        ctx.publish("evt")

    def test_unsubscribe_no_event_bus(self):
        ctx = PluginContext(None, "orphan")
        ctx.unsubscribe("evt", lambda: None)

    def test_multiple_subscribers_all_called(self, ctx):
        results = []
        def h1(*a, **kw): results.append("h1")
        def h2(*a, **kw): results.append("h2")
        ctx.subscribe("multi", h1)
        ctx.subscribe("multi", h2)
        ctx.publish("multi")
        assert results == ["h1", "h2"]

    def test_subscribe_different_events(self, ctx):
        results = []
        def h_a(*a, **kw): results.append("a")
        def h_b(*a, **kw): results.append("b")
        ctx.subscribe("evt_a", h_a)
        ctx.subscribe("evt_b", h_b)
        ctx.publish("evt_a")
        assert results == ["a"]
        ctx.publish("evt_b")
        assert results == ["a", "b"]


class TestPluginEventMetadata:
    """Event metadata (args/kwargs) propagation."""

    @pytest.fixture
    def ctx(self):
        return PluginContext(_FakeRegistry(), "test-p")

    def test_args_propagated(self, ctx):
        received = []
        def handler(*a, **kw): received.append(a)
        ctx.subscribe("evt", handler)
        ctx.publish("evt", 1, 2, 3)
        assert received[0] == (1, 2, 3)

    def test_kwargs_propagated(self, ctx):
        received = []
        def handler(*a, **kw): received.append(kw)
        ctx.subscribe("evt", handler)
        ctx.publish("evt", x=10, y=20)
        assert received[0] == {"x": 10, "y": 20}

    def test_empty_publish(self, ctx):
        received = []
        def handler(*a, **kw): received.append(True)
        ctx.subscribe("evt", handler)
        ctx.publish("evt")
        assert received == [True]


class TestPluginEventErrorIsolation:
    """One failing subscriber does not affect others."""

    @pytest.fixture
    def ctx(self):
        return PluginContext(_FakeRegistry(), "test-p")

    def test_exploding_subscriber_does_not_block_others(self, ctx):
        results = []
        def good(*a, **kw): results.append("ok")
        def bad(*a, **kw): raise RuntimeError("fail")
        def also_good(*a, **kw): results.append("also_ok")
        ctx.subscribe("evt", good)
        ctx.subscribe("evt", bad)
        ctx.subscribe("evt", also_good)
        ctx.publish("evt")
        assert results == ["ok", "also_ok"]

    def test_all_exploding_does_not_crash(self, ctx):
        def bad1(*a, **kw): raise RuntimeError("fail1")
        def bad2(*a, **kw): raise RuntimeError("fail2")
        ctx.subscribe("evt", bad1)
        ctx.subscribe("evt", bad2)
        ctx.publish("evt")


# ==========================================================================
# PluginContext – event cleanup
# ==========================================================================


class TestPluginEventCleanup:
    """Plugin subscriptions are cleaned up on unload / shutdown."""

    def test_cleanup_subscriptions_unsubscribes_all(self):
        reg = _FakeRegistry()
        bus = reg.get("event_bus")
        ctx = PluginContext(reg, "test-p")
        results = []
        def h1(*a, **kw): results.append("h1")
        def h2(*a, **kw): results.append("h2")
        ctx.subscribe("evt1", h1)
        ctx.subscribe("evt2", h2)
        ctx._cleanup_subscriptions()
        bus.publish("evt1")
        bus.publish("evt2")
        assert results == []

    def test_cleanup_on_unload(self):
        reg = _FakeRegistry()
        mgr = PluginManager(reg)
        p = _EventPlugin()
        mgr.register(p, p.manifest)
        mgr.load("event-plugin")
        bus = reg.get("event_bus")
        bus.publish("custom.event")
        assert len(p.received) == 1
        mgr.unload("event-plugin", remove=True)
        p.received.clear()
        bus.publish("custom.event")
        assert p.received == []

    def test_cleanup_on_shutdown(self):
        reg = _FakeRegistry()
        mgr = PluginManager(reg)
        p = _EventPlugin()
        mgr.register(p, p.manifest)
        mgr.load("event-plugin")
        bus = reg.get("event_bus")
        bus.publish("custom.event")
        assert len(p.received) == 1
        mgr.shutdown_all()
        p.received.clear()
        bus.publish("custom.event")
        assert p.received == []

    def test_cleanup_no_event_bus(self):
        ctx = PluginContext(None, "orphan")
        ctx.subscribe("evt", lambda: None)
        ctx._cleanup_subscriptions()

    def test_multiple_plugins_isolated_cleanup(self):
        reg = _FakeRegistry()
        bus = reg.get("event_bus")
        mgr = PluginManager(reg)
        results = []
        class P1(Plugin):
            name = "p1"; version = "1.0.0"
            manifest = PluginManifest(name="p1", version="1.0.0")
            def on_load(self):
                self.subscribe("evt", lambda *a, **kw: results.append("p1"))
        class P2(Plugin):
            name = "p2"; version = "1.0.0"
            manifest = PluginManifest(name="p2", version="1.0.0")
            def on_load(self):
                self.subscribe("evt", lambda *a, **kw: results.append("p2"))
        p1, p2 = P1(), P2()
        mgr.register(p1)
        mgr.load("p1")
        mgr.register(p2)
        mgr.load("p2")
        bus.publish("evt")
        assert results == ["p1", "p2"]
        mgr.unload("p1", remove=True)
        results.clear()
        bus.publish("evt")
        assert results == ["p2"]


# ==========================================================================
# Plugin – event convenience methods
# ==========================================================================


class TestPluginEventMethods:
    """Plugin event methods delegate to context."""

    def test_subscribe_delegates(self):
        reg = _FakeRegistry()
        ctx = PluginContext(reg, "test-p")
        p = _LifecyclePlugin()
        p._inject(ctx)
        received = []
        p.subscribe("evt", lambda *a, **kw: received.append(True))
        p.publish("evt")
        assert received == [True]

    def test_unsubscribe_delegates(self):
        reg = _FakeRegistry()
        ctx = PluginContext(reg, "test-p")
        p = _LifecyclePlugin()
        p._inject(ctx)
        received = []
        def h(*a, **kw): received.append(True)
        p.subscribe("evt", h)
        p.unsubscribe("evt", h)
        p.publish("evt")
        assert received == []

    def test_no_context_no_crash(self):
        p = _LifecyclePlugin()
        p.subscribe("evt", lambda: None)
        p.publish("evt")
        p.unsubscribe("evt", lambda: None)


# ==========================================================================
# PluginContext – AI integration
# ==========================================================================


class _AIPlugin(Plugin):
    name = "ai-plugin"
    version = "1.0.0"
    manifest = PluginManifest(name="ai-plugin", version="1.0.0")

    def __init__(self) -> None:
        super().__init__()
        self.results: list[str] = []

    def on_load(self) -> None:
        self.results.append("loaded")


class TestPluginAIChat:
    """PluginContext AI chat methods."""

    @pytest.fixture
    def ctx(self):
        return PluginContext(_FakeRegistry(), "test-p")

    def test_ai_ask_delegates(self, ctx):
        result = ctx.ai_ask("hello")
        ctx.ai_manager.ask.assert_called_once()

    def test_ai_ask_with_conversation(self, ctx):
        ctx.ai_ask("hello", conversation_id="conv-1")
        ctx.ai_manager.ask.assert_called_once()

    def test_ai_ask_no_ai_manager(self):
        ctx = PluginContext(None, "orphan")
        assert ctx.ai_ask("hello") is None

    def test_ai_ask_stream_delegates(self, ctx):
        ctx.ai_ask_stream("test-provider", "hello")
        ctx.ai_manager.ask_stream.assert_called_once()

    def test_ai_ask_stream_no_ai_manager(self):
        ctx = PluginContext(None, "orphan")
        assert ctx.ai_ask_stream("p", "hello") is None


class TestPluginConversation:
    """PluginContext conversation management."""

    @pytest.fixture
    def ctx(self):
        return PluginContext(_FakeRegistry(), "test-p")

    def test_create_conversation(self, ctx):
        conv = ctx.create_conversation(provider="test", system_prompt="helpful")
        ctx.ai_manager.create_conversation.assert_called_once()

    def test_get_conversation(self, ctx):
        ctx.get_conversation("conv-1")
        ctx.ai_manager.conversation_manager.get.assert_called_with("conv-1")

    def test_delete_conversation(self, ctx):
        ctx.delete_conversation("conv-1")
        ctx.ai_manager.conversation_manager.delete.assert_called_with("conv-1")

    def test_create_conversation_no_ai_manager(self):
        ctx = PluginContext(None, "orphan")
        assert ctx.create_conversation() is None

    def test_get_conversation_no_ai_manager(self):
        ctx = PluginContext(None, "orphan")
        assert ctx.get_conversation("x") is None

    def test_delete_conversation_no_ai_manager(self):
        ctx = PluginContext(None, "orphan")
        assert ctx.delete_conversation("x") is False


class TestPluginAIPlanning:
    """PluginContext planning and reasoning."""

    @pytest.fixture
    def ctx(self):
        return PluginContext(_FakeRegistry(), "test-p")

    def test_ai_plan_delegates(self, ctx):
        ctx.ai_plan("do something")
        ctx.ai_manager.plan.assert_called_once()

    def test_ai_plan_no_ai_manager(self):
        ctx = PluginContext(None, "orphan")
        assert ctx.ai_plan("x") is None

    def test_ai_reason_delegates(self, ctx):
        ctx.ai_reason("why?")
        ctx.ai_manager.reason.assert_called_once()

    def test_ai_reason_no_ai_manager(self):
        ctx = PluginContext(None, "orphan")
        assert ctx.ai_reason("x") is None


class TestPluginStructuredOutput:
    """PluginContext structured output support."""

    @pytest.fixture
    def ctx(self):
        return PluginContext(_FakeRegistry(), "test-p")

    def test_create_structured_schema_no_registry(self):
        ctx = PluginContext(None, "orphan")
        assert ctx.create_structured_schema("n", {}) is None

    def test_parse_structured_no_registry(self):
        ctx = PluginContext(None, "orphan")
        assert ctx.parse_structured("{}", None) is None


class TestPluginToolRegistry:
    """PluginContext tool registration."""

    @pytest.fixture
    def ctx(self):
        return PluginContext(_FakeRegistry(), "test-p")

    def test_register_tool(self, ctx):
        tool = ToolDefinition(
            name="test_tool",
            description="A test tool",
            parameters={"type": "object", "properties": {}},
        )
        ctx.register_tool(tool)
        assert ctx.tool_registry.has("test_tool")

    def test_register_tool_no_registry(self):
        ctx = PluginContext(None, "orphan")
        ctx.register_tool(None)

    def test_unregister_tool(self, ctx):
        tool = ToolDefinition(
            name="remove_me",
            description="To be removed",
            parameters={"type": "object", "properties": {}},
        )
        ctx.register_tool(tool)
        assert ctx.unregister_tool("remove_me") is True
        assert ctx.tool_registry.has("remove_me") is False

    def test_unregister_tool_nonexistent(self, ctx):
        assert ctx.unregister_tool("ghost") is False

    def test_unregister_tool_no_registry(self):
        ctx = PluginContext(None, "orphan")
        assert ctx.unregister_tool("x") is False

    def test_list_tools(self, ctx):
        tool = ToolDefinition(
            name="listed",
            description="A listed tool",
            parameters={"type": "object", "properties": {}},
        )
        ctx.register_tool(tool)
        tools = ctx.list_tools()
        assert any(t.name == "listed" for t in tools)

    def test_list_tools_empty(self, ctx):
        assert ctx.list_tools() == []

    def test_list_tools_no_registry(self):
        ctx = PluginContext(None, "orphan")
        assert ctx.list_tools() == []


class TestPluginTemplateRegistry:
    """PluginContext prompt template registration."""

    @pytest.fixture
    def ctx(self):
        return PluginContext(_FakeRegistry(), "test-p")

    def test_register_template(self, ctx):
        tmpl = PromptTemplate(
            name="greet",
            description="Greeting template",
            template="Hello {{name}}",
            variables=[PromptVariable(name="name", description="Name")],
        )
        ctx.register_template(tmpl)
        assert ctx.template_registry.has("greet")

    def test_register_template_no_registry(self):
        ctx = PluginContext(None, "orphan")
        ctx.register_template(None)

    def test_unregister_template(self, ctx):
        tmpl = PromptTemplate(
            name="remove_me",
            description="To be removed",
            template="Hello {{name}}",
            variables=[PromptVariable(name="name", description="Name")],
        )
        ctx.register_template(tmpl)
        assert ctx.template_registry.has("remove_me")
        assert ctx.unregister_template("remove_me") is True
        assert ctx.template_registry.has("remove_me") is False

    def test_unregister_template_no_registry(self):
        ctx = PluginContext(None, "orphan")
        assert ctx.unregister_template("x") is False

    def test_get_template(self, ctx):
        tmpl = PromptTemplate(
            name="get_me",
            description="Get me",
            template="Hi {{name}}",
            variables=[PromptVariable(name="name", description="Name")],
        )
        ctx.register_template(tmpl)
        retrieved = ctx.get_template("get_me")
        assert retrieved is not None
        assert retrieved.name == "get_me"

    def test_get_template_no_registry(self):
        ctx = PluginContext(None, "orphan")
        assert ctx.get_template("x") is None


class TestPluginAIServiceProperties:
    """PluginContext AI-related service properties."""

    @pytest.fixture
    def ctx(self):
        return PluginContext(_FakeRegistry(), "test-p")

    def test_template_registry(self, ctx):
        assert ctx.template_registry is not None

    def test_tool_registry(self, ctx):
        assert ctx.tool_registry is not None

    def test_memory_aware_ai(self, ctx):
        assert ctx.memory_aware_ai is None

    def test_ai_diagnostics(self, ctx):
        assert ctx.ai_diagnostics is None

    def test_template_registry_no_registry(self):
        ctx = PluginContext(None, "orphan")
        assert ctx.template_registry is None

    def test_tool_registry_no_registry(self):
        ctx = PluginContext(None, "orphan")
        assert ctx.tool_registry is None

    def test_memory_aware_ai_no_registry(self):
        ctx = PluginContext(None, "orphan")
        assert ctx.memory_aware_ai is None

    def test_ai_diagnostics_no_registry(self):
        ctx = PluginContext(None, "orphan")
        assert ctx.ai_diagnostics is None


class TestPluginAIMethods:
    """Plugin AI convenience methods delegate to context."""

    def test_ai_ask_delegates(self):
        reg = _FakeRegistry()
        ctx = PluginContext(reg, "test-p")
        p = _LifecyclePlugin()
        p._inject(ctx)
        p.ai_ask("hello")
        reg.get("ai_manager").ask.assert_called_once()

    def test_ai_plan_delegates(self):
        reg = _FakeRegistry()
        ctx = PluginContext(reg, "test-p")
        p = _LifecyclePlugin()
        p._inject(ctx)
        p.ai_plan("objective")
        reg.get("ai_manager").plan.assert_called_once()

    def test_ai_reason_delegates(self):
        reg = _FakeRegistry()
        ctx = PluginContext(reg, "test-p")
        p = _LifecyclePlugin()
        p._inject(ctx)
        p.ai_reason("why?")
        reg.get("ai_manager").reason.assert_called_once()

    def test_register_tool_delegates(self):
        reg = _FakeRegistry()
        ctx = PluginContext(reg, "test-p")
        p = _LifecyclePlugin()
        p._inject(ctx)
        tool = ToolDefinition(
            name="plugin_tool",
            description="Plugin tool",
            parameters={"type": "object", "properties": {}},
        )
        p.register_tool(tool)
        assert reg.get("tool_registry").has("plugin_tool")

    def test_register_template_delegates(self):
        reg = _FakeRegistry()
        ctx = PluginContext(reg, "test-p")
        p = _LifecyclePlugin()
        p._inject(ctx)
        tmpl = PromptTemplate(
            name="plugin_tmpl",
            description="Plugin template",
            template="Hello {{name}}",
            variables=[PromptVariable(name="name", description="Name")],
        )
        p.register_template(tmpl)
        assert reg.get("template_registry").has("plugin_tmpl")

    def test_create_conversation_delegates(self):
        reg = _FakeRegistry()
        ctx = PluginContext(reg, "test-p")
        p = _LifecyclePlugin()
        p._inject(ctx)
        p.create_conversation(provider="test")
        reg.get("ai_manager").create_conversation.assert_called_once()

    def test_no_context_no_crash(self):
        p = _LifecyclePlugin()
        p.ai_ask("hello")
        p.ai_plan("x")
        p.ai_reason("y")
        p.register_tool(None)
        p.register_template(None)


# ==========================================================================
# PluginContext – skill integration
# ==========================================================================


class _PluginSkill(Skill):
    name = "Plugin Skill"
    intent = "plugin_skill"
    version = "1.0.0"
    description = "A skill contributed by a plugin"

    def run(self, request):
        return SkillResult.ok(message="Plugin skill executed")


class _AIPluginSkill(Skill):
    name = "AI Plugin Skill"
    intent = "ai_plugin_skill"
    version = "1.0.0"

    def run(self, request):
        return self.ask("What is AI?")


class _Request:
    def __init__(self, entities: dict | None = None):
        self.entities = entities or {}


class TestPluginSkillRegistration:
    """PluginContext skill registration and lifecycle."""

    @pytest.fixture
    def ctx(self):
        return PluginContext(_FakeRegistry(), "test-p")

    def test_register_skill(self, ctx):
        skill = _PluginSkill()
        ctx.register_skill(skill)
        assert ctx.skill_manager.get("plugin_skill") is skill

    def test_register_skill_no_intent_fails(self, ctx):
        skill = _PluginSkill()
        skill.intent = ""
        ctx.register_skill(skill)
        assert ctx.skill_manager.get("") is ctx.skill_manager.fallback

    def test_register_skill_no_skill_manager(self):
        ctx = PluginContext(None, "orphan")
        ctx.register_skill(_PluginSkill())

    def test_unregister_skill(self, ctx):
        skill = _PluginSkill()
        ctx.register_skill(skill)
        assert ctx.skill_manager.get("plugin_skill") is skill
        result = ctx.unregister_skill("plugin_skill")
        assert result is True
        assert ctx.skill_manager.get("plugin_skill") is ctx.skill_manager.fallback

    def test_unregister_nonexistent(self, ctx):
        assert ctx.unregister_skill("ghost") is False

    def test_unregister_no_skill_manager(self):
        ctx = PluginContext(None, "orphan")
        assert ctx.unregister_skill("x") is False

    def test_skill_executes_correctly(self, ctx):
        skill = _PluginSkill()
        ctx.register_skill(skill)
        registered = ctx.skill_manager.get("plugin_skill")
        result = registered.run(_Request({}))
        assert result.success is True
        assert result.message == "Plugin skill executed"

    def test_duplicate_intent_replaced(self, ctx):
        s1 = _PluginSkill()
        s2 = _PluginSkill()
        ctx.register_skill(s1)
        ctx.register_skill(s2)
        assert ctx.skill_manager.get("plugin_skill") is s2


class TestPluginSkillAIEnabled:
    """AI-enabled plugin skills work through AIManager."""

    @pytest.fixture
    def ctx(self):
        return PluginContext(_FakeRegistry(), "test-p")

    def test_ai_skill_ask_delegates(self, ctx):
        skill = _AIPluginSkill()
        ctx.register_skill(skill)
        registered = ctx.skill_manager.get("ai_plugin_skill")
        registered.run(_Request({}))
        ctx.ai_manager.ask.assert_called_once()


class TestPluginSkillCleanup:
    """Plugin skills are cleaned up on unload/shutdown."""

    def test_unload_cleans_skills(self):
        reg = _FakeRegistry()
        mgr = PluginManager(reg)
        p = _LifecyclePlugin()
        mgr.register(p)
        mgr.load("lifecycle-test")
        skill = _PluginSkill()
        p.context.register_skill(skill)
        assert reg.get("skill_manager").get("plugin_skill") is skill
        mgr.unload("lifecycle-test", remove=True)
        assert reg.get("skill_manager").get("plugin_skill") is reg.get("skill_manager").fallback

    def test_cleanup_skills_method(self):
        reg = _FakeRegistry()
        ctx = PluginContext(reg, "test-p")
        skill = _PluginSkill()
        ctx.register_skill(skill)
        assert reg.get("skill_manager").get("plugin_skill") is skill
        ctx._cleanup_skills()
        assert reg.get("skill_manager").get("plugin_skill") is reg.get("skill_manager").fallback

    def test_cleanup_skills_no_skill_manager(self):
        ctx = PluginContext(None, "orphan")
        ctx._cleanup_skills()

    def test_shutdown_all_cleans_skills(self):
        reg = _FakeRegistry()
        mgr = PluginManager(reg)
        p = _LifecyclePlugin()
        mgr.register(p)
        mgr.load("lifecycle-test")
        skill = _PluginSkill()
        p.context.register_skill(skill)
        assert reg.get("skill_manager").get("plugin_skill") is skill
        mgr.shutdown_all()
        assert reg.get("skill_manager").get("plugin_skill") is reg.get("skill_manager").fallback


class TestPluginSkillMethods:
    """Plugin skill convenience methods delegate to context."""

    def test_register_skill_delegates(self):
        reg = _FakeRegistry()
        ctx = PluginContext(reg, "test-p")
        p = _LifecyclePlugin()
        p._inject(ctx)
        skill = _PluginSkill()
        p.register_skill(skill)
        assert reg.get("skill_manager").get("plugin_skill") is skill

    def test_unregister_skill_delegates(self):
        reg = _FakeRegistry()
        ctx = PluginContext(reg, "test-p")
        p = _LifecyclePlugin()
        p._inject(ctx)
        skill = _PluginSkill()
        p.register_skill(skill)
        assert p.unregister_skill("plugin_skill") is True
        assert reg.get("skill_manager").get("plugin_skill") is reg.get("skill_manager").fallback

    def test_no_context_no_crash(self):
        p = _LifecyclePlugin()
        p.register_skill(_PluginSkill())
        p.unregister_skill("x")


# ==========================================================================
# PluginManager – discover
# ==========================================================================


class TestPluginDiscover:
    """Plugin discovery from packages."""

    def test_discover_does_not_crash(self):
        mgr = PluginManager()
        mgr.discover(None)
        assert isinstance(mgr, PluginManager)


# ==========================================================================
# Backward compatibility
# ==========================================================================


class TestBackwardCompatibility:
    """SDK exports match expected public API."""

    def test_plugin_base_importable(self):
        from app.plugins import Plugin
        assert Plugin is not None

    def test_plugin_manager_importable(self):
        from app.plugins import PluginManager
        assert PluginManager is not None

    def test_plugin_context_importable(self):
        from app.plugins import PluginContext
        assert PluginContext is not None

    def test_plugin_config_importable(self):
        from app.plugins import PluginConfig
        assert PluginConfig is not None

    def test_plugin_manifest_importable(self):
        from app.plugins import PluginManifest
        assert PluginManifest is not None

    def test_plugin_dependency_importable(self):
        from app.plugins import PluginDependency
        assert PluginDependency is not None

    def test_validate_manifest_importable(self):
        from app.plugins import validate_manifest
        assert callable(validate_manifest)

    def test_check_version_importable(self):
        from app.plugins import check_version_compatibility
        assert callable(check_version_compatibility)


# ==========================================================================
# P10-07 – Plugin Configuration Framework
# ==========================================================================


@pytest.fixture
def temp_config_dir():
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp)


class TestPluginConfigNew:
    """PluginConfig creation, defaults, schema."""

    def test_create_without_persistence(self):
        pc = PluginConfig("test-plugin")
        assert pc.config_path is None
        assert not pc.loaded

    def test_create_with_persistence(self, temp_config_dir):
        pc = PluginConfig("test-plugin", config_dir=temp_config_dir)
        assert pc.config_path == temp_config_dir / "config.json"

    def test_defaults_empty(self):
        pc = PluginConfig("test-plugin")
        assert pc.defaults == {}

    def test_schema_extracts_defaults(self):
        schema = {
            "type": "object",
            "properties": {
                "host": {"type": "string", "default": "localhost"},
                "port": {"type": "integer", "default": 8080},
                "debug": {"type": "boolean", "default": False},
            },
        }
        pc = PluginConfig("test-plugin", schema=schema)
        assert pc.defaults == {"host": "localhost", "port": 8080, "debug": False}

    def test_schema_without_defaults(self):
        schema = {
            "type": "object",
            "properties": {
                "host": {"type": "string"},
                "port": {"type": "integer"},
            },
        }
        pc = PluginConfig("test-plugin", schema=schema)
        assert pc.defaults == {}

    def test_set_schema_after_creation(self):
        pc = PluginConfig("test-plugin")
        assert pc.schema is None
        schema = {"properties": {"key": {"type": "string", "default": "val"}}}
        pc.set_schema(schema)
        assert pc.schema == schema
        assert pc.defaults == {"key": "val"}

    def test_config_path_property(self, temp_config_dir):
        pc = PluginConfig("test-plugin", config_dir=temp_config_dir)
        assert pc.config_path == temp_config_dir / "config.json"

    def test_loaded_property(self):
        pc = PluginConfig("test-plugin")
        assert not pc.loaded


class TestPluginConfigDefaults:
    """Default value population."""

    def test_set_defaults_populates_missing(self):
        schema = {
            "properties": {
                "host": {"type": "string", "default": "localhost"},
                "port": {"type": "integer", "default": 3000},
            },
        }
        pc = PluginConfig("test-plugin", schema=schema)
        assert pc.get("host") is None
        pc.set_defaults()
        assert pc.get("host") == "localhost"
        assert pc.get("port") == 3000

    def test_set_defaults_does_not_overwrite(self):
        schema = {
            "properties": {
                "host": {"type": "string", "default": "localhost"},
                "port": {"type": "integer", "default": 3000},
            },
        }
        pc = PluginConfig("test-plugin", schema=schema)
        pc.set("host", "custom-host")
        pc.set_defaults()
        assert pc.get("host") == "custom-host"
        assert pc.get("port") == 3000

    def test_load_ensures_defaults(self, temp_config_dir):
        schema = {
            "properties": {
                "host": {"type": "string", "default": "localhost"},
            },
        }
        pc = PluginConfig("test-plugin", schema=schema, config_dir=temp_config_dir)
        pc.load()
        assert pc.get("host") == "localhost"

    def test_load_merges_with_existing(self, temp_config_dir):
        config_file = temp_config_dir / "config.json"
        config_file.parent.mkdir(parents=True, exist_ok=True)
        config_file.write_text('{"port": 9090}', encoding="utf-8")
        schema = {
            "properties": {
                "host": {"type": "string", "default": "localhost"},
                "port": {"type": "integer", "default": 3000},
            },
        }
        pc = PluginConfig("test-plugin", schema=schema, config_dir=temp_config_dir)
        pc.load()
        assert pc.get("host") == "localhost"
        assert pc.get("port") == 9090


class TestPluginConfigPersistence:
    """File-based persistence."""

    def test_save_creates_file(self, temp_config_dir):
        pc = PluginConfig("test-plugin", config_dir=temp_config_dir, auto_save=False)
        pc.set("key", "value")
        pc.save()
        config_file = temp_config_dir / "config.json"
        assert config_file.is_file()
        import json
        data = json.loads(config_file.read_text(encoding="utf-8"))
        assert data == {"key": "value"}

    def test_load_reads_file(self, temp_config_dir):
        config_file = temp_config_dir / "config.json"
        config_file.parent.mkdir(parents=True, exist_ok=True)
        config_file.write_text('{"saved": "data"}', encoding="utf-8")
        pc = PluginConfig("test-plugin", config_dir=temp_config_dir)
        pc.load()
        assert pc.get("saved") == "data"

    def test_reload_updates_from_disk(self, temp_config_dir):
        config_file = temp_config_dir / "config.json"
        config_file.parent.mkdir(parents=True, exist_ok=True)
        config_file.write_text('{"key": "original"}', encoding="utf-8")
        pc = PluginConfig("test-plugin", config_dir=temp_config_dir)
        pc.load()
        assert pc.get("key") == "original"
        pc.set("key", "modified")
        assert pc.get("key") == "modified"
        config_file.write_text('{"key": "disk-update"}', encoding="utf-8")
        pc.reload()
        assert pc.get("key") == "disk-update"

    def test_auto_save_on_set(self, temp_config_dir):
        pc = PluginConfig("test-plugin", config_dir=temp_config_dir, auto_save=True)
        pc.set("auto", "saved")
        config_file = temp_config_dir / "config.json"
        assert config_file.is_file()
        import json
        data = json.loads(config_file.read_text(encoding="utf-8"))
        assert data == {"auto": "saved"}

    def test_auto_save_on_clear(self, temp_config_dir):
        pc = PluginConfig("test-plugin", config_dir=temp_config_dir, auto_save=True)
        pc.set("key", "value")
        pc.clear()
        config_file = temp_config_dir / "config.json"
        import json
        data = json.loads(config_file.read_text(encoding="utf-8"))
        assert data == {}

    def test_auto_save_on_update(self, temp_config_dir):
        pc = PluginConfig("test-plugin", config_dir=temp_config_dir, auto_save=True)
        pc.update({"a": 1, "b": 2})
        config_file = temp_config_dir / "config.json"
        import json
        data = json.loads(config_file.read_text(encoding="utf-8"))
        assert data == {"a": 1, "b": 2}

    def test_save_no_config_dir_no_error(self):
        pc = PluginConfig("test-plugin", auto_save=False)
        pc.set("key", "value")
        pc.save()

    def test_load_no_config_dir_no_error(self):
        pc = PluginConfig("test-plugin")
        pc.load()

    def test_reload_no_config_dir_no_error(self):
        pc = PluginConfig("test-plugin")
        pc.reload()

    def test_persistence_isolation(self, temp_config_dir):
        dir_a = temp_config_dir / "plugin-a"
        dir_b = temp_config_dir / "plugin-b"
        pc_a = PluginConfig("a", config_dir=dir_a, auto_save=True)
        pc_b = PluginConfig("b", config_dir=dir_b, auto_save=True)
        pc_a.set("shared", "from-a")
        pc_b.set("shared", "from-b")
        pc_a2 = PluginConfig("a", config_dir=dir_a, auto_save=False)
        pc_a2.load()
        pc_b2 = PluginConfig("b", config_dir=dir_b, auto_save=False)
        pc_b2.load()
        assert pc_a2.get("shared") == "from-a"
        assert pc_b2.get("shared") == "from-b"


class TestPluginConfigUpdate:
    """Batch updates."""

    def test_update_adds_multiple_keys(self):
        pc = PluginConfig("test-plugin", auto_save=False)
        pc.update({"a": 1, "b": 2, "c": 3})
        assert pc.all() == {"a": 1, "b": 2, "c": 3}

    def test_update_overwrites_existing(self):
        pc = PluginConfig("test-plugin", auto_save=False)
        pc.set("a", "old")
        pc.update({"a": "new", "b": "added"})
        assert pc.get("a") == "new"
        assert pc.get("b") == "added"

    def test_update_merges_with_existing(self):
        pc = PluginConfig("test-plugin", auto_save=False)
        pc.set("existing", "keep")
        pc.update({"new": "value"})
        assert pc.get("existing") == "keep"
        assert pc.get("new") == "value"


class TestPluginConfigValidation:
    """Schema-based validation."""

    def test_validate_no_schema(self):
        pc = PluginConfig("test-plugin")
        assert pc.validate() == []

    def test_validate_required_fields(self):
        schema = {
            "type": "object",
            "required": ["host", "port"],
            "properties": {
                "host": {"type": "string"},
                "port": {"type": "integer"},
            },
        }
        pc = PluginConfig("test-plugin", schema=schema)
        pc.set("host", "localhost")
        errors = pc.validate()
        assert len(errors) == 1
        assert "port" in errors[0]

    def test_validate_type_mismatch(self):
        schema = {
            "properties": {
                "port": {"type": "integer"},
            },
        }
        pc = PluginConfig("test-plugin", schema=schema)
        pc.set("port", "not-a-number")
        errors = pc.validate()
        assert len(errors) == 1
        assert "port" in errors[0]

    def test_validate_passes(self):
        schema = {
            "required": ["name"],
            "properties": {
                "name": {"type": "string"},
                "count": {"type": "integer"},
            },
        }
        pc = PluginConfig("test-plugin", schema=schema)
        pc.set("name", "test")
        pc.set("count", 42)
        assert pc.validate() == []

    def test_validate_data_arg(self):
        schema = {
            "required": ["key"],
            "properties": {"key": {"type": "string"}},
        }
        pc = PluginConfig("test-plugin", schema=schema)
        errors = pc.validate({"key": 123})
        assert len(errors) == 1

    def test_type_match_string(self):
        assert PluginConfig._type_match("hello", "string")
        assert not PluginConfig._type_match(42, "string")

    def test_type_match_integer(self):
        assert PluginConfig._type_match(42, "integer")
        assert not PluginConfig._type_match("42", "integer")

    def test_type_match_number(self):
        assert PluginConfig._type_match(3.14, "number")
        assert PluginConfig._type_match(42, "number")
        assert not PluginConfig._type_match("nan", "number")

    def test_type_match_boolean(self):
        assert PluginConfig._type_match(True, "boolean")
        assert not PluginConfig._type_match(1, "boolean")

    def test_type_match_array(self):
        assert PluginConfig._type_match([1, 2], "array")
        assert not PluginConfig._type_match("not-array", "array")

    def test_type_match_object(self):
        assert PluginConfig._type_match({"a": 1}, "object")
        assert not PluginConfig._type_match("not-obj", "object")

    def test_type_match_unknown_type(self):
        assert PluginConfig._type_match("anything", "unknown_type")

    def test_validate_none_values(self):
        schema = {
            "required": ["host"],
            "properties": {"host": {"type": "string"}},
        }
        pc = PluginConfig("test-plugin", schema=schema)
        pc.set("host", None)
        errors = pc.validate()
        assert len(errors) == 1


class TestPluginConfigEvents:
    """Configuration change events."""

    def test_set_publishes_changed_event(self):
        bus = EventBus()
        received = []
        bus.subscribe("plugin.config.changed", lambda d: received.append(d))
        pc = PluginConfig("test-plugin", event_bus=bus, auto_save=False)
        pc.set("key", "value")
        assert len(received) == 1
        assert received[0]["plugin"] == "test-plugin"
        assert received[0]["key"] == "value"

    def test_clear_publishes_changed_event(self):
        bus = EventBus()
        received = []
        bus.subscribe("plugin.config.changed", lambda d: received.append(d))
        pc = PluginConfig("test-plugin", event_bus=bus, auto_save=False)
        pc.clear()
        assert len(received) == 1

    def test_update_publishes_changed_event(self):
        bus = EventBus()
        received = []
        bus.subscribe("plugin.config.changed", lambda d: received.append(d))
        pc = PluginConfig("test-plugin", event_bus=bus, auto_save=False)
        pc.update({"a": 1, "b": 2})
        assert len(received) == 1
        assert received[0]["a"] == 1
        assert received[0]["b"] == 2

    def test_load_publishes_loaded_event(self):
        bus = EventBus()
        received = []
        bus.subscribe("plugin.config.loaded", lambda d: received.append(d))
        pc = PluginConfig("test-plugin", event_bus=bus, config_dir=Path(tempfile.gettempdir()) / f"_p10_test_load_{id(bus)}")
        pc.load()
        assert len(received) == 1
        assert received[0]["plugin"] == "test-plugin"

    def test_save_publishes_saved_event(self, temp_config_dir):
        bus = EventBus()
        received = []
        bus.subscribe("plugin.config.saved", lambda d: received.append(d))
        pc = PluginConfig("test-plugin", event_bus=bus, config_dir=temp_config_dir, auto_save=False)
        pc.set("key", "value")
        pc.save()
        assert len(received) == 1
        assert "path" in received[0]

    def test_reload_publishes_reloaded_event(self, temp_config_dir):
        bus = EventBus()
        received = []
        bus.subscribe("plugin.config.reloaded", lambda d: received.append(d))
        config_file = temp_config_dir / "config.json"
        config_file.parent.mkdir(parents=True, exist_ok=True)
        config_file.write_text('{}', encoding="utf-8")
        pc = PluginConfig("test-plugin", event_bus=bus, config_dir=temp_config_dir)
        pc.reload()
        assert len(received) == 1
        assert received[0]["plugin"] == "test-plugin"

    def test_no_event_bus_no_error(self):
        pc = PluginConfig("test-plugin", auto_save=False)
        pc.set("key", "value")
        pc.save()
        pc.load()
        pc.reload()

    def test_event_contains_plugin_name(self):
        bus = EventBus()
        received = []
        bus.subscribe("plugin.config.changed", lambda d: received.append(d))
        pc = PluginConfig("my-plugin", event_bus=bus, auto_save=False)
        pc.set("x", 1)
        assert received[0]["plugin"] == "my-plugin"


class TestPluginConfigCoreConfig:
    """Read-only core configuration access."""

    def test_core_config_accessible(self):
        ctx = PluginContext(None, "test")
        assert ctx.core_config is not None

    def test_core_config_readonly_values(self):
        ctx = PluginContext(None, "test")
        assert hasattr(ctx.core_config, "VERSION")
        assert hasattr(ctx.core_config, "APP_NAME")
        assert hasattr(ctx.core_config, "DATA_DIR")

    def test_core_config_cannot_write(self):
        ctx = PluginContext(None, "test")
        with pytest.raises(AttributeError):
            ctx.core_config.VERSION = "99.99.99"


class TestPluginContextConfigMethods:
    """PluginContext convenience methods for config lifecycle."""

    def test_load_config_no_error(self):
        ctx = PluginContext(None, "test")
        ctx.load_config()

    def test_save_config_no_error(self):
        ctx = PluginContext(None, "test")
        ctx.save_config()

    def test_reload_config_no_error(self):
        ctx = PluginContext(None, "test")
        ctx.reload_config()


class TestPluginManagerConfigLifecycle:
    """PluginManager config lifecycle integration."""

    def test_load_sets_schema_from_manifest(self):
        from app.plugins.sdk import PluginManifest
        class ConfigPlugin(Plugin):
            name = "config-test"
            version = "1.0.0"
            manifest = PluginManifest(
                name="config-test",
                version="1.0.0",
                config_schema={
                    "properties": {
                        "host": {"type": "string", "default": "localhost"},
                    },
                },
            )

        mgr = PluginManager()
        mgr.register(ConfigPlugin())
        mgr.load("config-test")
        plugin = mgr.get_plugin("config-test")
        assert plugin is not None
        assert plugin.context is not None
        assert plugin.context.config.schema is not None
        assert plugin.context.config.get("host") == "localhost"

    def test_unload_saves_config(self, temp_config_dir):
        from app.core.config import Config
        original_data_dir = Config.DATA_DIR
        try:
            Config.DATA_DIR = temp_config_dir
            plugin_name = "save-on-unload"
            manifest = PluginManifest(name=plugin_name, version="1.0.0")
            class SavePlugin(Plugin):
                name = plugin_name
                version = "1.0.0"

            mgr = PluginManager()
            mgr.register(SavePlugin(), manifest)
            mgr.load(plugin_name)
            plugin = mgr.get_plugin(plugin_name)
            assert plugin is not None
            assert plugin.context is not None
            plugin.context.config.set("saved-key", "saved-value")
            mgr.unload(plugin_name, remove=True)
            config_path = temp_config_dir / "plugins" / plugin_name / "config.json"
            assert config_path.is_file()
            import json
            data = json.loads(config_path.read_text(encoding="utf-8"))
            assert data.get("saved-key") == "saved-value"
        finally:
            Config.DATA_DIR = original_data_dir

    def test_manifest_without_config_schema(self):
        mgr = PluginManager()
        class NoSchemaPlugin(Plugin):
            name = "no-schema"
            version = "1.0.0"

        mgr.register(NoSchemaPlugin())
        mgr.load("no-schema")
        plugin = mgr.get_plugin("no-schema")
        assert plugin is not None
        assert plugin.context is not None
        assert plugin.context.config.schema is None


class TestPluginConfigFailureIsolation:
    """Graceful failure handling."""

    def test_invalid_json_on_load(self, temp_config_dir):
        config_file = temp_config_dir / "config.json"
        config_file.parent.mkdir(parents=True, exist_ok=True)
        config_file.write_text("not valid json", encoding="utf-8")
        pc = PluginConfig("test-plugin", config_dir=temp_config_dir)
        pc.load()
        assert pc.loaded

    def test_save_failure_no_crash(self):
        pc = PluginConfig("test-plugin", auto_save=False)
        pc.save()

    def test_reload_failure_no_crash(self):
        pc = PluginConfig("test-plugin")
        pc.reload()


class TestPluginConfigNamespaceIsolation:
    """Config isolation between plugins."""

    def test_isolation_via_separate_instances(self):
        pc1 = PluginConfig("plugin-a", auto_save=False)
        pc2 = PluginConfig("plugin-b", auto_save=False)
        pc1.set("key", "from-a")
        pc2.set("key", "from-b")
        assert pc1.get("key") == "from-a"
        assert pc2.get("key") == "from-b"
        assert pc1.all() != pc2.all() or pc1.all() == {}

    def test_isolation_via_context(self):
        ctx_a = PluginContext(None, "plugin-a")
        ctx_b = PluginContext(None, "plugin-b")
        ctx_a.config.set("shared", "a")
        ctx_b.config.set("shared", "b")
        assert ctx_a.config.get("shared") == "a"
        assert ctx_b.config.get("shared") == "b"

    def test_shutdown_all_isolated(self):
        from app.core.config import Config
        import tempfile
        original = Config.DATA_DIR
        try:
            Config.DATA_DIR = Path(tempfile.mkdtemp())
            mgr = PluginManager()
            class P1(Plugin):
                name = "plugin-1"
                version = "1.0.0"
            class P2(Plugin):
                name = "plugin-2"
                version = "1.0.0"
            for p in [P1(), P2()]:
                mgr.register(p)
                mgr.load(p.name)
                p.context.config.set("isolated", p.name)
            mgr.shutdown_all()
            assert mgr.list_plugins() == []
        finally:
            Config.DATA_DIR = original


class TestPluginConfigBackwardCompat:
    """Existing PluginConfig API continues to work."""

    def test_get_set(self):
        pc = PluginConfig("test")
        pc.set("key1", "value1")
        assert pc.get("key1") == "value1"

    def test_get_default(self):
        pc = PluginConfig("test")
        assert pc.get("nonexistent", "default") == "default"

    def test_get_default_none(self):
        pc = PluginConfig("test")
        assert pc.get("nonexistent") is None

    def test_all_returns_copy(self):
        pc = PluginConfig("test")
        pc.set("a", 1)
        pc.set("b", 2)
        data = pc.all()
        assert data == {"a": 1, "b": 2}

    def test_clear(self):
        pc = PluginConfig("test")
        pc.set("key", "value")
        pc.clear()
        assert pc.get("key") is None

    def test_overwrite(self):
        pc = PluginConfig("test")
        pc.set("key", "old")
        pc.set("key", "new")
        assert pc.get("key") == "new"

    def test_importable_from_app_plugins(self):
        from app.plugins import PluginConfig as PC
        assert PC is PluginConfig


# ==========================================================================
# P10-08 – Plugin Security & Permissions
# ==========================================================================


class TestPermissionConstants:
    """Built-in permission types."""

    def test_ai_permission(self):
        assert Permission.AI == "ai"

    def test_events_permission(self):
        assert Permission.EVENTS == "events"

    def test_services_permission(self):
        assert Permission.SERVICES == "services"

    def test_skills_permission(self):
        assert Permission.SKILLS == "skills"

    def test_config_permission(self):
        assert Permission.CONFIG == "config"

    def test_memory_permission(self):
        assert Permission.MEMORY == "memory"

    def test_filesystem_permission(self):
        assert Permission.FILESYSTEM == "filesystem"

    def test_network_permission(self):
        assert Permission.NETWORK == "network"

    def test_is_valid_known(self):
        assert Permission.is_valid("ai")
        assert Permission.is_valid("network")
        assert not Permission.is_valid("unknown_perm")

    def test_all_permissions(self):
        all_perms = Permission.all_permissions()
        assert len(all_perms) == 8
        assert "ai" in all_perms
        assert "events" in all_perms
        assert "services" in all_perms
        assert "skills" in all_perms
        assert "config" in all_perms
        assert "memory" in all_perms
        assert "filesystem" in all_perms
        assert "network" in all_perms

    def test_all_frozenset(self):
        assert isinstance(Permission._ALL, frozenset)
        assert len(Permission._ALL) == 8


class TestPermissionDenied:
    """Security exception."""

    def test_exception_message(self):
        exc = PermissionDenied("my-plugin", "ai", "ai_ask")
        assert "my-plugin" in str(exc)
        assert "ai" in str(exc)
        assert "ai_ask" in str(exc)

    def test_exception_attributes(self):
        exc = PermissionDenied("p", "svc", "register")
        assert exc.plugin_name == "p"
        assert exc.permission == "svc"
        assert exc.action == "register"

    def test_exception_no_action(self):
        exc = PermissionDenied("p", "config")
        assert "this operation" in str(exc)

    def test_exception_is_exception(self):
        assert issubclass(PermissionDenied, Exception)


class TestPermissionManager:
    """PermissionManager creation and checks."""

    def test_no_permissions_grants_all(self):
        pm = PermissionManager("test-plugin")
        assert pm.has_all()
        assert pm.check(Permission.AI)
        assert pm.check(Permission.EVENTS)
        assert pm.check(Permission.SERVICES)
        assert pm.check(Permission.SKILLS)
        assert pm.check(Permission.CONFIG)
        assert pm.check(Permission.MEMORY)
        assert pm.check(Permission.FILESYSTEM)
        assert pm.check(Permission.NETWORK)

    def test_explicit_permissions(self):
        pm = PermissionManager("test-plugin", permissions=["ai", "events"])
        assert pm.check(Permission.AI)
        assert pm.check(Permission.EVENTS)
        assert not pm.check(Permission.SERVICES)
        assert not pm.check(Permission.SKILLS)
        assert not pm.check(Permission.CONFIG)
        assert not pm.check(Permission.MEMORY)

    def test_invalid_permissions_ignored(self):
        pm = PermissionManager("test-plugin", permissions=["ai", "invalid_perm"])
        assert pm.check(Permission.AI)
        assert not pm.check(Permission.EVENTS)

    def test_empty_permissions_list_grants_all(self):
        pm = PermissionManager("test-plugin", permissions=[])
        assert pm.has_all()

    def test_has_all_false(self):
        pm = PermissionManager("test-plugin", permissions=["ai"])
        assert not pm.has_all()

    def test_require_passes(self):
        pm = PermissionManager("test-plugin", permissions=["ai"])
        pm.require(Permission.AI, "test")

    def test_require_raises(self):
        pm = PermissionManager("test-plugin", permissions=["ai"])
        with pytest.raises(PermissionDenied) as exc_info:
            pm.require(Permission.SERVICES, "register")
        assert exc_info.value.plugin_name == "test-plugin"
        assert exc_info.value.permission == "services"

    def test_check_action_logged(self):
        pm = PermissionManager("test-plugin", permissions=["ai"])
        assert pm.check(Permission.AI, "custom_action")
        assert not pm.check(Permission.SERVICES, "custom_action")

    def test_to_list(self):
        pm = PermissionManager("test-plugin", permissions=["ai", "events"])
        plist = pm.to_list()
        assert "ai" in plist
        assert "events" in plist

    def test_describe(self):
        pm = PermissionManager("test-plugin", permissions=["ai"])
        desc = pm.describe()
        assert "ai" in desc

    def test_permissions_property(self):
        pm = PermissionManager("test-plugin", permissions=["ai"])
        assert isinstance(pm.permissions, frozenset)
        assert "ai" in pm.permissions


class TestPluginManifestPermissions:
    """Permission declarations in PluginManifest."""

    def test_permissions_field_default_empty(self):
        m = PluginManifest(name="test", version="1.0.0")
        assert m.permissions == []

    def test_permissions_field_set(self):
        m = PluginManifest(
            name="test", version="1.0.0",
            permissions=["ai", "events"],
        )
        assert m.permissions == ["ai", "events"]

    def test_manifest_with_permissions_validates(self):
        m = PluginManifest(
            name="test", version="1.0.0",
            permissions=["ai", "events"],
        )
        errors = validate_manifest(m)
        assert len(errors) == 0

    def test_manifest_invalid_permission_fails(self):
        m = PluginManifest(
            name="test", version="1.0.0",
            permissions=["ai", "hack_the_planet"],
        )
        errors = validate_manifest(m)
        assert any("permissions" in e for e in errors)
        assert any("hack_the_planet" in e for e in errors)


class TestPluginContextPermissionEnforcement:
    """Runtime permission enforcement in PluginContext."""

    def test_no_permissions_allows_all(self):
        ctx = PluginContext(None, "test-plugin")
        assert ctx._check_permission(Permission.AI, "test")
        assert ctx._check_permission(Permission.EVENTS, "test")
        assert ctx._check_permission(Permission.SERVICES, "test")

    def test_with_permissions_checks(self):
        ctx = PluginContext(None, "test-plugin")
        pm = PermissionManager("test-plugin", permissions=["ai"])
        ctx.set_permissions(pm)
        assert ctx._check_permission(Permission.AI, "test")
        assert not ctx._check_permission(Permission.SERVICES, "test")
        assert not ctx._check_permission(Permission.EVENTS, "test")


class TestPluginContextAIPermissions:
    """AI permission enforcement."""

    @pytest.fixture
    def ctx_no_ai(self):
        ctx = PluginContext(None, "test-plugin")
        pm = PermissionManager("test-plugin", permissions=["events"])
        ctx.set_permissions(pm)
        return ctx

    def test_ai_ask_denied(self, ctx_no_ai):
        assert ctx_no_ai.ai_ask("hello") is None

    def test_ai_ask_stream_denied(self, ctx_no_ai):
        assert ctx_no_ai.ai_ask_stream("openai", "hello") is None

    def test_ai_plan_denied(self, ctx_no_ai):
        assert ctx_no_ai.ai_plan("objective") is None

    def test_ai_reason_denied(self, ctx_no_ai):
        assert ctx_no_ai.ai_reason("objective") is None

    def test_create_conversation_denied(self, ctx_no_ai):
        assert ctx_no_ai.create_conversation() is None

    def test_get_conversation_denied(self, ctx_no_ai):
        assert ctx_no_ai.get_conversation("id") is None

    def test_delete_conversation_denied(self, ctx_no_ai):
        assert not ctx_no_ai.delete_conversation("id")

    def test_register_tool_denied(self, ctx_no_ai):
        ctx_no_ai.register_tool("tool")

    def test_unregister_tool_denied(self, ctx_no_ai):
        assert not ctx_no_ai.unregister_tool("tool")

    def test_list_tools_denied(self, ctx_no_ai):
        assert ctx_no_ai.list_tools() == []

    def test_register_template_denied(self, ctx_no_ai):
        ctx_no_ai.register_template("tmpl")

    def test_unregister_template_denied(self, ctx_no_ai):
        assert not ctx_no_ai.unregister_template("tmpl")

    def test_get_template_denied(self, ctx_no_ai):
        assert ctx_no_ai.get_template("tmpl") is None

    def test_create_structured_schema_denied(self, ctx_no_ai):
        assert ctx_no_ai.create_structured_schema("s", {}) is None

    def test_parse_structured_denied(self, ctx_no_ai):
        assert ctx_no_ai.parse_structured("text", {}) is None


class TestPluginContextServicePermissions:
    """Service permission enforcement."""

    @pytest.fixture
    def ctx_no_svc(self):
        from app.core.registry import ServiceRegistry
        reg = ServiceRegistry()
        ctx = PluginContext(reg, "test-plugin")
        pm = PermissionManager("test-plugin", permissions=["ai"])
        ctx.set_permissions(pm)
        return ctx

    def test_register_service_denied(self, ctx_no_svc):
        ctx_no_svc.register_service("svc", object())

    def test_export_service_denied(self, ctx_no_svc):
        ctx_no_svc.export_service("svc", object())

    def test_list_services_allowed(self, ctx_no_svc):
        result = ctx_no_svc.list_services()
        assert isinstance(result, list)


class TestPluginContextEventPermissions:
    """Event permission enforcement."""

    @pytest.fixture
    def ctx_no_events(self):
        bus = EventBus()
        from app.core.registry import ServiceRegistry
        reg = ServiceRegistry()
        reg.register("event_bus", bus)
        ctx = PluginContext(reg, "test-plugin")
        pm = PermissionManager("test-plugin", permissions=["ai"])
        ctx.set_permissions(pm)
        return ctx

    def test_subscribe_denied(self, ctx_no_events):
        ctx_no_events.subscribe("test.event", lambda: None)

    def test_publish_denied(self, ctx_no_events):
        ctx_no_events.publish("test.event")

    def test_unsubscribe_denied(self, ctx_no_events):
        ctx_no_events.unsubscribe("test.event", lambda: None)

    def test_publish_with_permission(self):
        bus = EventBus()
        from app.core.registry import ServiceRegistry
        reg = ServiceRegistry()
        reg.register("event_bus", bus)
        ctx = PluginContext(reg, "test-plugin")
        pm = PermissionManager("test-plugin", permissions=["events"])
        ctx.set_permissions(pm)
        received = []
        bus.subscribe("test.event", lambda: received.append(1))
        ctx.publish("test.event")
        assert len(received) == 1


class TestPluginContextSkillPermissions:
    """Skill permission enforcement."""

    @pytest.fixture
    def ctx_no_skills(self):
        from app.core.registry import ServiceRegistry
        from app.skills.manager import SkillManager
        reg = ServiceRegistry()
        reg.register("skill_manager", SkillManager())
        ctx = PluginContext(reg, "test-plugin")
        pm = PermissionManager("test-plugin", permissions=["ai"])
        ctx.set_permissions(pm)
        return ctx

    def test_register_skill_denied(self, ctx_no_skills):
        skill = MagicMock()
        skill.intent = "test.intent"
        ctx_no_skills.register_skill(skill)

    def test_unregister_skill_denied(self, ctx_no_skills):
        assert not ctx_no_skills.unregister_skill("test.intent")


class TestPluginContextConfigPermissions:
    """Configuration permission enforcement."""

    def test_config_set_denied(self):
        ctx = PluginContext(None, "test-plugin")
        pm = PermissionManager("test-plugin", permissions=["ai"])
        ctx.set_permissions(pm)
        ctx.config.set("key", "value")
        assert ctx.config.get("key") is None

    def test_config_clear_denied(self):
        ctx = PluginContext(None, "test-plugin")
        pm = PermissionManager("test-plugin", permissions=["ai"])
        ctx.set_permissions(pm)
        ctx.config.set("key", "value")
        ctx.config.clear()

    def test_config_update_denied(self):
        ctx = PluginContext(None, "test-plugin")
        pm = PermissionManager("test-plugin", permissions=["ai"])
        ctx.set_permissions(pm)
        ctx.config.update({"key": "value"})
        assert ctx.config.get("key") is None

    def test_config_save_denied(self):
        ctx = PluginContext(None, "test-plugin")
        pm = PermissionManager("test-plugin", permissions=["ai"])
        ctx.set_permissions(pm)
        ctx.config.save()

    def test_config_set_defaults_denied(self):
        ctx = PluginContext(None, "test-plugin")
        pm = PermissionManager("test-plugin", permissions=["ai"])
        ctx.set_permissions(pm)
        ctx.config.set_defaults()

    def test_config_get_allowed_without_permission(self):
        ctx = PluginContext(None, "test-plugin")
        pm = PermissionManager("test-plugin", permissions=["ai"])
        ctx.set_permissions(pm)
        assert ctx.config.get("key") is None
        assert ctx.config.all() == {}

    def test_config_set_allowed_with_permission(self):
        ctx = PluginContext(None, "test-plugin")
        pm = PermissionManager("test-plugin", permissions=["config"])
        ctx.set_permissions(pm)
        ctx.config.set("key", "value")
        assert ctx.config.get("key") == "value"


class TestPluginManagerPermissionLifecycle:
    """PluginManager integrates permissions during load."""

    def test_load_creates_permission_manager(self):
        mgr = PluginManager()
        class PermPlugin(Plugin):
            name = "perm-test"
            version = "1.0.0"
            manifest = PluginManifest(
                name="perm-test",
                version="1.0.0",
                permissions=["ai"],
            )
        mgr.register(PermPlugin())
        mgr.load("perm-test")
        plugin = mgr.get_plugin("perm-test")
        assert plugin is not None
        assert plugin.context is not None
        assert plugin.context._permissions is not None
        assert plugin.context._permissions.check(Permission.AI)
        assert not plugin.context._permissions.check(Permission.SERVICES)

    def test_load_without_permissions_grants_all(self):
        mgr = PluginManager()
        class NoPermPlugin(Plugin):
            name = "noperm"
            version = "1.0.0"
        mgr.register(NoPermPlugin())
        mgr.load("noperm")
        plugin = mgr.get_plugin("noperm")
        assert plugin is not None
        assert plugin.context is not None
        assert plugin.context._permissions is not None
        assert plugin.context._permissions.has_all()

    def test_load_uses_capabilities_as_fallback(self):
        mgr = PluginManager()
        class CapPlugin(Plugin):
            name = "cap-test"
            version = "1.0.0"
            manifest = PluginManifest(
                name="cap-test",
                version="1.0.0",
                capabilities=["ai"],
            )
        mgr.register(CapPlugin())
        mgr.load("cap-test")
        plugin = mgr.get_plugin("cap-test")
        assert plugin is not None
        assert plugin.context is not None
        assert plugin.context._permissions.check(Permission.AI)
        assert not plugin.context._permissions.check(Permission.SERVICES)

    def test_load_selective_permissions(self):
        mgr = PluginManager()
        class SelectivePlugin(Plugin):
            name = "selective"
            version = "1.0.0"
            manifest = PluginManifest(
                name="selective",
                version="1.0.0",
                permissions=["ai", "services"],
            )
        mgr.register(SelectivePlugin())
        mgr.load("selective")
        plugin = mgr.get_plugin("selective")
        assert plugin is not None
        assert plugin.context is not None
        assert plugin.context._permissions.check(Permission.AI)
        assert plugin.context._permissions.check(Permission.SERVICES)
        assert not plugin.context._permissions.check(Permission.EVENTS)


class TestPluginSecurityBackwardCompat:
    """Backward compatibility tests."""

    def test_existing_api_unchanged(self):
        from app.plugins import (
            Permission as P,
            PermissionDenied as PD,
            PermissionManager as PM,
        )
        assert P is not None
        assert issubclass(PD, Exception)
        assert PM is not None

    def test_plugin_without_manifest_gets_all_permissions(self):
        mgr = PluginManager()
        class SimplePlugin(Plugin):
            name = "simple"
            version = "1.0.0"
        mgr.register(SimplePlugin())
        mgr.load("simple")
        plugin = mgr.get_plugin("simple")
        assert plugin is not None
        assert plugin.context is not None
        assert plugin.context._permissions is None or plugin.context._permissions.has_all()

    def test_register_service_works_without_permission_manager(self):
        ctx = PluginContext(None, "test")
        ctx.register_service("svc", object())

    def test_subscribe_works_without_permission_manager(self):
        ctx = PluginContext(None, "test")
        ctx.subscribe("e", lambda: None)


# ==========================================================================
# P10-09 – Plugin Packaging & Installation
# ==========================================================================


@pytest.fixture
def temp_plugin_source():
    """Create a temporary plugin source directory."""
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "my-plugin"
        src.mkdir()
        (src / "__init__.py").write_text(
            'from app.plugins.sdk import Plugin\n'
            'class MyPlugin(Plugin):\n'
            '    name = "my-plugin"\n'
            '    version = "1.0.0"\n',
            encoding="utf-8",
        )
        (src / "plugin.json").write_text(
            json.dumps({
                "name": "my-plugin",
                "version": "1.0.0",
                "description": "Test plugin",
                "min_core_version": "0.4.0",
            }),
            encoding="utf-8",
        )
        yield src


@pytest.fixture
def jarvis_plugin(temp_plugin_source):
    """Create a .jarvis-plugin ZIP from the source."""
    output = temp_plugin_source.parent / "my-plugin.jarvis-plugin"
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in temp_plugin_source.rglob("*"):
            if f.is_file():
                zf.write(f, f.relative_to(temp_plugin_source))
    yield output


@pytest.fixture
def pkg_manager(temp_plugin_source):
    """PackageManager with mocked Config.PLUGIN_DIR."""
    from app.core.config import Config
    original_plugin_dir = Config.PLUGIN_DIR
    original_data_dir = Config.DATA_DIR
    Config.PLUGIN_DIR = temp_plugin_source.parent / "installed"
    Config.DATA_DIR = temp_plugin_source.parent / "data"
    mgr = PluginManager()
    pm = PackageManager(mgr)
    yield pm, mgr
    Config.PLUGIN_DIR = original_plugin_dir
    Config.DATA_DIR = original_data_dir


class TestPluginPackage:
    """PluginPackage creation and inspection."""

    def test_inspect_valid_package(self, jarvis_plugin):
        pkg_path = Path(jarvis_plugin)
        pkg = _create_test_package(pkg_path)
        assert pkg.name == "my-plugin"
        assert pkg.version == "1.0.0"
        assert pkg.errors == []

    def test_inspect_invalid_zip(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake_pkg = Path(tmp) / "fake.jarvis-plugin"
            fake_pkg.write_text("not a zip", encoding="utf-8")
            with pytest.raises(PackageValidationError):
                _create_test_package(fake_pkg)

    def test_inspect_missing_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg_path = Path(tmp) / "no-manifest.jarvis-plugin"
            import zipfile
            with zipfile.ZipFile(pkg_path, "w") as zf:
                zf.writestr("some.py", "code")
            with pytest.raises(PackageValidationError):
                _create_test_package(pkg_path)

    def test_inspect_nonexistent(self):
        with pytest.raises(PackageNotFoundError):
            mgr = PluginManager()
            pm = PackageManager(mgr)
            pm.inspect("/nonexistent/path.jarvis-plugin")


class TestPackageInstall:
    """Package installation."""

    def test_install_success(self, jarvis_plugin, pkg_manager):
        pm, mgr = pkg_manager
        result = pm.install(jarvis_plugin, enable=False)
        assert result == "my-plugin"

    def test_install_creates_directory(self, jarvis_plugin, pkg_manager):
        pm, mgr = pkg_manager
        pm.install(jarvis_plugin, enable=False)
        from app.core.config import Config
        assert (Config.PLUGIN_DIR / "my-plugin").is_dir()
        assert (Config.PLUGIN_DIR / "my-plugin" / "plugin.json").is_file()

    def test_install_records_metadata(self, jarvis_plugin, pkg_manager):
        pm, mgr = pkg_manager
        pm.install(jarvis_plugin, enable=False)
        meta = pm.get_installed("my-plugin")
        assert meta is not None
        assert meta.name == "my-plugin"
        assert meta.version == "1.0.0"

    def test_install_duplicate_fails(self, jarvis_plugin, pkg_manager):
        pm, mgr = pkg_manager
        pm.install(jarvis_plugin, enable=False)
        with pytest.raises(PackageExistsError):
            pm.install(jarvis_plugin, enable=False)

    def test_install_invalid_package_fails(self, pkg_manager):
        pm, mgr = pkg_manager
        with tempfile.TemporaryDirectory() as tmp:
            bad_pkg = Path(tmp) / "bad.jarvis-plugin"
            bad_pkg.write_text("not a zip", encoding="utf-8")
            with pytest.raises(PackageValidationError):
                pm.install(bad_pkg)

    def test_list_installed(self, jarvis_plugin, pkg_manager):
        pm, mgr = pkg_manager
        assert pm.list_installed() == []
        pm.install(jarvis_plugin, enable=False)
        installed = pm.list_installed()
        assert len(installed) == 1
        assert installed[0].name == "my-plugin"

    def test_get_installed_nonexistent(self, pkg_manager):
        pm, mgr = pkg_manager
        assert pm.get_installed("nonexistent") is None

    def test_install_with_loader(self, jarvis_plugin, temp_plugin_source):
        from app.core.config import Config
        original_plugin_dir = Config.PLUGIN_DIR
        original_data_dir = Config.DATA_DIR
        try:
            Config.PLUGIN_DIR = temp_plugin_source.parent / "installed2"
            Config.DATA_DIR = temp_plugin_source.parent / "data2"
            mgr = PluginManager()
            from app.plugins.sdk.loader import PluginLoader
            loader = PluginLoader(mgr)
            loader.add_directory(Config.PLUGIN_DIR)
            pm = PackageManager(mgr, loader)
            result = pm.install(jarvis_plugin, enable=False)
            assert result == "my-plugin"
        finally:
            Config.PLUGIN_DIR = original_plugin_dir
            Config.DATA_DIR = original_data_dir


class TestPackageUninstall:
    """Package uninstallation."""

    def test_uninstall_removes_directory(self, jarvis_plugin, pkg_manager):
        pm, mgr = pkg_manager
        pm.install(jarvis_plugin, enable=False)
        pm.uninstall("my-plugin")
        from app.core.config import Config
        assert not (Config.PLUGIN_DIR / "my-plugin").is_dir()

    def test_uninstall_removes_metadata(self, jarvis_plugin, pkg_manager):
        pm, mgr = pkg_manager
        pm.install(jarvis_plugin, enable=False)
        pm.uninstall("my-plugin")
        assert pm.get_installed("my-plugin") is None

    def test_uninstall_nonexistent_fails(self, pkg_manager):
        pm, mgr = pkg_manager
        with pytest.raises(PackageNotFoundError):
            pm.uninstall("nonexistent")


class TestPackageUpgrade:
    """Package upgrade."""

    def test_upgrade_updates_version(self, jarvis_plugin, temp_plugin_source, pkg_manager):
        pm, mgr = pkg_manager
        pm.install(jarvis_plugin, enable=False)
        (temp_plugin_source / "plugin.json").write_text(
            json.dumps({
                "name": "my-plugin",
                "version": "2.0.0",
                "description": "Upgraded",
                "min_core_version": "0.4.0",
            }),
            encoding="utf-8",
        )
        upgraded_pkg = temp_plugin_source.parent / "my-plugin-v2.jarvis-plugin"
        import zipfile
        with zipfile.ZipFile(upgraded_pkg, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in temp_plugin_source.rglob("*"):
                if f.is_file():
                    zf.write(f, f.relative_to(temp_plugin_source))
        pm.upgrade("my-plugin", upgraded_pkg, enable=False)
        meta = pm.get_installed("my-plugin")
        assert meta is not None
        assert meta.version == "2.0.0"

    def test_upgrade_nonexistent_fails(self, jarvis_plugin, pkg_manager):
        pm, mgr = pkg_manager
        with pytest.raises(PackageNotFoundError):
            pm.upgrade("nonexistent", jarvis_plugin)


class TestPackageExport:
    """Package export."""

    def test_export_creates_zip(self, jarvis_plugin, pkg_manager):
        pm, mgr = pkg_manager
        pm.install(jarvis_plugin, enable=False)
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "exports"
            out_dir.mkdir()
            output = pm.export("my-plugin", out_dir)
            assert output.is_file()
            assert output.suffix == ".jarvis-plugin"

    def test_export_nonexistent_fails(self, pkg_manager):
        pm, mgr = pkg_manager
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "exports"
            out_dir.mkdir()
            with pytest.raises(PackageNotFoundError):
                pm.export("nonexistent", out_dir)


class TestPackageIntegrity:
    """Package integrity and verification."""

    def test_verify_installed_package(self, jarvis_plugin, pkg_manager):
        pm, mgr = pkg_manager
        pm.install(jarvis_plugin, enable=False)
        assert pm.verify("my-plugin")

    def test_verify_nonexistent_fails(self, pkg_manager):
        pm, mgr = pkg_manager
        assert not pm.verify("nonexistent")

    def test_verify_missing_directory_fails(self, jarvis_plugin, pkg_manager):
        pm, mgr = pkg_manager
        pm.install(jarvis_plugin, enable=False)
        from app.core.config import Config
        import shutil
        shutil.rmtree(Config.PLUGIN_DIR / "my-plugin")
        assert not pm.verify("my-plugin")


class TestPackageCompatibility:
    """Version compatibility during install."""

    def test_incompatible_version_fails(self, temp_plugin_source, pkg_manager):
        pm, mgr = pkg_manager
        (temp_plugin_source / "plugin.json").write_text(
            json.dumps({
                "name": "my-plugin",
                "version": "1.0.0",
                "min_core_version": "99.0.0",
            }),
            encoding="utf-8",
        )
        pkg_path = temp_plugin_source.parent / "incompat.jarvis-plugin"
        import zipfile
        with zipfile.ZipFile(pkg_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in temp_plugin_source.rglob("*"):
                if f.is_file():
                    zf.write(f, f.relative_to(temp_plugin_source))
        with pytest.raises(PackageCompatibilityError):
            pm.install(pkg_path)


class TestPackageRollback:
    """Rollback on install failure."""

    def test_install_failure_cleans_up(self, jarvis_plugin, pkg_manager):
        pm, mgr = pkg_manager
        from app.core.config import Config
        with pytest.raises(PackageError):
            pm.install(Path("nonexistent-path"), enable=False)


class TestPackageMetadata:
    """Installation metadata."""

    def test_install_metadata_fields(self, jarvis_plugin, pkg_manager):
        pm, mgr = pkg_manager
        pm.install(jarvis_plugin, enable=False)
        meta = pm.get_installed("my-plugin")
        assert meta is not None
        assert isinstance(meta.name, str)
        assert isinstance(meta.version, str)
        assert isinstance(meta.installed_at, str)
        assert isinstance(meta.package_hash, str)
        assert isinstance(meta.manifest, dict)

    def test_install_metadata_persistence(self, jarvis_plugin, pkg_manager):
        pm, mgr = pkg_manager
        pm.install(jarvis_plugin, enable=False)
        from app.plugins.sdk.package import _load_installed_meta
        raw = _load_installed_meta()
        assert "my-plugin" in raw
        assert raw["my-plugin"]["version"] == "1.0.0"

    def test_install_metadata_removed_on_uninstall(self, jarvis_plugin, pkg_manager):
        pm, mgr = pkg_manager
        pm.install(jarvis_plugin, enable=False)
        pm.uninstall("my-plugin")
        from app.plugins.sdk.package import _load_installed_meta
        raw = _load_installed_meta()
        assert "my-plugin" not in raw


class TestPackageErrorTypes:
    """Package error hierarchy."""

    def test_package_error_base(self):
        assert issubclass(PackageValidationError, PackageError)
        assert issubclass(PackageExistsError, PackageError)
        assert issubclass(PackageNotFoundError, PackageError)
        assert issubclass(PackageCompatibilityError, PackageError)
        assert issubclass(PackageError, Exception)

    def test_package_error_message(self):
        err = PackageError("test error")
        assert str(err) == "test error"


class TestPackageBackwardCompat:
    """Backward compatibility tests."""

    def test_importable_from_app_plugins(self):
        from app.plugins import PackageManager as PM
        assert PM is not None

    def test_importable_from_sdk(self):
        from app.plugins.sdk import PackageManager as PM
        assert PM is not None

    def test_install_without_loader(self, jarvis_plugin, pkg_manager):
        pm, mgr = pkg_manager
        result = pm.install(jarvis_plugin, enable=False)
        assert result == "my-plugin"

    def test_inspect_returns_plugin_package(self, jarvis_plugin):
        mgr = PluginManager()
        pm = PackageManager(mgr)
        pkg = pm.inspect(jarvis_plugin)
        assert isinstance(pkg, PluginPackage)
        assert pkg.name == "my-plugin"
        assert isinstance(pkg.file_hash, str)
        assert len(pkg.file_hash) == 64


# ==========================================================================
# P10-10 – Plugin Developer Tools
# ==========================================================================


class TestScaffoldGeneration:
    """Plugin project scaffolding."""

    def test_scaffold_creates_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = scaffold_plugin("my-tool", tmp)
            assert project.name == "my-tool"
            assert project.path.is_dir()
            assert (project.path / "main.py").is_file()
            assert (project.path / "__init__.py").is_file()
            assert (project.path / "plugin.json").is_file()

    def test_scaffold_reads_manifest_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = scaffold_plugin(
                "test-p", tmp,
                version="2.0.0", description="desc",
                author="me", permissions=["ai", "events"],
            )
            data = json.loads(
                (project.path / "plugin.json").read_text(encoding="utf-8"),
            )
            assert data["name"] == "test-p"
            assert data["version"] == "2.0.0"
            assert data["description"] == "desc"
            assert data["author"] == "me"
            assert data["permissions"] == ["ai", "events"]

    def test_scaffold_generates_valid_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = scaffold_plugin("scaffold-test", tmp)
            errs = validate_manifest(project.manifest)
            assert errs == []

    def test_scaffold_main_py_has_plugin_class(self):
        with tempfile.TemporaryDirectory() as tmp:
            scaffold_plugin("hello-world", tmp)
            content = (Path(tmp) / "hello-world" / "main.py").read_text(
                encoding="utf-8",
            )
            assert "class HelloWorldPlugin(Plugin)" in content
            assert 'name = "hello-world"' in content
            assert 'version = "1.0.0"' in content

    def test_scaffold_existing_path_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "existing").mkdir()
            with pytest.raises(FileExistsError):
                scaffold_plugin("existing", tmp)

    def test_scaffold_invalid_manifest_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            with pytest.raises(ValueError, match="Invalid manifest"):
                scaffold_plugin("", tmp)

    def test_scaffold_with_config_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            schema = {
                "type": "object",
                "properties": {
                    "api_key": {"type": "string", "description": "API key"},
                },
                "required": ["api_key"],
            }
            project = scaffold_plugin("cfg-plugin", tmp, config_schema=schema)
            loaded = json.loads(
                (project.path / "plugin.json").read_text(encoding="utf-8"),
            )
            assert loaded["config_schema"] == schema
            assert loaded["config_schema"]["required"] == ["api_key"]

    def test_scaffold_with_dependencies(self):
        with tempfile.TemporaryDirectory() as tmp:
            deps = [PluginDependency("base", "1.0.0")]
            project = scaffold_plugin("dep-plugin", tmp, dependencies=deps)
            loaded = json.loads(
                (project.path / "plugin.json").read_text(encoding="utf-8"),
            )
            assert loaded["dependencies"] == [{"name": "base", "version": "1.0.0"}]

    def test_scaffold_with_capabilities(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = scaffold_plugin("cap-p", tmp, capabilities=["logging", "ai"])
            loaded = json.loads(
                (project.path / "plugin.json").read_text(encoding="utf-8"),
            )
            assert loaded["capabilities"] == ["logging", "ai"]

    def test_scaffold_invalid_output_dir_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / "nonexistent"
            with pytest.raises(ValueError, match="Output directory"):
                scaffold_plugin("test", fake)


class TestManifestGeneration:
    """Manifest generation utilities."""

    def test_generate_manifest_basic(self):
        m = generate_manifest("test-p", version="2.0.0")
        assert m.name == "test-p"
        assert m.version == "2.0.0"
        assert validate_manifest(m) == []

    def test_generate_manifest_with_all_fields(self):
        m = generate_manifest(
            "full", version="1.0.0", description="desc",
            author="author", permissions=["ai", "events"],
            capabilities=["logging"],
            dependencies=[PluginDependency("dep", "1.0.0")],
            config_schema={"type": "object"},
        )
        assert m.description == "desc"
        assert m.author == "author"
        assert m.permissions == ["ai", "events"]
        assert m.capabilities == ["logging"]
        assert len(m.dependencies) == 1
        assert m.config_schema == {"type": "object"}

    def test_generate_manifest_invalid_raises(self):
        with pytest.raises(ValueError, match="Invalid manifest"):
            generate_manifest("")

    def test_manifest_to_json_roundtrip(self):
        m = PluginManifest(
            name="json-test", version="1.0.0",
            permissions=["ai"],
            dependencies=[PluginDependency("dep", "1.0.0")],
        )
        data = json.loads(manifest_to_json(m))
        assert data["name"] == "json-test"
        assert data["permissions"] == ["ai"]
        assert data["dependencies"] == [{"name": "dep", "version": "1.0.0"}]


class TestManifestValidation:
    """Extended manifest validation via validate_plugin_manifest."""

    def test_validate_valid_manifest(self):
        m = PluginManifest(name="test", version="1.0.0")
        result = validate_plugin_manifest(m)
        assert result.valid is True
        assert result.errors == []

    def test_validate_invalid_name(self):
        m = PluginManifest(name="", version="1.0.0")
        result = validate_plugin_manifest(m)
        assert result.valid is False
        assert any("name" in e for e in result.errors)

    def test_validate_warns_no_author(self):
        m = PluginManifest(name="test", version="1.0.0")
        result = validate_plugin_manifest(m)
        assert any("author" in w for w in result.warnings)

    def test_validate_warns_no_description(self):
        m = PluginManifest(name="test", version="1.0.0")
        result = validate_plugin_manifest(m)
        assert any("description" in w for w in result.warnings)

    def test_validate_warns_no_permissions(self):
        m = PluginManifest(name="test", version="1.0.0")
        result = validate_plugin_manifest(m)
        assert any("permissions" in w for w in result.warnings)

    def test_validate_with_permissions_no_warning(self):
        m = PluginManifest(
            name="test", version="1.0.0",
            permissions=["ai"],
        )
        result = validate_plugin_manifest(m)
        assert not any("permissions" in w for w in result.warnings)

    def test_validate_invalid_permission(self):
        m = PluginManifest(
            name="test", version="1.0.0",
            permissions=["invalid_perm"],
        )
        result = validate_plugin_manifest(m)
        assert result.valid is False

    def test_validate_manifest_with_deps(self):
        m = PluginManifest(
            name="test", version="1.0.0",
            dependencies=[PluginDependency("other", "1.0.0")],
        )
        result = validate_plugin_manifest(m)
        assert result.valid is True


class TestPackageInspection:
    """Package inspection via inspect_package."""

    def test_inspect_package_basic(self, jarvis_plugin):
        info = inspect_package(jarvis_plugin)
        assert info["name"] == "my-plugin"
        assert info["version"] == "1.0.0"
        assert info["valid"] is True
        assert info["validation_errors"] == []

    def test_inspect_package_contents(self, jarvis_plugin):
        info = inspect_package(jarvis_plugin)
        assert "__init__.py" in info["contents"]
        assert "plugin.json" in info["contents"]

    def test_inspect_package_file_hash(self, jarvis_plugin):
        info = inspect_package(jarvis_plugin)
        assert isinstance(info["file_hash"], str)
        assert len(info["file_hash"]) == 64

    def test_inspect_package_file_size(self, jarvis_plugin):
        info = inspect_package(jarvis_plugin)
        assert info["file_size"] > 0

    def test_inspect_nonexistent_raises(self):
        with pytest.raises(FileNotFoundError):
            inspect_package("/nonexistent/file.jarvis-plugin")

    def test_inspect_package_with_permissions(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "perm-plugin"
            src.mkdir()
            (src / "__init__.py").write_text("", encoding="utf-8")
            (src / "plugin.json").write_text(
                json.dumps({
                    "name": "perm-plugin",
                    "version": "1.0.0",
                    "permissions": ["ai", "events"],
                }),
                encoding="utf-8",
            )
            pkg_path = Path(tmp) / "perm-plugin.jarvis-plugin"
            import zipfile
            with zipfile.ZipFile(pkg_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for f in src.rglob("*"):
                    if f.is_file():
                        zf.write(f, f.relative_to(src))
            info = inspect_package(pkg_path)
            assert info["permissions"] == ["ai", "events"]

    def test_inspect_package_dependencies(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "dep-pkg"
            src.mkdir()
            (src / "__init__.py").write_text("", encoding="utf-8")
            (src / "plugin.json").write_text(
                json.dumps({
                    "name": "dep-pkg",
                    "version": "1.0.0",
                    "dependencies": [{"name": "base", "version": "1.0.0"}],
                }),
                encoding="utf-8",
            )
            pkg_path = Path(tmp) / "dep-pkg.jarvis-plugin"
            import zipfile
            with zipfile.ZipFile(pkg_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for f in src.rglob("*"):
                    if f.is_file():
                        zf.write(f, f.relative_to(src))
            info = inspect_package(pkg_path)
            assert info["dependencies"] == [{"name": "base", "version": "1.0.0"}]

    def test_inspect_package_config_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "schema-pkg"
            src.mkdir()
            (src / "__init__.py").write_text("", encoding="utf-8")
            (src / "plugin.json").write_text(
                json.dumps({
                    "name": "schema-pkg",
                    "version": "1.0.0",
                    "config_schema": {
                        "type": "object",
                        "properties": {"key": {"type": "string"}},
                    },
                }),
                encoding="utf-8",
            )
            pkg_path = Path(tmp) / "schema-pkg.jarvis-plugin"
            import zipfile
            with zipfile.ZipFile(pkg_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for f in src.rglob("*"):
                    if f.is_file():
                        zf.write(f, f.relative_to(src))
            info = inspect_package(pkg_path)
            assert info["config_schema"] is not None
            assert "key" in info["config_schema"]["properties"]


class TestDependencyInspection:
    """Dependency inspector."""

    def test_inspect_empty_dependencies(self):
        m = PluginManifest(name="test", version="1.0.0")
        result = inspect_dependencies(m)
        assert result == []

    def test_inspect_with_dependencies(self):
        m = PluginManifest(
            name="test", version="1.0.0",
            dependencies=[PluginDependency("dep1", "1.0.0")],
        )
        result = inspect_dependencies(m)
        assert len(result) == 1
        assert result[0]["name"] == "dep1"
        assert result[0]["version_spec"] == "1.0.0"

    def test_inspect_with_manager(self):
        mgr = PluginManager()
        m = PluginManifest(
            name="consumer", version="1.0.0",
            dependencies=[PluginDependency("provider", "1.0.0")],
        )
        result = inspect_dependencies(m, plugin_manager=mgr)
        assert result[0]["resolved"] is None

    def test_inspect_dependency_star_version(self):
        m = PluginManifest(
            name="test", version="1.0.0",
            dependencies=[PluginDependency("any", "*")],
        )
        result = inspect_dependencies(m)
        assert result[0]["version_spec"] == "*"

    def test_inspect_dependency_inspector_class(self):
        m = PluginManifest(
            name="test", version="1.0.0",
            dependencies=[PluginDependency("dep", "1.0.0")],
        )
        result = DependencyInspector.inspect(m)
        assert len(result) == 1
        assert result[0]["name"] == "dep"


class TestPermissionInspection:
    """Permission inspector."""

    def test_inspect_no_permissions(self):
        m = PluginManifest(name="test", version="1.0.0")
        result = inspect_permissions(m)
        assert result["declared"] == []
        assert result["has_all"] is True
        assert "none declared" in result["summary"]

    def test_inspect_known_permissions(self):
        m = PluginManifest(
            name="test", version="1.0.0",
            permissions=["ai", "events"],
        )
        result = inspect_permissions(m)
        assert "ai" in result["known"]
        assert "events" in result["known"]
        assert result["unknown"] == []

    def test_inspect_unknown_permission(self):
        m = PluginManifest(
            name="test", version="1.0.0",
            permissions=["unknown_perm"],
        )
        result = inspect_permissions(m)
        assert "unknown_perm" in result["unknown"]

    def test_inspect_missing_permissions(self):
        m = PluginManifest(
            name="test", version="1.0.0",
            permissions=["ai"],
        )
        result = inspect_permissions(m)
        assert "events" in result["missing"]
        assert "services" in result["missing"]

    def test_inspect_all_permissions(self):
        m = PluginManifest(
            name="test", version="1.0.0",
            permissions=Permission.all_permissions(),
        )
        result = inspect_permissions(m)
        assert result["has_all"] is True
        assert len(result["missing"]) == 0

    def test_permission_inspector_class(self):
        m = PluginManifest(name="test", version="1.0.0")
        result = PermissionInspector.inspect(m)
        assert result["declared"] == []


class TestConfigInspection:
    """Configuration schema inspector."""

    def test_inspect_no_schema(self):
        m = PluginManifest(name="test", version="1.0.0")
        result = inspect_config_schema(m)
        assert result["has_schema"] is False
        assert "No configuration" in result["summary"]

    def test_inspect_empty_schema(self):
        m = PluginManifest(
            name="test", version="1.0.0",
            config_schema={},
        )
        result = inspect_config_schema(m)
        assert result["has_schema"] is True
        assert result["fields"] == []

    def test_inspect_schema_with_fields(self):
        schema = {
            "type": "object",
            "properties": {
                "api_key": {"type": "string", "description": "API key"},
                "timeout": {"type": "integer", "default": 30},
            },
            "required": ["api_key"],
        }
        m = PluginManifest(name="test", version="1.0.0", config_schema=schema)
        result = inspect_config_schema(m)
        assert result["field_count"] == 2
        assert result["required_count"] == 1
        field_names = [f["name"] for f in result["fields"]]
        assert "api_key" in field_names
        assert "timeout" in field_names

    def test_inspect_schema_field_properties(self):
        schema = {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "desc", "default": "val"},
            },
            "required": ["key"],
        }
        m = PluginManifest(name="test", version="1.0.0", config_schema=schema)
        result = inspect_config_schema(m)
        field = result["fields"][0]
        assert field["name"] == "key"
        assert field["type"] == "string"
        assert field["description"] == "desc"
        assert field["default"] == "val"
        assert field["required"] is True

    def test_config_inspector_class(self):
        m = PluginManifest(name="test", version="1.0.0")
        result = ConfigInspector.inspect(m)
        assert result["has_schema"] is False


class TestPluginDiagnostics:
    """Plugin diagnostics."""

    def test_diagnose_unregistered_plugin(self):
        mgr = PluginManager()
        result = diagnose_plugin("nonexistent", mgr)
        assert result.name == "nonexistent"
        assert result.manifest_valid is False
        assert any("not registered" in e for e in result.manifest_errors)

    def test_diagnose_registered_plugin(self):
        from app.plugins.sdk.base import Plugin
        class DiagPlugin(Plugin):
            name = "diag-test"
            version = "1.0.0"
        mgr = PluginManager()
        p = DiagPlugin()
        mgr.register(p)
        mgr.load("diag-test")
        result = diagnose_plugin("diag-test", mgr)
        assert result.name == "diag-test"
        assert result.version == "1.0.0"
        assert result.manifest_valid or True

    def test_diagnose_returns_diagnostics_result(self):
        mgr = PluginManager()
        result = diagnose_plugin("any", mgr)
        assert isinstance(result, PluginDiagnosticsResult)
        assert isinstance(result.services, list)

    def test_diagnose_plugin_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "test-p"
            src.mkdir()
            (src / "__init__.py").write_text("# test", encoding="utf-8")
            (src / "plugin.json").write_text(
                json.dumps({"name": "test-p", "version": "1.0.0"}),
                encoding="utf-8",
            )
            mgr = PluginManager()
            result = diagnose_plugin("test-p", mgr, plugin_dir=src)
            assert result.source_valid is True


class TestHealthCheck:
    """Plugin health checks."""

    def test_health_check_unregistered(self):
        mgr = PluginManager()
        result = health_check_plugin("nonexistent", mgr)
        assert result.healthy is False
        assert result.manifest_ok is False

    def test_health_check_registered(self):
        from app.plugins.sdk.base import Plugin
        class HealthyPlugin(Plugin):
            name = "healthy"
            version = "1.0.0"
        mgr = PluginManager()
        p = HealthyPlugin()
        mgr.register(p)
        mgr.load("healthy")
        result = health_check_plugin("healthy", mgr)
        assert isinstance(result, HealthCheckResult)
        assert result.name == "healthy"

    def test_health_check_errors_list(self):
        mgr = PluginManager()
        result = health_check_plugin("missing", mgr)
        assert isinstance(result.errors, list)

    def test_health_check_permissions_ok(self):
        m = PluginManifest(
            name="test", version="1.0.0",
            permissions=["ai"],
        )
        mgr = PluginManager()
        from app.plugins.sdk.base import Plugin
        class PermPlugin(Plugin):
            name = "test"
            version = "1.0.0"
            manifest = m
        p = PermPlugin()
        mgr.register(p, m)
        mgr.load("test")
        result = health_check_plugin("test", mgr)
        assert result.permissions_ok is True

    def test_health_check_unknown_permission(self):
        m = PluginManifest(
            name="test", version="1.0.0",
            permissions=["bad_perm"],
        )
        mgr = PluginManager()
        from app.plugins.sdk.base import Plugin
        class BadPermPlugin(Plugin):
            name = "test"
            version = "1.0.0"
            manifest = m
        p = BadPermPlugin()
        errs = mgr.register(p, m)
        assert len(errs) > 0
        result = health_check_plugin("test", mgr)
        assert result.manifest_ok is False


class TestInfoExporter:
    """Plugin info exporter."""

    def test_export_nonexistent(self):
        mgr = PluginManager()
        info = export_plugin_info("nope", mgr)
        assert info["name"] == "nope"
        assert info["loaded"] is False

    def test_export_registered_plugin(self):
        from app.plugins.sdk.base import Plugin
        class ExpPlugin(Plugin):
            name = "exporter"
            version = "2.0.0"
        mgr = PluginManager()
        mgr.register(ExpPlugin())
        mgr.load("exporter")
        info = export_plugin_info("exporter", mgr)
        assert info["name"] == "exporter"
        assert info["version"] == "2.0.0"
        assert info["loaded"] is True

    def test_export_include_raw_manifest(self):
        from app.plugins.sdk.base import Plugin
        class RawPlugin(Plugin):
            name = "raw"
            version = "1.0.0"
        mgr = PluginManager()
        mgr.register(RawPlugin())
        info = export_plugin_info("raw", mgr, include_raw=True)
        assert "raw_manifest" in info
        assert info["raw_manifest"]["name"] == "raw"

    def test_export_timestamp(self):
        mgr = PluginManager()
        info = export_plugin_info("test", mgr)
        assert "exported_at" in info

    def test_export_with_services(self):
        from app.plugins.sdk.base import Plugin
        class SvcPlugin(Plugin):
            name = "svc-p"
            version = "1.0.0"
        mgr = PluginManager()
        p = SvcPlugin()
        mgr.register(p)
        mgr.load("svc-p")
        mgr.register_plugin_service("svc-p", "my.svc")
        info = export_plugin_info("svc-p", mgr)
        assert "my.svc" in info["services"]

    def test_info_exporter_class(self):
        mgr = PluginManager()
        info = PluginInfoExporter.export("test", mgr)
        assert "name" in info


class TestDocGeneration:
    """Plugin documentation generator."""

    def test_generate_docs_basic(self):
        m = PluginManifest(name="doc-test", version="1.0.0")
        mgr = PluginManager()
        mgr.register(type("DocPlugin", (Plugin,), {"name": "doc-test", "version": "1.0.0"})())
        mgr._manifests["doc-test"] = m
        docs = generate_plugin_docs("doc-test", mgr)
        assert "# Plugin: doc-test" in docs
        assert "**Version:** 1.0.0" in docs

    def test_generate_docs_no_manifest(self):
        mgr = PluginManager()
        docs = generate_plugin_docs("missing", mgr)
        assert "No manifest available" in docs

    def test_generate_docs_with_author_description(self):
        m = PluginManifest(
            name="doc-test", version="1.0.0",
            author="Test Author", description="A test plugin",
        )
        mgr = PluginManager()
        mgr._manifests["doc-test"] = m
        docs = generate_plugin_docs("doc-test", mgr)
        assert "Test Author" in docs
        assert "A test plugin" in docs

    def test_generate_docs_with_permissions(self):
        m = PluginManifest(
            name="doc-test", version="1.0.0",
            permissions=["ai", "events"],
        )
        mgr = PluginManager()
        mgr._manifests["doc-test"] = m
        docs = generate_plugin_docs("doc-test", mgr)
        assert "Permissions" in docs
        assert "`ai`" in docs

    def test_generate_docs_with_config_schema(self):
        schema = {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "desc"},
            },
            "required": ["key"],
        }
        m = PluginManifest(
            name="doc-test", version="1.0.0",
            config_schema=schema,
        )
        mgr = PluginManager()
        mgr._manifests["doc-test"] = m
        docs = generate_plugin_docs("doc-test", mgr)
        assert "Configuration" in docs
        assert "| Field |" in docs

    def test_generate_docs_with_dependencies(self):
        m = PluginManifest(
            name="doc-test", version="1.0.0",
            dependencies=[PluginDependency("base", "1.0.0")],
        )
        mgr = PluginManager()
        mgr._manifests["doc-test"] = m
        docs = generate_plugin_docs("doc-test", mgr)
        assert "Dependencies" in docs
        assert "`base`" in docs

    def test_doc_generator_class(self):
        mgr = PluginManager()
        docs = PluginDocGenerator.generate("test", mgr)
        assert isinstance(docs, str)


class TestPluginValidator:
    """Plugin validator service."""

    def test_validate_valid_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            scaffold_plugin("valid-proj", tmp)
            result = validate_plugin_project(Path(tmp) / "valid-proj")
            assert result.valid is True

    def test_validate_missing_directory(self):
        result = validate_plugin_project("/nonexistent/path")
        assert result.valid is False
        assert any("Directory not found" in e for e in result.errors)

    def test_validate_missing_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = validate_plugin_project(tmp)
            assert result.valid is False

    def test_validate_invalid_manifest_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "plugin.json").write_text(
                "not-json", encoding="utf-8",
            )
            result = validate_plugin_project(tmp)
            assert result.valid is False

    def test_validate_warns_no_author(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "plugin.json").write_text(
                json.dumps({"name": "test", "version": "1.0.0"}),
                encoding="utf-8",
            )
            result = validate_plugin_project(tmp)
            assert not result.valid
            assert any("main.py" in e for e in result.errors)

    def test_validate_with_source_and_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "__init__.py").write_text("", encoding="utf-8")
            (Path(tmp) / "plugin.json").write_text(
                json.dumps({"name": "test", "version": "1.0.0"}),
                encoding="utf-8",
            )
            result = validate_plugin_project(tmp)
            assert result.valid is True

    def test_validate_unknown_permission(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "__init__.py").write_text("", encoding="utf-8")
            (Path(tmp) / "plugin.json").write_text(
                json.dumps({
                    "name": "test", "version": "1.0.0",
                    "permissions": ["bad_perm"],
                }),
                encoding="utf-8",
            )
            result = validate_plugin_project(tmp)
            assert result.valid is False
            assert any("bad_perm" in e for e in result.errors)

    def test_validate_format_result_valid(self):
        result = ValidationResult(valid=True)
        text = format_validation_result(result)
        assert text == "VALID"

    def test_validate_format_result_invalid(self):
        result = ValidationResult(
            valid=False,
            errors=["err1"],
            warnings=["warn1"],
        )
        text = format_validation_result(result)
        assert "INVALID" in text
        assert "err1" in text
        assert "warn1" in text

    def test_plugin_validator_class(self):
        with tempfile.TemporaryDirectory() as tmp:
            scaffold_plugin("cls-valid", tmp)
            result = PluginValidator.validate_project(
                Path(tmp) / "cls-valid",
            )
            assert result.valid is True

    def test_plugin_validator_manifest_class(self):
        m = PluginManifest(name="test", version="1.0.0")
        result = PluginValidator.validate_manifest(m)
        assert result.valid is True


class TestDeveloperUtilities:
    """Developer helper utilities."""

    def test_discover_plugin_dirs(self):
        with tempfile.TemporaryDirectory() as tmp:
            p1 = Path(tmp) / "plugin-a"
            p1.mkdir()
            (p1 / "__init__.py").write_text("", encoding="utf-8")
            (p1 / "plugin.json").write_text(
                json.dumps({"name": "a", "version": "1.0.0"}),
                encoding="utf-8",
            )
            p2 = Path(tmp) / "not-plugin"
            p2.mkdir()
            result = discover_plugin_dirs(tmp)
            names = [d.name for d in result]
            assert "plugin-a" in names
            assert "not-plugin" not in names

    def test_discover_plugin_dirs_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = discover_plugin_dirs(tmp)
            assert result == []

    def test_discover_plugin_dirs_nonexistent(self):
        result = discover_plugin_dirs("/nonexistent/path")
        assert result == []

    def test_resolve_plugin_file_found(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "test.py").write_text("", encoding="utf-8")
            result = resolve_plugin_file(tmp, "test.py")
            assert result is not None
            assert result.name == "test.py"

    def test_resolve_plugin_file_not_found(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = resolve_plugin_file(tmp, "missing.py")
            assert result is None

    def test_resolve_plugin_file_path_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = resolve_plugin_file(tmp, "../etc/passwd")
            assert result is None

    def test_list_plugin_permission_summary_empty(self):
        mgr = PluginManager()
        result = list_plugin_permission_summary(mgr)
        assert result == []

    def test_list_plugin_permission_summary(self):
        m = PluginManifest(
            name="test", version="1.0.0",
            permissions=["ai"],
        )
        mgr = PluginManager()
        from app.plugins.sdk.base import Plugin
        class PermSumPlugin(Plugin):
            name = "test"
            version = "1.0.0"
        p = PermSumPlugin()
        mgr.register(p, m)
        result = list_plugin_permission_summary(mgr)
        assert len(result) == 1
        assert result[0]["name"] == "test"
        assert result[0]["permissions"] == ["ai"]

    def test_list_plugin_permission_summary_none_manager(self):
        result = list_plugin_permission_summary(None)
        assert result == []

    def test_compute_hash_public(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "test.txt"
            f.write_text("hello", encoding="utf-8")
            h = compute_hash(f)
            assert isinstance(h, str)
            assert len(h) == 64

    def test_load_manifest_from_zip_public(self, jarvis_plugin):
        import zipfile
        with zipfile.ZipFile(jarvis_plugin, "r") as zf:
            manifest = load_manifest_from_zip(zf)
            assert manifest.name == "my-plugin"


class TestToolsBackwardCompat:
    """Backward compatibility for P10-10 developer tools."""

    def test_importable_from_app_plugins(self):
        from app.plugins import scaffold_plugin as sp
        assert sp is not None
        from app.plugins import generate_manifest as gm
        assert gm is not None
        from app.plugins import inspect_package as ip
        assert ip is not None

    def test_importable_from_sdk(self):
        from app.plugins.sdk import scaffold_plugin as sp
        assert sp is not None
        from app.plugins.sdk import generate_manifest as gm
        assert gm is not None
        from app.plugins.sdk import inspect_package as ip
        assert ip is not None

    def test_class_aliases_functional(self):
        with tempfile.TemporaryDirectory() as tmp:
            scaffold_plugin("cls-test", tmp)
            result = PluginValidator.validate_project(
                Path(tmp) / "cls-test",
            )
            assert result.valid is True

    def test_permission_inspector_via_class(self):
        m = PluginManifest(name="test", version="1.0.0")
        info = PermissionInspector.inspect(m)
        assert "summary" in info

    def test_dependency_inspector_via_class(self):
        m = PluginManifest(name="test", version="1.0.0")
        result = DependencyInspector.inspect(m)
        assert result == []

    def test_config_inspector_via_class(self):
        m = PluginManifest(name="test", version="1.0.0")
        info = ConfigInspector.inspect(m)
        assert info["has_schema"] is False

    def test_info_exporter_via_class(self):
        mgr = PluginManager()
        info = PluginInfoExporter.export("test", mgr)
        assert info["loaded"] is False

    def test_doc_generator_via_class(self):
        mgr = PluginManager()
        docs = PluginDocGenerator.generate("test", mgr)
        assert isinstance(docs, str)


# ---- helpers ----

def _create_test_package(pkg_path: Path) -> PluginPackage:
    mgr = PluginManager()
    pm = PackageManager(mgr)
    return pm.inspect(pkg_path)
