"""Tests for the Evolution REST API (P11-07)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.server import create_app
from app.core.registry import ServiceRegistry


# ==========================================================================
# Helpers
# ==========================================================================


def _make_app(registry: ServiceRegistry | None = None) -> FastAPI:
    if registry is None:
        registry = ServiceRegistry()
        registry.register("dispatcher", MagicMock())
        registry.register("event_bus", MagicMock())
    return create_app(registry)


def _make_client(registry: ServiceRegistry | None = None) -> TestClient:
    app = _make_app(registry)
    return TestClient(app)


def _make_evolution_app() -> FastAPI:
    """Build an app with a fully mocked evolution_ai service."""
    ai_router = MagicMock()
    ai_manager = MagicMock()
    registry = ServiceRegistry()
    registry.register("ai_router", ai_router)
    registry.register("ai_manager", ai_manager)
    registry.register("dispatcher", MagicMock())
    registry.register("event_bus", MagicMock())

    evo_mock = MagicMock()
    evo_mock.plan.return_value = "Mocked evolution plan"
    evo_mock.generate.return_value = "Mocked generated code"
    evo_mock.autofix.return_value = "Mocked fixed code"
    evo_mock._ai = ai_manager
    evo_mock._router = ai_router
    registry.register("evolution_ai", evo_mock)
    return create_app(registry)


def _make_evolution_client():
    return TestClient(_make_evolution_app())


# ==========================================================================
# Route registration
# ==========================================================================


class TestEvolutionRouteRegistration:
    """Evolution routes appear in OpenAPI schema."""

    def test_evolution_routes_in_openapi(self):
        client = _make_client()
        schema = client.get("/api/v1/openapi.json").json()
        paths = schema["paths"]
        assert "/api/v1/evolution/status" in paths
        assert "/api/v1/evolution/scan" in paths
        assert "/api/v1/evolution/plan" in paths
        assert "/api/v1/evolution/generate" in paths
        assert "/api/v1/evolution/autofix" in paths
        assert "/api/v1/evolution/validate" in paths
        assert "/api/v1/evolution/sandbox" in paths
        assert "/api/v1/evolution/upgrade" in paths
        assert "/api/v1/evolution/history" in paths


# ==========================================================================
# Status
# ==========================================================================


class TestEvolutionStatus:
    """GET /api/v1/evolution/status"""

    def test_status_returns_analysis(self):
        client = _make_client()
        resp = client.get("/api/v1/evolution/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "version" in data
        assert "files" in data
        assert "lines" in data
        assert "hash" in data
        assert isinstance(data["files"], int)
        assert isinstance(data["lines"], int)
        assert isinstance(data["hash"], str)
        assert len(data["hash"]) > 0


# ==========================================================================
# Scan
# ==========================================================================


class TestEvolutionScan:
    """POST /api/v1/evolution/scan"""

    def test_scan_default_root(self):
        client = _make_client()
        resp = client.post("/api/v1/evolution/scan", json={"root": "app/evolution"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["python_files"] > 0
        assert "files" in data["summary"]
        assert "classes" in data["summary"]
        assert "functions" in data["summary"]

    def test_scan_response_shape(self):
        client = _make_client()
        resp = client.post("/api/v1/evolution/scan", json={})
        assert resp.status_code == 200
        data = resp.json()
        for field in ("status", "python_files", "classes", "functions", "imports", "summary"):
            assert field in data, f"Missing field: {field}"


# ==========================================================================
# Plan
# ==========================================================================


class TestEvolutionPlan:
    """POST /api/v1/evolution/plan"""

    def test_plan_requires_registry(self):
        client = TestClient(create_app())
        resp = client.post("/api/v1/evolution/plan", json={})
        assert resp.status_code == 503

    def test_plan_with_registry(self):
        client = _make_evolution_client()
        with patch("app.evolution.planner.Path") as mock_path:
            mock_path.return_value.read_text.return_value = "Mock prompt"
            resp = client.post("/api/v1/evolution/plan", json={"objective": "Improve code"})
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "ok"
            assert "plan" in data


# ==========================================================================
# Generate
# ==========================================================================


class TestEvolutionGenerate:
    """POST /api/v1/evolution/generate"""

    def test_generate_requires_registry(self):
        client = TestClient(create_app())
        resp = client.post(
            "/api/v1/evolution/generate",
            json={"task": "add feature", "target_file": "app/evolution/analyzer.py"},
        )
        assert resp.status_code == 503

    def test_generate_missing_task(self):
        client = _make_client()
        resp = client.post(
            "/api/v1/evolution/generate",
            json={"task": "", "target_file": "app/evolution/analyzer.py"},
        )
        assert resp.status_code == 422

    def test_generate_missing_target(self):
        client = _make_client()
        resp = client.post(
            "/api/v1/evolution/generate",
            json={"task": "add feature", "target_file": ""},
        )
        assert resp.status_code == 422

    def test_generate_with_registry(self):
        client = _make_evolution_client()
        with patch("app.evolution.generator.Path") as mock_path:
            mock_instance = MagicMock()
            mock_path.return_value = mock_instance
            mock_instance.read_text.return_value = "# mock source"
            resp = client.post(
                "/api/v1/evolution/generate",
                json={"task": "refactor", "target_file": "app/evolution/analyzer.py"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "ok"
            assert "output_path" in data or "generated_patch.py" in str(data.get("output_path", ""))


# ==========================================================================
# Autofix
# ==========================================================================


class TestEvolutionAutofix:
    """POST /api/v1/evolution/autofix"""

    def test_autofix_requires_registry(self):
        client = TestClient(create_app())
        resp = client.post("/api/v1/evolution/autofix", json={})
        assert resp.status_code == 503

    def test_autofix_with_registry(self):
        client = _make_evolution_client()
        with patch("app.evolution.autofix.Path") as mock_path:
            mock_instance = MagicMock()
            mock_path.return_value = mock_instance
            mock_instance.read_text.return_value = "# review\nWARNING: lint issue"
            resp = client.post("/api/v1/evolution/autofix", json={})
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "ok"
            assert "patch_file" in data


# ==========================================================================
# Validate
# ==========================================================================


class TestEvolutionValidate:
    """POST /api/v1/evolution/validate"""

    def test_validate_valid_patch(self, tmp_path: Path):
        patch_file = tmp_path / "patch.py"
        patch_file.write_text("x = 1\n")
        client = _make_client()
        resp = client.post(
            "/api/v1/evolution/validate",
            json={"patch_path": str(patch_file)},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "valid" in data
        assert "report" in data

    def test_validate_invalid_syntax(self, tmp_path: Path):
        patch_file = tmp_path / "bad_patch.py"
        patch_file.write_text("def foo(:\n")
        client = _make_client()
        resp = client.post(
            "/api/v1/evolution/validate",
            json={"patch_path": str(patch_file)},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False
        assert any("FAIL" in line for line in data["report"])

    def test_validate_response_shape(self, tmp_path: Path):
        patch_file = tmp_path / "shape_patch.py"
        patch_file.write_text("pass\n")
        client = _make_client()
        resp = client.post(
            "/api/v1/evolution/validate",
            json={"patch_path": str(patch_file)},
        )
        data = resp.json()
        for field in ("valid", "report"):
            assert field in data, f"Missing field: {field}"


# ==========================================================================
# Sandbox
# ==========================================================================


class TestEvolutionSandbox:
    """POST /api/v1/evolution/sandbox"""

    def test_sandbox_simple_code(self):
        client = _make_client()
        resp = client.post(
            "/api/v1/evolution/sandbox",
            json={"source": "print('hello')"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "success" in data
        assert "returncode" in data
        assert "stdout" in data
        assert "stderr" in data
        assert "execution_time" in data
        assert "timed_out" in data
        assert "security_violations" in data

    def test_sandbox_blocked_import(self):
        client = _make_client()
        resp = client.post(
            "/api/v1/evolution/sandbox",
            json={"source": "import socket\n"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert len(data["security_violations"]) > 0

    def test_sandbox_response_shape(self):
        client = _make_client()
        resp = client.post(
            "/api/v1/evolution/sandbox",
            json={"source": "pass\n"},
        )
        data = resp.json()
        for field in ("success", "returncode", "stdout", "stderr",
                      "execution_time", "timed_out", "security_violations"):
            assert field in data, f"Missing field: {field}"


# ==========================================================================
# Upgrade
# ==========================================================================


class TestEvolutionUpgrade:
    """POST /api/v1/evolution/upgrade"""

    def test_upgrade_returns_report(self):
        client = _make_client()
        resp = client.post("/api/v1/evolution/upgrade")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert len(data["message"]) > 0

    def test_upgrade_response_shape(self):
        client = _make_client()
        resp = client.post("/api/v1/evolution/upgrade")
        data = resp.json()
        for field in ("success", "message"):
            assert field in data, f"Missing field: {field}"


# ==========================================================================
# History
# ==========================================================================


class TestEvolutionHistory:
    """GET /api/v1/evolution/history"""

    def test_history_returns_list(self):
        client = _make_client()
        resp = client.get("/api/v1/evolution/history")
        assert resp.status_code == 200
        data = resp.json()
        assert "history" in data
        assert isinstance(data["history"], list)
        if data["history"]:
            entry = data["history"][0]
            assert "timestamp" in entry
            assert "action" in entry
            assert "details" in entry

    def test_history_response_shape(self):
        client = _make_client()
        resp = client.get("/api/v1/evolution/history")
        data = resp.json()
        for field in ("history",):
            assert field in data, f"Missing field: {field}"


# ==========================================================================
# Error handling
# ==========================================================================


class TestEvolutionErrorHandling:
    """Verify proper error status codes."""

    def test_service_unavailable_on_plan(self):
        client = TestClient(create_app())
        resp = client.post("/api/v1/evolution/plan", json={})
        assert resp.status_code == 503

    def test_service_unavailable_on_generate(self):
        client = TestClient(create_app())
        resp = client.post(
            "/api/v1/evolution/generate",
            json={"task": "x", "target_file": "x.py"},
        )
        assert resp.status_code == 503

    def test_service_unavailable_on_autofix(self):
        client = TestClient(create_app())
        resp = client.post("/api/v1/evolution/autofix", json={})
        assert resp.status_code == 503
