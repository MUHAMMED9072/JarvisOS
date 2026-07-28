"""Tests for SecurityEventBus and SecurityServiceRegistry integration."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.core.event_bus import EventBus
from app.core.registry import ServiceRegistry
from app.kernel.security.context import SecurityContext, SecurityContextVar
from app.kernel.security.integration import SecurityEventBus, SecurityServiceRegistry


class TestSecurityEventBus:
    @pytest.fixture
    def bus(self):
        return EventBus()

    @pytest.fixture
    def secure_bus(self, bus):
        return SecurityEventBus(bus)

    def test_subscribe_allowed_with_context(self, secure_bus):
        ctx = SecurityContext(granted={"events.subscribe", "events.publish"})
        SecurityContextVar.set(ctx)
        cb = MagicMock()
        secure_bus.subscribe("test.event", cb)
        secure_bus.publish("test.event")
        cb.assert_called_once()
        SecurityContextVar.reset()

    def test_subscribe_denied_without_permission(self, secure_bus):
        ctx = SecurityContext(granted={"memory.read"})
        SecurityContextVar.set(ctx)
        with pytest.raises(PermissionError):
            secure_bus.subscribe("test.event", lambda: None)
        SecurityContextVar.reset()

    def test_publish_allowed_with_context(self, secure_bus):
        ctx = SecurityContext(granted={"events.publish"})
        SecurityContextVar.set(ctx)
        secure_bus.publish("test.event")
        SecurityContextVar.reset()

    def test_publish_denied_without_permission(self, secure_bus):
        ctx = SecurityContext(granted={"memory.read"})
        SecurityContextVar.set(ctx)
        with pytest.raises(PermissionError):
            secure_bus.publish("test.event")
        SecurityContextVar.reset()

    def test_subscribe_wildcard_allowed(self, secure_bus):
        ctx = SecurityContext(granted={"events.subscribe", "events.publish"})
        SecurityContextVar.set(ctx)
        cb = MagicMock()
        secure_bus.subscribe_wildcard("ai.*", cb)
        secure_bus.publish("ai.request")
        cb.assert_called_once()
        SecurityContextVar.reset()

    def test_unsubscribe_allowed(self, secure_bus):
        ctx = SecurityContext(granted={"events.subscribe", "events.unsubscribe", "events.publish"})
        SecurityContextVar.set(ctx)
        cb = MagicMock()
        secure_bus.subscribe("test", cb)
        secure_bus.unsubscribe("test", cb)
        secure_bus.publish("test")
        cb.assert_not_called()
        SecurityContextVar.reset()

    def test_no_context_no_check(self, secure_bus):
        SecurityContextVar.reset()
        cb = MagicMock()
        secure_bus.subscribe("test", cb)
        secure_bus.publish("test")
        cb.assert_called_once()

    def test_listener_count(self, secure_bus):
        ctx = SecurityContext(granted={"events.subscribe"})
        SecurityContextVar.set(ctx)
        assert secure_bus.listener_count == 0
        secure_bus.subscribe("evt", lambda: None)
        assert secure_bus.listener_count == 1
        SecurityContextVar.reset()

    def test_pattern_count(self, secure_bus):
        ctx = SecurityContext(granted={"events.subscribe"})
        SecurityContextVar.set(ctx)
        assert secure_bus.pattern_count == 0
        secure_bus.subscribe("a", lambda: None)
        secure_bus.subscribe("b", lambda: None)
        assert secure_bus.pattern_count == 2
        SecurityContextVar.reset()

    def test_clear_requires_admin(self, secure_bus):
        ctx = SecurityContext(granted={"events.subscribe"})
        SecurityContextVar.set(ctx)
        with pytest.raises(PermissionError):
            secure_bus.clear()
        SecurityContextVar.reset()

    def test_clear_allowed_with_admin(self, secure_bus):
        ctx = SecurityContext(granted={"admin.agents.manage"})
        SecurityContextVar.set(ctx)
        secure_bus.clear()
        SecurityContextVar.reset()


class TestSecurityServiceRegistry:
    @pytest.fixture
    def registry(self):
        return ServiceRegistry()

    @pytest.fixture
    def secure_registry(self, registry):
        return SecurityServiceRegistry(registry)

    def test_register_allowed(self, secure_registry):
        ctx = SecurityContext(granted={"services.register"})
        SecurityContextVar.set(ctx)
        secure_registry.register("svc", "value")
        assert secure_registry.exists("svc") is True
        SecurityContextVar.reset()

    def test_register_denied(self, secure_registry):
        ctx = SecurityContext(granted={"memory.read"})
        SecurityContextVar.set(ctx)
        with pytest.raises(PermissionError):
            secure_registry.register("svc", "value")
        SecurityContextVar.reset()

    def test_get_allowed(self, secure_registry):
        secure_registry._registry.register("svc", "value")
        ctx = SecurityContext(granted={"services.get"})
        SecurityContextVar.set(ctx)
        assert secure_registry.get("svc") == "value"
        SecurityContextVar.reset()

    def test_get_denied(self, secure_registry):
        secure_registry._registry.register("svc", "value")
        ctx = SecurityContext(granted={"memory.read"})
        SecurityContextVar.set(ctx)
        with pytest.raises(PermissionError):
            secure_registry.get("svc")
        SecurityContextVar.reset()

    def test_exists_no_check(self, secure_registry):
        secure_registry._registry.register("svc", "value")
        assert secure_registry.exists("svc") is True
        assert secure_registry.exists("missing") is False

    def test_get_optional_no_check(self, secure_registry):
        secure_registry._registry.register("svc", "value")
        assert secure_registry.get_optional("svc") == "value"

    def test_list_services_allowed(self, secure_registry):
        secure_registry._registry.register("a", 1)
        ctx = SecurityContext(granted={"services.list"})
        SecurityContextVar.set(ctx)
        assert secure_registry.list_services() == ["a"]
        SecurityContextVar.reset()

    def test_list_services_denied(self, secure_registry):
        ctx = SecurityContext(granted={"memory.read"})
        SecurityContextVar.set(ctx)
        with pytest.raises(PermissionError):
            secure_registry.list_services()
        SecurityContextVar.reset()

    def test_remove_requires_admin(self, secure_registry):
        secure_registry._registry.register("svc", "value")
        ctx = SecurityContext(granted={"services.register"})
        SecurityContextVar.set(ctx)
        with pytest.raises(PermissionError):
            secure_registry.remove("svc")
        SecurityContextVar.reset()

    def test_remove_allowed_with_admin(self, secure_registry):
        secure_registry._registry.register("svc", "value")
        ctx = SecurityContext(granted={"admin.agents.manage"})
        SecurityContextVar.set(ctx)
        secure_registry.remove("svc")
        assert secure_registry.exists("svc") is False
        SecurityContextVar.reset()

    def test_start_all_requires_admin(self, secure_registry):
        ctx = SecurityContext(granted={"services.register"})
        SecurityContextVar.set(ctx)
        with pytest.raises(PermissionError):
            secure_registry.start_all()
        SecurityContextVar.reset()

    def test_shutdown_all_requires_admin(self, secure_registry):
        ctx = SecurityContext(granted={"services.register"})
        SecurityContextVar.set(ctx)
        with pytest.raises(PermissionError):
            secure_registry.shutdown_all()
        SecurityContextVar.reset()

    def test_no_context_no_check(self, secure_registry):
        SecurityContextVar.reset()
        secure_registry.register("svc", "value")
        assert secure_registry.get("svc") == "value"
