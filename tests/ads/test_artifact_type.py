from __future__ import annotations

import pytest

from app.ads.artifact_type import (
    ADS_STAGES,
    ArtifactType,
    BUILTIN_ARTIFACT_TYPES,
)
from app.ads.type_registry import ARTIFACT_TYPE_REGISTRY, ArtifactTypeRegistry


class TestArtifactType:
    def test_create(self):
        at = ArtifactType(name="TestType", description="A test type")
        assert at.name == "TestType"

    def test_to_dict(self):
        at = ArtifactType(name="MyType", description="Desc", stages=["build", "test"])
        d = at.to_dict()
        assert d["name"] == "MyType"
        assert d["stages"] == ["build", "test"]


class TestBuiltinTypes:
    def test_ten_types(self):
        assert len(BUILTIN_ARTIFACT_TYPES) == 10

    def test_all_have_names(self):
        for name, at in BUILTIN_ARTIFACT_TYPES.items():
            assert at.name == name

    def test_agent_type(self):
        at = BUILTIN_ARTIFACT_TYPES["Agent"]
        assert at.base_class == "app.agents.base.Agent"
        assert at.output_extension == ".py"

    def test_documentation_type(self):
        at = BUILTIN_ARTIFACT_TYPES["Documentation"]
        assert at.base_class is None
        assert at.output_extension == ".md"

    def test_workflow_type(self):
        at = BUILTIN_ARTIFACT_TYPES["Workflow"]
        assert at.output_extension == ".yaml"

    def test_tool_manifest_schema(self):
        schema = BUILTIN_ARTIFACT_TYPES["Tool"].manifest_schema
        assert "tool_name" in schema.get("required", [])

    def test_agent_manifest_schema(self):
        schema = BUILTIN_ARTIFACT_TYPES["Agent"].manifest_schema
        assert "capabilities" in schema.get("required", [])

    def test_doc_schema_has_format_enum(self):
        schema = BUILTIN_ARTIFACT_TYPES["Documentation"].manifest_schema
        fmt = schema["properties"]["format"]
        assert fmt["enum"] == ["markdown", "html", "rst"]


class TestArtifactTypeRegistry:
    @pytest.fixture
    def registry(self):
        return ArtifactTypeRegistry()

    def test_list_types(self, registry):
        types = registry.list_types()
        assert len(types) == 10

    def test_get(self, registry):
        at = registry.get("Agent")
        assert at is not None
        assert at.name == "Agent"

    def test_get_nonexistent(self, registry):
        assert registry.get("NoSuchType") is None

    def test_is_valid(self, registry):
        assert registry.is_valid("Agent") is True
        assert registry.is_valid("NoSuchType") is False

    def test_get_stages(self, registry):
        stages = registry.get_stages("Agent")
        assert len(stages) == len(ADS_STAGES)

    def test_get_stages_doc(self, registry):
        stages = registry.get_stages("Documentation")
        assert "benchmark" not in stages  # doc skips benchmark

    def test_get_base_class(self, registry):
        assert registry.get_base_class("Agent") == "app.agents.base.Agent"
        assert registry.get_base_class("Documentation") is None

    def test_register_new_type(self, registry):
        new_type = ArtifactType(name="CustomAgent", description="Custom")
        registry.register(new_type)
        assert registry.is_valid("CustomAgent") is True
        assert registry.count() == 11

    def test_runtime_registration(self, registry):
        """Extensibility: agents can register new types at runtime."""
        assert registry.is_valid("MyPlugin") is False
        registry.register(ArtifactType(name="MyPlugin", description="Runtime plugin"))
        assert registry.is_valid("MyPlugin") is True

    def test_singleton(self):
        assert ARTIFACT_TYPE_REGISTRY.is_valid("Agent") is True

    def test_health(self, registry):
        h = registry.health()
        assert h["alive"] is True
        assert h["registered_types"] == 10


class TestManifestValidation:
    @pytest.fixture
    def registry(self):
        return ArtifactTypeRegistry()

    def test_valid_agent_manifest(self, registry):
        manifest = {
            "name": "my-agent",
            "version": "1.0.0",
            "type": "Agent",
            "capabilities": ["analysis", "reporting"],
        }
        errors = registry.validate_manifest("Agent", manifest)
        assert errors == []

    def test_missing_required(self, registry):
        manifest = {"name": "my-agent"}
        errors = registry.validate_manifest("Agent", manifest)
        assert any("version" in e for e in errors)
        assert any("capabilities" in e for e in errors)

    def test_invalid_type_enum(self, registry):
        manifest = {
            "name": "bad",
            "version": "1.0.0",
            "type": "WrongType",
            "capabilities": [],
        }
        errors = registry.validate_manifest("Agent", manifest)
        assert any("type" in e and "WrongType" in e for e in errors)

    def test_version_pattern(self, registry):
        manifest = {
            "name": "bad-version",
            "version": "not-semver",
            "type": "Agent",
            "capabilities": [],
        }
        errors = registry.validate_manifest("Agent", manifest)
        assert any("version" in e for e in errors)

    def test_unknown_type(self, registry):
        errors = registry.validate_manifest("NoSuchType", {})
        assert len(errors) == 1
        assert "Unknown" in errors[0]

    def test_wrong_type_for_field(self, registry):
        manifest = {
            "name": "test",
            "version": "1.0.0",
            "type": "Agent",
            "capabilities": "not-an-array",
        }
        errors = registry.validate_manifest("Agent", manifest)
        assert any("capabilities" in e for e in errors)

    def test_tool_manifest_requires_tool_name(self, registry):
        manifest = {
            "name": "my-tool",
            "version": "1.0.0",
            "type": "Tool",
        }
        errors = registry.validate_manifest("Tool", manifest)
        assert any("tool_name" in e for e in errors)

    def test_valid_tool_manifest(self, registry):
        manifest = {
            "name": "git-tool",
            "version": "2.1.0",
            "type": "Tool",
            "tool_name": "git",
            "description": "Git integration",
        }
        errors = registry.validate_manifest("Tool", manifest)
        assert errors == []
