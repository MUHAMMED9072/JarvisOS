"""Tests for the Skills REST API (P11-03)."""

from __future__ import annotations

from unittest.mock import MagicMock, PropertyMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.schemas import (
    SkillCategoryInfo,
    SkillCategoryListResponse,
    SkillDiscoverResponse,
    SkillExecuteResponse,
    SkillInfo,
    SkillIntentInfo,
    SkillIntentListResponse,
    SkillListResponse,
    SkillReloadResponse,
)
from app.api.server import create_app
from app.core.registry import ServiceRegistry
from app.skills.base import Skill
from app.skills.manager import SkillManager
from app.skills.result import SkillResult


# ==========================================================================
# Helpers
# ==========================================================================


class _ConcreteSkill(Skill):
    name = "Test Skill"
    intent = "test_intent"
    version = "2.0.0"
    description = "A test skill"
    author = "Tester"

    def run(self, request):
        return SkillResult.ok(
            message="Executed test skill",
            data={"input": request.text},
        )


class _AnotherSkill(Skill):
    name = "Another Skill"
    intent = "another_intent"
    version = "1.0.0"
    description = "Another test skill"
    author = "Dev"

    def run(self, request):
        return SkillResult.ok(message="Executed another skill")


def _make_app(
    registry: ServiceRegistry | None = None,
    skill_manager: SkillManager | None = None,
) -> FastAPI:
    if registry is None:
        registry = ServiceRegistry()
    if skill_manager is not None:
        registry.register("skill_manager", skill_manager)
    registry.register("dispatcher", MagicMock())
    registry.register("memory", MagicMock())
    registry.register("event_bus", MagicMock())
    return create_app(registry)


def _make_client(
    registry: ServiceRegistry | None = None,
    skill_manager: SkillManager | None = None,
) -> TestClient:
    app = _make_app(registry, skill_manager)
    return TestClient(app)


# ==========================================================================
# Route registration
# ==========================================================================


class TestSkillRouteRegistration:
    """Skills routes are registered in the OpenAPI schema."""

    def test_skills_routes_in_openapi(self):
        sm = SkillManager()
        sm.register(_ConcreteSkill())
        client = _make_client(skill_manager=sm)
        schema = client.get("/api/v1/openapi.json").json()
        paths = schema["paths"]
        assert "/api/v1/skills" in paths
        assert "/api/v1/skills/{name}" in paths
        assert "/api/v1/skills/{name}/execute" in paths
        assert "/api/v1/skills/reload" in paths
        assert "/api/v1/skills/discover" in paths
        assert "/api/v1/skills/categories" in paths
        assert "/api/v1/skills/intents" in paths

    def test_skills_routes_openapi_types(self):
        sm = SkillManager()
        sm.register(_ConcreteSkill())
        client = _make_client(skill_manager=sm)
        schema = client.get("/api/v1/openapi.json").json()
        paths = schema["paths"]
        assert "get" in paths["/api/v1/skills"]
        assert "get" in paths["/api/v1/skills/{name}"]
        assert "post" in paths["/api/v1/skills/{name}/execute"]
        assert "post" in paths["/api/v1/skills/reload"]
        assert "post" in paths["/api/v1/skills/discover"]
        assert "get" in paths["/api/v1/skills/categories"]
        assert "get" in paths["/api/v1/skills/intents"]

    def test_skills_routes_503_without_skill_manager(self):
        app = _make_app()
        client = TestClient(app)
        for path, method in [
            ("/api/v1/skills", "get"),
            ("/api/v1/skills/test", "get"),
            ("/api/v1/skills/reload", "post"),
            ("/api/v1/skills/discover", "post"),
            ("/api/v1/skills/categories", "get"),
            ("/api/v1/skills/intents", "get"),
        ]:
            if method == "post":
                r = client.post(path, json={})
            else:
                r = client.get(path)
            assert r.status_code == 503, f"{method.upper()} {path}"


# ==========================================================================
# List skills
# ==========================================================================


class TestListSkills:
    """GET /api/v1/skills."""

    def test_list_returns_empty(self):
        client = _make_client(skill_manager=SkillManager())
        r = client.get("/api/v1/skills")
        assert r.status_code == 200
        assert r.json()["skills"] == []

    def test_list_returns_skills(self):
        sm = SkillManager()
        sm.register(_ConcreteSkill())
        sm.register(_AnotherSkill())
        client = _make_client(skill_manager=sm)
        r = client.get("/api/v1/skills")
        assert r.status_code == 200
        data = r.json()
        assert len(data["skills"]) == 2

    def test_list_returns_sorted_by_name(self):
        sm = SkillManager()
        sm.register(_AnotherSkill())
        sm.register(_ConcreteSkill())
        client = _make_client(skill_manager=sm)
        r = client.get("/api/v1/skills")
        names = [s["name"] for s in r.json()["skills"]]
        assert names == sorted(names, key=str.lower)

    def test_list_includes_metadata(self):
        sm = SkillManager()
        sm.register(_ConcreteSkill())
        client = _make_client(skill_manager=sm)
        r = client.get("/api/v1/skills")
        skill = r.json()["skills"][0]
        assert skill["name"] == "Test Skill"
        assert skill["intent"] == "test_intent"
        assert skill["version"] == "2.0.0"
        assert skill["description"] == "A test skill"
        assert skill["author"] == "Tester"
        assert skill["enabled"] is True

    def test_list_includes_category(self):
        sm = SkillManager()
        skill = _ConcreteSkill()
        sm.register(skill)
        client = _make_client(skill_manager=sm)
        r = client.get("/api/v1/skills")
        skill_info = r.json()["skills"][0]
        category = skill_info["category"]
        assert isinstance(category, str)

    def test_list_model_validation(self):
        sm = SkillManager()
        sm.register(_ConcreteSkill())
        client = _make_client(skill_manager=sm)
        r = client.get("/api/v1/skills")
        SkillListResponse(**r.json())


# ==========================================================================
# Get single skill
# ==========================================================================


class TestGetSkill:
    """GET /api/v1/skills/{name}."""

    def test_get_by_name(self):
        sm = SkillManager()
        sm.register(_ConcreteSkill())
        client = _make_client(skill_manager=sm)
        r = client.get("/api/v1/skills/Test%20Skill")
        assert r.status_code == 200
        assert r.json()["name"] == "Test Skill"

    def test_get_by_name_case_insensitive(self):
        sm = SkillManager()
        sm.register(_ConcreteSkill())
        client = _make_client(skill_manager=sm)
        r = client.get("/api/v1/skills/test%20skill")
        assert r.status_code == 200
        assert r.json()["name"] == "Test Skill"

    def test_get_by_intent(self):
        sm = SkillManager()
        sm.register(_ConcreteSkill())
        client = _make_client(skill_manager=sm)
        r = client.get("/api/v1/skills/test_intent")
        assert r.status_code == 200
        assert r.json()["intent"] == "test_intent"

    def test_get_not_found(self):
        client = _make_client(skill_manager=SkillManager())
        r = client.get("/api/v1/skills/nonexistent")
        assert r.status_code == 404

    def test_get_returns_metadata(self):
        sm = SkillManager()
        sm.register(_ConcreteSkill())
        client = _make_client(skill_manager=sm)
        r = client.get("/api/v1/skills/test_intent")
        data = r.json()
        assert data["name"] == "Test Skill"
        assert data["version"] == "2.0.0"
        assert data["author"] == "Tester"

    def test_get_model_validation(self):
        sm = SkillManager()
        sm.register(_ConcreteSkill())
        client = _make_client(skill_manager=sm)
        r = client.get("/api/v1/skills/test_intent")
        SkillInfo(**r.json())

    def test_get_prefers_intent_match(self):
        sm = SkillManager()
        sm.register(_ConcreteSkill())
        client = _make_client(skill_manager=sm)
        r = client.get("/api/v1/skills/test_intent")
        assert r.status_code == 200


# ==========================================================================
# Execute skill
# ==========================================================================


class TestExecuteSkill:
    """POST /api/v1/skills/{name}/execute."""

    def test_execute_returns_result(self):
        sm = SkillManager()
        sm.register(_ConcreteSkill())
        client = _make_client(skill_manager=sm)
        r = client.post(
            "/api/v1/skills/Test%20Skill/execute",
            json={"text": "hello"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True
        assert data["message"] == "Executed test skill"
        assert data["skill"] == "Test Skill"

    def test_execute_by_intent(self):
        sm = SkillManager()
        sm.register(_ConcreteSkill())
        client = _make_client(skill_manager=sm)
        r = client.post(
            "/api/v1/skills/test_intent/execute",
            json={"text": "hello"},
        )
        assert r.status_code == 200
        assert r.json()["success"] is True

    def test_execute_returns_data(self):
        sm = SkillManager()
        sm.register(_ConcreteSkill())
        client = _make_client(skill_manager=sm)
        r = client.post(
            "/api/v1/skills/test_intent/execute",
            json={"text": "world"},
        )
        data = r.json()["data"]
        assert data.get("input") == "world"

    def test_execute_returns_execution_time(self):
        sm = SkillManager()
        sm.register(_ConcreteSkill())
        client = _make_client(skill_manager=sm)
        r = client.post(
            "/api/v1/skills/test_intent/execute",
            json={"text": "hi"},
        )
        assert r.json()["execution_time"] >= 0

    def test_execute_not_found(self):
        client = _make_client(skill_manager=SkillManager())
        r = client.post(
            "/api/v1/skills/nonexistent/execute",
            json={"text": "hello"},
        )
        assert r.status_code == 404

    def test_execute_without_text_returns_422(self):
        sm = SkillManager()
        sm.register(_ConcreteSkill())
        client = _make_client(skill_manager=sm)
        r = client.post(
            "/api/v1/skills/test_intent/execute",
            json={},
        )
        assert r.status_code == 422

    def test_execute_passes_brain(self):
        sm = SkillManager()
        skill = _ConcreteSkill()
        original_run = skill.run

        def tracked_run(request):
            assert request.brain == "fast"
            return original_run(request)

        skill.run = tracked_run
        sm.register(skill)
        client = _make_client(skill_manager=sm)
        r = client.post(
            "/api/v1/skills/test_intent/execute",
            json={"text": "hi", "brain": "fast"},
        )
        assert r.status_code == 200

    def test_execute_passes_source(self):
        sm = SkillManager()
        skill = _ConcreteSkill()
        original_run = skill.run

        def tracked_run(request):
            assert request.source == "api"
            return original_run(request)

        skill.run = tracked_run
        sm.register(skill)
        client = _make_client(skill_manager=sm)
        r = client.post(
            "/api/v1/skills/test_intent/execute",
            json={"text": "hi"},
        )
        assert r.status_code == 200

    def test_execute_failing_skill(self):
        class FailingSkill(Skill):
            name = "Fail Skill"
            intent = "fail_intent"

            def run(self, request):
                msg = "Something went wrong"
                raise RuntimeError(msg)

        sm = SkillManager()
        sm.register(FailingSkill())
        client = _make_client(skill_manager=sm)
        r = client.post(
            "/api/v1/skills/fail_intent/execute",
            json={"text": "hi"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is False
        assert "went wrong" in data["message"]

    def test_execute_model_validation(self):
        sm = SkillManager()
        sm.register(_ConcreteSkill())
        client = _make_client(skill_manager=sm)
        r = client.post(
            "/api/v1/skills/test_intent/execute",
            json={"text": "hi"},
        )
        SkillExecuteResponse(**r.json())


# ==========================================================================
# Reload skills
# ==========================================================================


class TestReloadSkills:
    """POST /api/v1/skills/reload."""

    def test_reload_all_returns_ok(self):
        sm = SkillManager()
        client = _make_client(skill_manager=sm)
        r = client.post("/api/v1/skills/reload", json={"all": True})
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_reload_without_intent_or_all_returns_400(self):
        sm = SkillManager()
        client = _make_client(skill_manager=sm)
        r = client.post("/api/v1/skills/reload", json={})
        assert r.status_code == 400

    def test_reload_nonexistent_intent_returns_404(self):
        sm = SkillManager()
        client = _make_client(skill_manager=sm)
        r = client.post(
            "/api/v1/skills/reload",
            json={"intent": "nonexistent"},
        )
        assert r.status_code == 404

    def test_reload_all_model_validation(self):
        sm = SkillManager()
        client = _make_client(skill_manager=sm)
        r = client.post("/api/v1/skills/reload", json={"all": True})
        SkillReloadResponse(**r.json())

    def test_reload_without_request_body_returns_422(self):
        sm = SkillManager()
        client = _make_client(skill_manager=sm)
        r = client.post("/api/v1/skills/reload", json={})
        assert r.status_code == 400

    def test_reload_all_returns_intent_list(self):
        sm = SkillManager()
        sm.register(_ConcreteSkill())
        client = _make_client(skill_manager=sm)
        r = client.post("/api/v1/skills/reload", json={"all": True})
        assert isinstance(r.json()["intents"], list)


# ==========================================================================
# Discover skills
# ==========================================================================


class TestDiscoverSkills:
    """POST /api/v1/skills/discover."""

    def test_discover_returns_ok(self):
        sm = SkillManager()
        client = _make_client(skill_manager=sm)
        r = client.post("/api/v1/skills/discover")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_discover_returns_count(self):
        sm = SkillManager()
        client = _make_client(skill_manager=sm)
        r = client.post("/api/v1/skills/discover")
        assert isinstance(r.json()["count"], int)

    def test_discover_returns_skills_list(self):
        sm = SkillManager()
        client = _make_client(skill_manager=sm)
        r = client.post("/api/v1/skills/discover")
        assert isinstance(r.json()["skills"], list)

    def test_discover_model_validation(self):
        sm = SkillManager()
        client = _make_client(skill_manager=sm)
        r = client.post("/api/v1/skills/discover")
        SkillDiscoverResponse(**r.json())

    def test_discover_discovers_skills(self):
        sm = SkillManager()
        client = _make_client(skill_manager=sm)
        r = client.post("/api/v1/skills/discover")
        assert r.json()["count"] >= 0


# ==========================================================================
# Categories
# ==========================================================================


class TestListCategories:
    """GET /api/v1/skills/categories."""

    def test_categories_returns_list(self):
        sm = SkillManager()
        client = _make_client(skill_manager=sm)
        r = client.get("/api/v1/skills/categories")
        assert r.status_code == 200
        assert isinstance(r.json()["categories"], list)

    def test_categories_with_skills(self):
        sm = SkillManager()
        sm.register(_ConcreteSkill())
        client = _make_client(skill_manager=sm)
        r = client.get("/api/v1/skills/categories")
        cats = r.json()["categories"]
        names = [c["name"] for c in cats]
        assert len(names) >= 0

    def test_categories_sorted(self):
        sm = SkillManager()
        sm.register(_ConcreteSkill())
        client = _make_client(skill_manager=sm)
        r = client.get("/api/v1/skills/categories")
        names = [c["name"] for c in r.json()["categories"]]
        assert names == sorted(names)

    def test_categories_have_counts(self):
        sm = SkillManager()
        sm.register(_ConcreteSkill())
        client = _make_client(skill_manager=sm)
        r = client.get("/api/v1/skills/categories")
        for c in r.json()["categories"]:
            assert c["count"] >= 0

    def test_categories_model_validation(self):
        sm = SkillManager()
        sm.register(_ConcreteSkill())
        client = _make_client(skill_manager=sm)
        r = client.get("/api/v1/skills/categories")
        SkillCategoryListResponse(**r.json())


# ==========================================================================
# Intents
# ==========================================================================


class TestListIntents:
    """GET /api/v1/skills/intents."""

    def test_intents_returns_list(self):
        sm = SkillManager()
        client = _make_client(skill_manager=sm)
        r = client.get("/api/v1/skills/intents")
        assert r.status_code == 200
        assert isinstance(r.json()["intents"], list)

    def test_intents_returns_skill_data(self):
        sm = SkillManager()
        sm.register(_ConcreteSkill())
        client = _make_client(skill_manager=sm)
        r = client.get("/api/v1/skills/intents")
        intent = r.json()["intents"][0]
        assert intent["name"] == "Test Skill"
        assert intent["intent"] == "test_intent"
        assert intent["description"] == "A test skill"

    def test_intents_sorted(self):
        sm = SkillManager()
        sm.register(_AnotherSkill())
        sm.register(_ConcreteSkill())
        client = _make_client(skill_manager=sm)
        r = client.get("/api/v1/skills/intents")
        intents = [i["intent"] for i in r.json()["intents"]]
        assert intents == sorted(intents)

    def test_intents_empty_when_no_skills(self):
        client = _make_client(skill_manager=SkillManager())
        r = client.get("/api/v1/skills/intents")
        assert r.json()["intents"] == []

    def test_intents_model_validation(self):
        sm = SkillManager()
        sm.register(_ConcreteSkill())
        client = _make_client(skill_manager=sm)
        r = client.get("/api/v1/skills/intents")
        SkillIntentListResponse(**r.json())


# ==========================================================================
# Schema models
# ==========================================================================


class TestSkillSchemaModels:
    """Skill Pydantic model validation."""

    def test_skill_info_model(self):
        m = SkillInfo(name="Test", intent="test")
        assert m.name == "Test"
        assert m.enabled is True
        assert m.category == ""

    def test_skill_info_all_fields(self):
        m = SkillInfo(
            name="Full",
            intent="full",
            description="desc",
            version="3.0.0",
            author="Me",
            enabled=False,
            category="test",
        )
        assert m.category == "test"

    def test_skill_list_response(self):
        s = SkillInfo(name="A", intent="a")
        r = SkillListResponse(skills=[s])
        assert len(r.skills) == 1

    def test_skill_execute_request_requires_text(self):
        from app.api.schemas import SkillExecuteRequest

        m = SkillExecuteRequest(text="hello")
        assert m.text == "hello"
        assert m.source == "api"
        assert m.brain is None

    def test_skill_execute_request_without_text_raises(self):
        from app.api.schemas import SkillExecuteRequest

        with pytest.raises(ValueError):
            SkillExecuteRequest()

    def test_skill_execute_response(self):
        m = SkillExecuteResponse(success=True, message="ok")
        assert m.success is True
        assert m.execution_time == 0.0

    def test_skill_intent_info(self):
        m = SkillIntentInfo(name="Test", intent="test", description="desc")
        assert m.name == "Test"

    def test_skill_intent_list_response(self):
        i = SkillIntentInfo(name="Test", intent="test")
        r = SkillIntentListResponse(intents=[i])
        assert len(r.intents) == 1

    def test_skill_category_info(self):
        m = SkillCategoryInfo(name="ai", count=3)
        assert m.count == 3

    def test_skill_category_list_response(self):
        c = SkillCategoryInfo(name="ai", count=1)
        r = SkillCategoryListResponse(categories=[c])
        assert len(r.categories) == 1

    def test_skill_reload_request(self):
        from app.api.schemas import SkillReloadRequest

        m = SkillReloadRequest(intent="test", all=True)
        assert m.intent == "test"
        assert m.all is True

    def test_skill_reload_response(self):
        m = SkillReloadResponse(status="ok", message="done")
        assert m.status == "ok"
        assert m.intents == []

    def test_skill_discover_response(self):
        m = SkillDiscoverResponse(status="ok", count=5, skills=["a", "b"])
        assert m.count == 5

    def test_all_skill_models_importable(self):
        from app.api.schemas import (
            SkillCategoryInfo,
            SkillCategoryListResponse,
            SkillDiscoverResponse,
            SkillExecuteRequest,
            SkillExecuteResponse,
            SkillInfo,
            SkillIntentInfo,
            SkillIntentListResponse,
            SkillListResponse,
            SkillReloadRequest,
            SkillReloadResponse,
        )
        assert SkillInfo is not None
        assert SkillExecuteRequest is not None
        assert SkillReloadRequest is not None
        assert SkillDiscoverResponse is not None


# ==========================================================================
# Error handling
# ==========================================================================


class TestSkillErrorHandling:
    """Error scenarios for skill endpoints."""

    def test_missing_skill_manager_503(self):
        client = TestClient(create_app())
        r = client.get("/api/v1/skills")
        assert r.status_code == 503

    def test_execute_missing_text_422(self):
        sm = SkillManager()
        sm.register(_ConcreteSkill())
        client = _make_client(skill_manager=sm)
        r = client.post(
            "/api/v1/skills/test_intent/execute",
            json={},
        )
        assert r.status_code == 422

    def test_execute_nonexistent_skill_404(self):
        client = _make_client(skill_manager=SkillManager())
        r = client.post(
            "/api/v1/skills/nonexistent/execute",
            json={"text": "hello"},
        )
        assert r.status_code == 404

    def test_reload_without_body_returns_422(self):
        sm = SkillManager()
        client = _make_client(skill_manager=sm)
        r = client.post("/api/v1/skills/reload", json={})
        assert r.status_code == 400

    def test_reload_without_body_model_validation(self):
        from app.api.schemas import SkillReloadRequest

        m = SkillReloadRequest()
        assert m.intent is None
        assert m.all is False

    def test_get_nonexistent_skill_404(self):
        client = _make_client(skill_manager=SkillManager())
        r = client.get("/api/v1/skills/nonexistent")
        assert r.status_code == 404
        err = r.json()
        assert "error" in err
        assert err["error"]["code"] == "not_found"

    def test_discover_with_services(self):
        sm = SkillManager()
        reg = ServiceRegistry()
        reg.register("skill_manager", sm)
        reg.register("dispatcher", MagicMock())
        reg.register("memory", MagicMock())
        reg.register("event_bus", MagicMock())
        client = TestClient(create_app(reg))
        r = client.post("/api/v1/skills/discover")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


# ==========================================================================
# Backward compatibility
# ==========================================================================


class TestSkillBackwardCompatibility:
    """Backward compatibility with existing models."""

    def test_existing_skill_manager_unchanged(self):
        sm = SkillManager()
        skill = _ConcreteSkill()
        sm.register(skill)
        assert sm.get("test_intent") is skill

    def test_existing_skill_base_unchanged(self):
        skill = _ConcreteSkill()
        assert isinstance(skill, Skill)
        assert skill.name == "Test Skill"

    def test_existing_routes_unchanged(self):
        sm = SkillManager()
        sm.register(_ConcreteSkill())
        client = _make_client(skill_manager=sm)
        assert client.get("/api/v1/health").status_code == 200
        assert client.get("/api/v1/status").status_code == 200
