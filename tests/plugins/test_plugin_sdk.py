"""Tests for the Plugin SDK framework."""

from __future__ import annotations

import tempfile
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
    Plugin,
    PluginConfig,
    PluginContext,
    PluginDependency,
    PluginManager,
    PluginManifest,
    check_version_compatibility,
    validate_manifest,
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
