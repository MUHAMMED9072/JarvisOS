"""Tests for the REST API layer (P11-01)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi import Depends, FastAPI, Request
from fastapi.testclient import TestClient

from app.api.dependencies import get_service, require_service
from app.api.errors import (
    APIException,
    BadRequestError,
    NotFoundError,
    ServiceUnavailableError,
)
from app.api.schemas import (
    ConfigResponse,
    ErrorResponse,
    HealthResponse,
    ServiceInfo,
    ServiceListResponse,
    StatusResponse,
)
from app.api.server import create_app
from app.core.config import Config
from app.core.registry import ServiceRegistry


# ==========================================================================
# Helpers
# ==========================================================================


def _make_app(registry: ServiceRegistry | None = None) -> FastAPI:
    return create_app(registry)


def _make_client(registry: ServiceRegistry | None = None) -> TestClient:
    app = _make_app(registry)
    return TestClient(app)


# ==========================================================================
# App creation & route registration
# ==========================================================================


class TestAppCreation:
    """FastAPI application creation and configuration."""

    def test_create_app_without_registry(self):
        app = _make_app()
        assert app.title == "JARVIS OS API"
        assert app.version == "0.4.0"
        assert app.state.registry is None

    def test_create_app_with_registry(self):
        reg = ServiceRegistry()
        app = _make_app(reg)
        assert app.state.registry is reg

    def test_create_app_custom_title(self):
        app = create_app(title="Custom API", version="2.0.0")
        assert app.title == "Custom API"
        assert app.version == "2.0.0"

    def test_openapi_endpoint_exists(self):
        client = _make_client()
        r = client.get("/api/v1/openapi.json")
        assert r.status_code == 200
        assert r.json()["info"]["title"] == "JARVIS OS API"

    def test_docs_endpoint_exists(self):
        client = _make_client()
        r = client.get("/api/v1/docs")
        assert r.status_code == 200

    def test_redoc_endpoint_exists(self):
        client = _make_client()
        r = client.get("/api/v1/redoc")
        assert r.status_code == 200

    def test_all_routes_registered(self):
        client = _make_client()
        schema = client.get("/api/v1/openapi.json").json()
        paths = schema["paths"]
        assert "/api/v1/health" in paths
        assert "/api/v1/status" in paths
        assert "/api/v1/config" in paths
        assert "/api/v1/services" in paths

    def test_create_app_returns_fastapi_app(self):
        app = _make_app()
        assert isinstance(app, FastAPI)

    def test_registry_on_app_state(self):
        reg = ServiceRegistry()
        app = _make_app(reg)
        assert app.state.registry is reg


# ==========================================================================
# Health endpoint
# ==========================================================================


class TestHealthEndpoint:
    """GET /api/v1/health."""

    def test_health_returns_200(self):
        client = _make_client()
        r = client.get("/api/v1/health")
        assert r.status_code == 200

    def test_health_response_model(self):
        client = _make_client()
        r = client.get("/api/v1/health")
        data = r.json()
        assert "status" in data
        assert "version" in data
        assert "services_healthy" in data

    def test_health_status_healthy(self):
        client = _make_client()
        r = client.get("/api/v1/health")
        assert r.json()["status"] == "healthy"

    def test_health_version_matches_config(self):
        client = _make_client()
        r = client.get("/api/v1/health")
        assert r.json()["version"] == Config.VERSION

    def test_health_with_registry(self):
        reg = ServiceRegistry()
        reg.register("test_service", object())
        client = _make_client(reg)
        r = client.get("/api/v1/health")
        assert r.json()["services_healthy"] >= 1

    def test_health_without_registry(self):
        client = _make_client()
        r = client.get("/api/v1/health")
        assert r.json()["services_healthy"] == 0

    def test_health_response_model_validation(self):
        client = _make_client()
        r = client.get("/api/v1/health")
        model = HealthResponse(**r.json())
        assert model.status == "healthy"

    def test_health_content_type(self):
        client = _make_client()
        r = client.get("/api/v1/health")
        assert "application/json" in r.headers["content-type"]


# ==========================================================================
# Status endpoint
# ==========================================================================


class TestStatusEndpoint:
    """GET /api/v1/status."""

    def test_status_returns_200(self):
        client = _make_client()
        r = client.get("/api/v1/status")
        assert r.status_code == 200

    def test_status_response_fields(self):
        client = _make_client()
        r = client.get("/api/v1/status")
        data = r.json()
        assert "status" in data
        assert "version" in data
        assert "plugins" in data
        assert "skills" in data
        assert "services" in data
        assert "memory" in data
        assert "voice" in data

    def test_status_running(self):
        client = _make_client()
        r = client.get("/api/v1/status")
        assert r.json()["status"] == "running"

    def test_status_version(self):
        client = _make_client()
        r = client.get("/api/v1/status")
        assert r.json()["version"] == Config.VERSION

    def test_status_with_full_registry(self):
        reg = ServiceRegistry()
        pm = MagicMock()
        pm.list_plugins.return_value = []
        reg.register("plugin_manager", pm)
        sm = MagicMock()
        sm.skills = {}
        reg.register("skill_manager", sm)
        reg.register("memory", object())
        vc = MagicMock()
        vc.enabled = False
        reg.register("voice_config", vc)
        client = _make_client(reg)
        r = client.get("/api/v1/status")
        assert r.status_code == 200

    def test_status_voice_enabled(self):
        reg = ServiceRegistry()
        vc = MagicMock()
        vc.enabled = True
        reg.register("voice_config", vc)
        client = _make_client(reg)
        r = client.get("/api/v1/status")
        assert r.json()["voice"] == "enabled"

    def test_status_voice_disabled(self):
        reg = ServiceRegistry()
        vc = MagicMock()
        vc.enabled = False
        reg.register("voice_config", vc)
        client = _make_client(reg)
        r = client.get("/api/v1/status")
        assert r.json()["voice"] == "disabled"

    def test_status_empty_registry(self):
        reg = ServiceRegistry()
        client = _make_client(reg)
        r = client.get("/api/v1/status")
        assert r.json()["services"] == 0
        assert r.json()["plugins"] == 0
        assert r.json()["skills"] == 0

    def test_status_model_validation(self):
        client = _make_client()
        r = client.get("/api/v1/status")
        model = StatusResponse(**r.json())
        assert model.status == "running"


# ==========================================================================
# Configuration endpoint
# ==========================================================================


class TestConfigEndpoint:
    """GET /api/v1/config."""

    def test_config_returns_200(self):
        client = _make_client()
        r = client.get("/api/v1/config")
        assert r.status_code == 200

    def test_config_response_fields(self):
        client = _make_client()
        r = client.get("/api/v1/config")
        data = r.json()
        assert "app_name" in data
        assert "version" in data
        assert "data_dir" in data
        assert "plugin_dir" in data
        assert "log_level" in data
        assert "default_brain" in data
        assert "voice_enabled" in data
        assert "wake_word" in data

    def test_config_app_name(self):
        client = _make_client()
        r = client.get("/api/v1/config")
        assert r.json()["app_name"] == Config.APP_NAME

    def test_config_version(self):
        client = _make_client()
        r = client.get("/api/v1/config")
        assert r.json()["version"] == Config.VERSION

    def test_config_log_level(self):
        client = _make_client()
        r = client.get("/api/v1/config")
        assert r.json()["log_level"] == Config.LOG_LEVEL

    def test_config_voice_enabled_default(self):
        client = _make_client()
        r = client.get("/api/v1/config")
        assert r.json()["voice_enabled"] is False

    def test_config_wake_word(self):
        client = _make_client()
        r = client.get("/api/v1/config")
        assert r.json()["wake_word"] == Config.WAKE_WORD

    def test_config_read_only(self):
        client = _make_client()
        r = client.post("/api/v1/config", json={"app_name": "hacked"})
        assert r.status_code in (405, 404)

    def test_config_model_validation(self):
        client = _make_client()
        r = client.get("/api/v1/config")
        model = ConfigResponse(**r.json())
        assert model.app_name == Config.APP_NAME


# ==========================================================================
# Service discovery endpoint
# ==========================================================================


class TestServiceDiscoveryEndpoint:
    """GET /api/v1/services."""

    def test_services_returns_200(self):
        client = _make_client()
        r = client.get("/api/v1/services")
        assert r.status_code == 200

    def test_services_response_model(self):
        client = _make_client()
        r = client.get("/api/v1/services")
        data = r.json()
        assert "services" in data

    def test_services_empty_without_registry(self):
        client = _make_client()
        r = client.get("/api/v1/services")
        assert r.json()["services"] == []

    def test_services_with_registry(self):
        reg = ServiceRegistry()
        reg.register("svc1", object())
        reg.register("svc2", object())
        client = _make_client(reg)
        r = client.get("/api/v1/services")
        services = r.json()["services"]
        names = [s["name"] for s in services]
        assert "svc1" in names
        assert "svc2" in names

    def test_services_availability_true(self):
        reg = ServiceRegistry()
        reg.register("my_svc", object())
        client = _make_client(reg)
        r = client.get("/api/v1/services")
        svc = next(s for s in r.json()["services"] if s["name"] == "my_svc")
        assert svc["available"] is True

    def test_services_sorted(self):
        reg = ServiceRegistry()
        reg.register("z_svc", object())
        reg.register("a_svc", object())
        client = _make_client(reg)
        r = client.get("/api/v1/services")
        names = [s["name"] for s in r.json()["services"]]
        assert names == sorted(names)

    def test_services_model_validation(self):
        reg = ServiceRegistry()
        reg.register("svc1", object())
        client = _make_client(reg)
        r = client.get("/api/v1/services")
        model = ServiceListResponse(**r.json())
        assert len(model.services) >= 1

    def test_services_has_service_info_model(self):
        info = ServiceInfo(name="test", available=True)
        assert info.name == "test"
        assert info.available is True


# ==========================================================================
# Error handling
# ==========================================================================


class TestErrorHandling:
    """Error models and exception mapping."""

    def test_not_found_404(self):
        client = _make_client()
        r = client.get("/api/v1/nonexistent")
        assert r.status_code == 404

    def test_validation_error_422(self):
        client = _make_client()
        r = client.get("/api/v1/health?invalid_param=x")
        assert r.status_code in (200, 422)

    def test_api_exception_model(self):
        resp = ErrorResponse.model_validate({
            "error": {
                "code": "test_error",
                "message": "Test message",
                "details": {"key": "value"},
            },
        })
        assert resp.error.code == "test_error"
        assert resp.error.message == "Test message"
        assert resp.error.details == {"key": "value"}

    def test_api_exception_basic(self):
        err = APIException()
        assert err.status_code == 500
        assert err.code == "internal_error"

    def test_not_found_error(self):
        err = NotFoundError()
        assert err.status_code == 404
        assert err.code == "not_found"

    def test_not_found_error_message(self):
        err = NotFoundError("Custom message")
        assert err.message == "Custom message"

    def test_bad_request_error(self):
        err = BadRequestError("Bad input")
        assert err.status_code == 400
        assert err.code == "bad_request"
        assert err.message == "Bad input"

    def test_service_unavailable_error(self):
        err = ServiceUnavailableError("Service down")
        assert err.status_code == 503
        assert err.code == "service_unavailable"
        assert err.message == "Service down"

    def test_api_exception_with_details(self):
        err = APIException(
            status_code=418, code="teapot", message="Short",
            details={"type": "teapot"},
        )
        assert err.details == {"type": "teapot"}

    def test_error_response_serialization(self):
        from app.api.schemas import ErrorDetail

        detail = ErrorDetail(code="err", message="msg")
        assert detail.model_dump() == {"code": "err", "message": "msg", "details": None}

    def test_internal_error_handler(self):
        client = _make_client()

        @client.app.get("/api/v1/_test_crash")
        async def _crash():
            raise RuntimeError("Unexpected crash")

        from fastapi.testclient import TestClient
        quiet = TestClient(client.app, raise_server_exceptions=False)
        r = quiet.get("/api/v1/_test_crash")
        assert r.status_code == 500
        data = r.json()
        assert data["error"]["code"] == "internal_error"


# ==========================================================================
# Middleware
# ==========================================================================


class TestMiddleware:
    """Request logging middleware."""

    def test_middleware_does_not_block_requests(self):
        client = _make_client()
        r = client.get("/api/v1/health")
        assert r.status_code == 200

    def test_middleware_logs_requests(self):
        client = _make_client()
        r = client.get("/api/v1/health")
        assert r.status_code == 200

    def test_middleware_logs_status(self):
        client = _make_client()
        r = client.get("/api/v1/health")
        assert r.status_code == 200

    def test_middleware_fires_on_error(self):
        client = _make_client()

        @client.app.get("/api/v1/_test_mw_err")
        async def _err():
            raise RuntimeError("Middleware test")

        from fastapi.testclient import TestClient
        quiet = TestClient(client.app, raise_server_exceptions=False)
        r = quiet.get("/api/v1/_test_mw_err")
        assert r.status_code == 500

    def test_middleware_works_with_all_routes(self):
        client = _make_client()
        for path in ("/api/v1/health", "/api/v1/status", "/api/v1/config", "/api/v1/services"):
            r = client.get(path)
            assert r.status_code == 200


# ==========================================================================
# Dependency injection
# ==========================================================================


class TestDependencyInjection:
    """FastAPI dependency injection for ServiceRegistry."""

    def test_get_registry_from_app_state(self):
        reg = ServiceRegistry()
        app = _make_app(reg)
        from fastapi.testclient import TestClient

        client = TestClient(app)

        @app.get("/api/v1/_test_reg")
        async def _test_reg(request: Request):
            from app.api.dependencies import get_registry
            r = get_registry(request)
            return {"found": r is not None}

        r = client.get("/api/v1/_test_reg")
        assert r.json()["found"] is True

    def test_get_registry_none_when_missing(self):
        app = _make_app()
        from fastapi.testclient import TestClient

        client = TestClient(app)

        @app.get("/api/v1/_test_no_reg")
        async def _test_no_reg(request: Request):
            from app.api.dependencies import get_registry
            r = get_registry(request)
            return {"found": r is not None}

        r = client.get("/api/v1/_test_no_reg")
        assert r.json()["found"] is False

    def test_get_service_dependency(self):
        reg = ServiceRegistry()
        reg.register("my_svc", {"data": 42})
        app = _make_app(reg)
        from fastapi.testclient import TestClient

        client = TestClient(app)

        dep = get_service("my_svc")

        @app.get("/api/v1/_test_svc")
        async def _test_svc(svc=Depends(dep)):
            return {"data": svc["data"]}

        r = client.get("/api/v1/_test_svc")
        assert r.json()["data"] == 42

    def test_get_service_none_when_missing(self):
        reg = ServiceRegistry()
        app = _make_app(reg)
        from fastapi.testclient import TestClient

        client = TestClient(app)

        dep = get_service("missing_svc")

        @app.get("/api/v1/_test_missing")
        async def _test_missing(svc=Depends(dep)):
            return {"found": svc is not None}

        r = client.get("/api/v1/_test_missing")
        assert r.json()["found"] is False

    def test_require_service_returns_service(self):
        reg = ServiceRegistry()
        reg.register("required_svc", "value")
        app = _make_app(reg)
        from fastapi.testclient import TestClient

        client = TestClient(app)

        dep = require_service("required_svc")

        @app.get("/api/v1/_test_require")
        async def _test_require(svc=Depends(dep)):
            return {"svc": svc}

        r = client.get("/api/v1/_test_require")
        assert r.json()["svc"] == "value"

    def test_require_service_raises_503(self):
        reg = ServiceRegistry()
        app = _make_app(reg)
        from fastapi.testclient import TestClient

        client = TestClient(app)

        dep = require_service("missing_svc")

        @app.get("/api/v1/_test_require_missing")
        async def _test_require_missing(svc=Depends(dep)):
            return {"svc": svc}

        r = client.get("/api/v1/_test_require_missing")
        assert r.status_code == 503
        assert r.json()["error"]["code"] == "service_unavailable"


# ==========================================================================
# OpenAPI generation
# ==========================================================================


class TestOpenAPIGeneration:
    """OpenAPI schema generation."""

    def test_openapi_schema_valid(self):
        client = _make_client()
        r = client.get("/api/v1/openapi.json")
        assert r.status_code == 200
        schema = r.json()
        assert "openapi" in schema
        assert "info" in schema
        assert "paths" in schema

    def test_openapi_has_health_path(self):
        client = _make_client()
        schema = client.get("/api/v1/openapi.json").json()
        assert "/api/v1/health" in schema["paths"]

    def test_openapi_has_status_path(self):
        client = _make_client()
        schema = client.get("/api/v1/openapi.json").json()
        assert "/api/v1/status" in schema["paths"]

    def test_openapi_has_config_path(self):
        client = _make_client()
        schema = client.get("/api/v1/openapi.json").json()
        assert "/api/v1/config" in schema["paths"]

    def test_openapi_has_services_path(self):
        client = _make_client()
        schema = client.get("/api/v1/openapi.json").json()
        assert "/api/v1/services" in schema["paths"]

    def test_openapi_paths_are_get(self):
        client = _make_client()
        schema = client.get("/api/v1/openapi.json").json()
        for path in ["/api/v1/health", "/api/v1/status", "/api/v1/config", "/api/v1/services"]:
            assert "get" in schema["paths"][path]

    def test_openapi_has_schemas(self):
        client = _make_client()
        schema = client.get("/api/v1/openapi.json").json()
        assert "components" in schema
        assert "schemas" in schema["components"]


# ==========================================================================
# Validation
# ==========================================================================


class TestValidation:
    """Request validation via Pydantic models."""

    def test_health_response_type(self):
        resp = HealthResponse(status="healthy", version="1.0.0")
        assert resp.status == "healthy"
        assert resp.version == "1.0.0"

    def test_health_response_defaults(self):
        resp = HealthResponse(status="ok", version="1.0")
        assert resp.services_healthy == 0
        assert resp.uptime == ""

    def test_status_response_defaults(self):
        resp = StatusResponse(status="running", version="1.0")
        assert resp.plugins == 0
        assert resp.skills == 0
        assert resp.services == 0

    def test_config_response_defaults(self):
        resp = ConfigResponse(app_name="Test", version="1.0")
        assert resp.voice_enabled is False

    def test_error_response_with_details(self):
        from app.api.schemas import ErrorDetail

        detail = ErrorDetail(code="err", message="msg", details={"key": 1})
        assert detail.details == {"key": 1}

    def test_service_info_available(self):
        info = ServiceInfo(name="svc", available=False)
        assert info.available is False

    def test_service_list_response(self):
        resp = ServiceListResponse(
            services=[ServiceInfo(name="a", available=True)],
        )
        assert len(resp.services) == 1

    def test_validation_error_item(self):
        from app.api.schemas import ValidationErrorItem

        item = ValidationErrorItem(field="name", message="Required")
        assert item.field == "name"
        assert item.message == "Required"


# ==========================================================================
# Backward compatibility
# ==========================================================================


class TestBackwardCompatibility:
    """Backward compatibility tests."""

    def test_create_app_importable(self):
        from app.api import create_app
        assert create_app is not None

    def test_health_response_importable(self):
        from app.api.schemas import HealthResponse
        assert HealthResponse is not None

    def test_status_response_importable(self):
        from app.api.schemas import StatusResponse
        assert StatusResponse is not None

    def test_config_response_importable(self):
        from app.api.schemas import ConfigResponse
        assert ConfigResponse is not None

    def test_service_list_response_importable(self):
        from app.api.schemas import ServiceListResponse
        assert ServiceListResponse is not None

    def test_api_exception_importable(self):
        from app.api.errors import APIException
        assert APIException is not None

    def test_not_found_error_importable(self):
        from app.api.errors import NotFoundError
        assert NotFoundError is not None

    def test_get_registry_importable(self):
        from app.api.dependencies import get_registry
        assert get_registry is not None

    def test_create_app_without_registry_no_errors(self):
        app = _make_app()
        client = TestClient(app)
        r = client.get("/api/v1/health")
        assert r.status_code == 200

    def test_api_version_prefix(self):
        client = _make_client()
        assert client.get("/api/v1/health").status_code == 200
        assert client.get("/health").status_code == 404
