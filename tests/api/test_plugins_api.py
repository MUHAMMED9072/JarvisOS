"""Tests for the Plugin REST API (P11-04)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.schemas import (
    PluginActionResponse,
    PluginDiscoverResponse,
    PluginInfo,
    PluginListResponse,
    PluginPackageListResponse,
    PluginPermissionListResponse,
    PluginServiceListResponse,
)
from app.api.server import create_app
from app.core.registry import ServiceRegistry
from app.plugins.sdk.base import Plugin
from app.plugins.sdk.models import PluginManifest


# ==========================================================================
# Test plugins
# ==========================================================================


class _TestPlugin(Plugin):
    name = "test_plugin"
    version = "1.0.0"


class _AnotherPlugin(Plugin):
    name = "another_plugin"
    version = "2.0.0"


class _BetaPlugin(Plugin):
    name = "beta_plugin"
    version = "0.5.0"
    manifest = PluginManifest(
        name="beta_plugin",
        version="0.5.0",
        description="Beta plugin",
        author="Beta Dev",
        min_core_version="0.4.0",
        capabilities=["test", "beta"],
        permissions=["ai", "events"],
    )


# ==========================================================================
# Helpers
# ==========================================================================


def _make_app(
    registry: ServiceRegistry | None = None,
    plugin_manager=None,
) -> FastAPI:
    if registry is None:
        registry = ServiceRegistry()
    if plugin_manager is not None:
        registry.register("plugin_manager", plugin_manager)
    registry.register("dispatcher", MagicMock())
    registry.register("memory", MagicMock())
    registry.register("event_bus", MagicMock())
    return create_app(registry)


def _make_client(
    registry: ServiceRegistry | None = None,
    plugin_manager=None,
) -> TestClient:
    app = _make_app(registry, plugin_manager)
    return TestClient(app)


# ==========================================================================
# Route registration
# ==========================================================================


class TestPluginRouteRegistration:
    """Plugin routes appear in OpenAPI schema."""

    def test_plugin_routes_in_openapi(self):
        from app.plugins.sdk.manager import PluginManager

        pm = PluginManager()
        pm.register(_TestPlugin())
        client = _make_client(plugin_manager=pm)
        schema = client.get("/api/v1/openapi.json").json()
        paths = schema["paths"]
        assert "/api/v1/plugins" in paths
        assert "/api/v1/plugins/{name}" in paths
        assert "/api/v1/plugins/discover" in paths
        assert "/api/v1/plugins/load" in paths
        assert "/api/v1/plugins/unload" in paths
        assert "/api/v1/plugins/reload" in paths
        assert "/api/v1/plugins/enable" in paths
        assert "/api/v1/plugins/disable" in paths
        assert "/api/v1/plugins/services" in paths
        assert "/api/v1/plugins/permissions" in paths
        assert "/api/v1/plugins/packages" in paths


# ==========================================================================
# List plugins
# ==========================================================================


class TestListPlugins:
    """GET /api/v1/plugins"""

    def test_list_empty(self):
        from app.plugins.sdk.manager import PluginManager

        pm = PluginManager()
        client = _make_client(plugin_manager=pm)
        resp = client.get("/api/v1/plugins")
        assert resp.status_code == 200
        data = resp.json()
        assert data["plugins"] == []

    def test_list_plugins(self):
        from app.plugins.sdk.manager import PluginManager

        pm = PluginManager()
        pm.register(_TestPlugin())
        pm.register(_AnotherPlugin())
        client = _make_client(plugin_manager=pm)
        resp = client.get("/api/v1/plugins")
        assert resp.status_code == 200
        data = resp.json()
        names = [p["name"] for p in data["plugins"]]
        assert names == ["another_plugin", "test_plugin"]

    def test_list_with_manifest_info(self):
        from app.plugins.sdk.manager import PluginManager

        pm = PluginManager()
        pm.register(_BetaPlugin())
        pm.register(_TestPlugin())
        client = _make_client(plugin_manager=pm)
        resp = client.get("/api/v1/plugins")
        assert resp.status_code == 200
        data = resp.json()
        plugins = {p["name"]: p for p in data["plugins"]}
        beta = plugins["beta_plugin"]
        assert beta["description"] == "Beta plugin"
        assert beta["author"] == "Beta Dev"
        assert beta["capabilities"] == ["test", "beta"]
        assert beta["permissions"] == ["ai", "events"]
        assert not beta["enabled"]
        test_p = plugins["test_plugin"]
        assert test_p["description"] == ""
        assert test_p["errors"] == []


# ==========================================================================
# Get single plugin
# ==========================================================================


class TestGetPlugin:
    """GET /api/v1/plugins/{name}"""

    def test_get_existing(self):
        from app.plugins.sdk.manager import PluginManager

        pm = PluginManager()
        pm.register(_TestPlugin())
        client = _make_client(plugin_manager=pm)
        resp = client.get("/api/v1/plugins/test_plugin")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "test_plugin"
        assert data["version"] == "1.0.0"

    def test_get_nonexistent(self):
        from app.plugins.sdk.manager import PluginManager

        pm = PluginManager()
        client = _make_client(plugin_manager=pm)
        resp = client.get("/api/v1/plugins/nonexistent")
        assert resp.status_code == 404

    def test_get_returns_errors(self):
        from app.plugins.sdk.manager import PluginManager

        pm = PluginManager()
        pm.register(_TestPlugin())
        pm._errors["test_plugin"] = ["something went wrong"]
        client = _make_client(plugin_manager=pm)
        resp = client.get("/api/v1/plugins/test_plugin")
        assert resp.status_code == 200
        assert "something went wrong" in resp.json()["errors"]


# ==========================================================================
# Load / Unload
# ==========================================================================


class TestLoadPlugin:
    """POST /api/v1/plugins/load"""

    def test_load_existing_plugin(self):
        from app.plugins.sdk.manager import PluginManager

        pm = PluginManager()
        pm.register(_TestPlugin())
        client = _make_client(plugin_manager=pm)
        resp = client.post("/api/v1/plugins/load", json={"name": "test_plugin"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "test_plugin" in data["message"]

    def test_load_nonexistent_plugin(self):
        from app.plugins.sdk.manager import PluginManager

        pm = PluginManager()
        client = _make_client(plugin_manager=pm)
        resp = client.post("/api/v1/plugins/load", json={"name": "ghost"})
        assert resp.status_code == 404

    def test_load_empty_name(self):
        from app.plugins.sdk.manager import PluginManager

        pm = PluginManager()
        client = _make_client(plugin_manager=pm)
        resp = client.post("/api/v1/plugins/load", json={"name": ""})
        assert resp.status_code == 422


class TestUnloadPlugin:
    """POST /api/v1/plugins/unload"""

    def test_unload_existing(self):
        from app.plugins.sdk.manager import PluginManager

        pm = PluginManager()
        pm.register(_TestPlugin())
        pm.load("test_plugin")
        client = _make_client(plugin_manager=pm)
        resp = client.post("/api/v1/plugins/unload", json={"name": "test_plugin"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_unload_nonexistent(self):
        from app.plugins.sdk.manager import PluginManager

        pm = PluginManager()
        client = _make_client(plugin_manager=pm)
        resp = client.post("/api/v1/plugins/unload", json={"name": "ghost"})
        assert resp.status_code == 404


# ==========================================================================
# Enable / Disable
# ==========================================================================


class TestEnablePlugin:
    """POST /api/v1/plugins/enable"""

    def test_enable_existing(self):
        from app.plugins.sdk.manager import PluginManager

        pm = PluginManager()
        pm.register(_TestPlugin())
        pm.load("test_plugin")
        client = _make_client(plugin_manager=pm)
        resp = client.post("/api/v1/plugins/enable", json={"name": "test_plugin"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_enable_nonexistent(self):
        from app.plugins.sdk.manager import PluginManager

        pm = PluginManager()
        client = _make_client(plugin_manager=pm)
        resp = client.post("/api/v1/plugins/enable", json={"name": "ghost"})
        assert resp.status_code == 404


class TestDisablePlugin:
    """POST /api/v1/plugins/disable"""

    def test_disable_existing(self):
        from app.plugins.sdk.manager import PluginManager

        pm = PluginManager()
        pm.register(_TestPlugin())
        pm.load("test_plugin")
        pm.enable("test_plugin")
        client = _make_client(plugin_manager=pm)
        resp = client.post("/api/v1/plugins/disable", json={"name": "test_plugin"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_disable_nonexistent(self):
        from app.plugins.sdk.manager import PluginManager

        pm = PluginManager()
        client = _make_client(plugin_manager=pm)
        resp = client.post("/api/v1/plugins/disable", json={"name": "ghost"})
        assert resp.status_code == 404


# ==========================================================================
# Reload
# ==========================================================================


class TestReloadPlugin:
    """POST /api/v1/plugins/reload"""

    def test_reload_nonexistent(self):
        from app.plugins.sdk.manager import PluginManager

        pm = PluginManager()
        client = _make_client(plugin_manager=pm)
        resp = client.post("/api/v1/plugins/reload", json={"name": "ghost"})
        assert resp.status_code == 404


# ==========================================================================
# Services listing
# ==========================================================================


class TestPluginServices:
    """GET /api/v1/plugins/services"""

    def test_services_empty(self):
        from app.plugins.sdk.manager import PluginManager

        pm = PluginManager()
        client = _make_client(plugin_manager=pm)
        resp = client.get("/api/v1/plugins/services")
        assert resp.status_code == 200
        assert resp.json()["services"] == []

    def test_services_with_registrations(self):
        from app.plugins.sdk.manager import PluginManager

        pm = PluginManager()
        pm.register_plugin_service("plugin_a", "svc_1")
        pm.register_plugin_service("plugin_a", "svc_2")
        pm.register_plugin_service("plugin_b", "svc_3")
        client = _make_client(plugin_manager=pm)
        resp = client.get("/api/v1/plugins/services")
        assert resp.status_code == 200
        data = resp.json()
        services = {s["plugin"]: s["services"] for s in data["services"]}
        assert services["plugin_a"] == ["svc_1", "svc_2"]
        assert services["plugin_b"] == ["svc_3"]


# ==========================================================================
# Permissions listing
# ==========================================================================


class TestPermissions:
    """GET /api/v1/plugins/permissions"""

    def test_permissions_list(self):
        from app.plugins.sdk.manager import PluginManager

        pm = PluginManager()
        client = _make_client(plugin_manager=pm)
        resp = client.get("/api/v1/plugins/permissions")
        assert resp.status_code == 200
        data = resp.json()
        names = [p["name"] for p in data["permissions"]]
        assert "ai" in names
        assert "events" in names
        assert "services" in names
        assert "skills" in names
        assert "config" in names
        assert "memory" in names
        assert "filesystem" in names
        assert "network" in names
        assert len(data["permissions"]) == 8


# ==========================================================================
# Packages listing
# ==========================================================================


class TestPackages:
    """GET /api/v1/plugins/packages"""

    def test_packages_empty_no_package_manager(self):
        """When no package_manager is registered, returns empty list."""
        from app.plugins.sdk.manager import PluginManager

        pm = PluginManager()
        client = _make_client(plugin_manager=pm)
        resp = client.get("/api/v1/plugins/packages")
        assert resp.status_code == 200
        assert resp.json()["packages"] == []

    def test_packages_with_registered_manager(self):
        """When package_manager is registered, delegates to it."""
        from app.plugins.sdk.manager import PluginManager
        from app.plugins.sdk.package import PackageManager

        pm = PluginManager()
        pkg_mgr = MagicMock(spec=PackageManager)
        pkg_mgr.list_installed.return_value = []
        registry = ServiceRegistry()
        registry.register("plugin_manager", pm)
        registry.register("package_manager", pkg_mgr)
        registry.register("dispatcher", MagicMock())
        registry.register("memory", MagicMock())
        registry.register("event_bus", MagicMock())
        client = TestClient(create_app(registry))
        resp = client.get("/api/v1/plugins/packages")
        assert resp.status_code == 200
        assert resp.json()["packages"] == []

    def test_packages_with_installed(self):
        from app.plugins.sdk.manager import PluginManager
        from app.plugins.sdk.package import PackageManager, InstallMetadata

        pm = PluginManager()
        pkg_mgr = MagicMock(spec=PackageManager)
        pkg_mgr.list_installed.return_value = [
            InstallMetadata(
                name="test_pkg",
                version="1.0.0",
                installed_at="2026-01-01T00:00:00Z",
                package_hash="abc123",
                manifest={"name": "test_pkg", "version": "1.0.0"},
            ),
        ]
        registry = ServiceRegistry()
        registry.register("plugin_manager", pm)
        registry.register("package_manager", pkg_mgr)
        registry.register("dispatcher", MagicMock())
        registry.register("memory", MagicMock())
        registry.register("event_bus", MagicMock())
        client = TestClient(create_app(registry))
        resp = client.get("/api/v1/plugins/packages")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["packages"]) == 1
        pkg = data["packages"][0]
        assert pkg["name"] == "test_pkg"
        assert pkg["version"] == "1.0.0"
        assert pkg["package_hash"] == "abc123"


# ==========================================================================
# Error handling
# ==========================================================================


class TestPluginErrorHandling:
    """Verify proper error status codes."""

    def test_service_unavailable(self):
        """Without plugin_manager registered, returns 503."""
        registry = ServiceRegistry()
        registry.register("dispatcher", MagicMock())
        registry.register("memory", MagicMock())
        registry.register("event_bus", MagicMock())
        client = TestClient(create_app(registry))
        resp = client.get("/api/v1/plugins")
        assert resp.status_code == 503

    def test_get_nonexistent_returns_404(self):
        from app.plugins.sdk.manager import PluginManager

        pm = PluginManager()
        client = _make_client(plugin_manager=pm)
        resp = client.get("/api/v1/plugins/nope")
        assert resp.status_code == 404


# ==========================================================================
# Discover endpoint (basic smoke test)
# ==========================================================================


class TestDiscover:
    """POST /api/v1/plugins/discover"""

    def test_discover_returns_ok(self):
        from app.plugins.sdk.manager import PluginManager

        pm = PluginManager()
        client = _make_client(plugin_manager=pm)
        resp = client.post("/api/v1/plugins/discover")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert isinstance(data["count"], int)
        assert isinstance(data["plugins"], list)


# ==========================================================================
# Response model shapes
# ==========================================================================


class TestResponseShapes:
    """Verify response payloads match expected Pydantic models."""

    def test_plugin_list_response_shape(self):
        from app.plugins.sdk.manager import PluginManager

        pm = PluginManager()
        pm.register(_BetaPlugin())
        client = _make_client(plugin_manager=pm)
        resp = client.get("/api/v1/plugins")
        data = resp.json()
        p = data["plugins"][0]
        for field in (
            "name", "version", "enabled", "description",
            "author", "min_core_version", "capabilities",
            "permissions", "services", "errors",
        ):
            assert field in p, f"Missing field: {field}"

    def test_action_response_shape(self):
        from app.plugins.sdk.manager import PluginManager

        pm = PluginManager()
        pm.register(_TestPlugin())
        client = _make_client(plugin_manager=pm)
        resp = client.post("/api/v1/plugins/load", json={"name": "test_plugin"})
        data = resp.json()
        for field in ("status", "message", "name"):
            assert field in data, f"Missing field: {field}"
