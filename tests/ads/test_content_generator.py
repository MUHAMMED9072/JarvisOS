import json

import pytest

from app.ads.architecture_designer import ArchitectureSpec
from app.ads.content_generator import ContentGenerator
from app.ads.requirements import RequirementsAnalyzer
from app.ads.gap_detector import GapDetector, GapReport
from app.ads.capability_analysis import CapabilityAnalysisResult
from app.ads.type_registry import ArtifactTypeRegistry


def _make_spec(name: str, atype: str, description: str = "") -> ArchitectureSpec:
    return ArchitectureSpec(
        name=name,
        artifact_type=atype,
        description=description or f"A {atype.lower()} called {name}",
        components=[
            {"name": f"Main{atype}", "type": "primary"},
        ],
        interfaces=[{"name": f"{name}_api", "component": f"Main{atype}", "methods": ["execute"]}],
        data_flow=[
            {"from": "input", "to": f"Main{atype}", "description": "Request enters"},
            {"from": f"Main{atype}", "to": "output", "description": "Result returned"},
        ],
        security_considerations=["Input validation required"],
    )


class TestContentGenerator:
    @pytest.fixture
    def generator(self):
        return ContentGenerator(output_dir="test_ads_output")

    def test_generate_agent(self, generator):
        spec = _make_spec("DataMonitor", "Agent")
        content = generator.generate(spec)
        assert f"{spec.name}.py" in content.files
        assert "DataMonitor" in content.files[f"{spec.name}.py"]

    def test_generate_tool(self, generator):
        spec = _make_spec("WebScraper", "Tool")
        content = generator.generate(spec)
        assert f"{spec.name}.py" in content.files

    def test_generate_plugin(self, generator):
        spec = _make_spec("SlackPlugin", "Plugin")
        content = generator.generate(spec)
        assert f"{spec.name}.py" in content.files

    def test_generate_skill(self, generator):
        spec = _make_spec("DataAnalysisSkill", "Skill")
        content = generator.generate(spec)
        assert f"{spec.name}.py" in content.files

    def test_generate_workflow(self, generator):
        spec = _make_spec("DeployWorkflow", "Workflow")
        content = generator.generate(spec)
        assert f"{spec.name}.yaml" in content.files
        assert "name: DeployWorkflow" in content.files[f"{spec.name}.yaml"]

    def test_generate_pipeline(self, generator):
        spec = _make_spec("DataPipeline", "Pipeline")
        content = generator.generate(spec)
        assert f"{spec.name}.yaml" in content.files

    def test_generate_knowledge_pack(self, generator):
        spec = _make_spec("MLKnowledge", "KnowledgePack")
        content = generator.generate(spec)
        assert f"{spec.name}.json" in content.files
        data = json.loads(content.files[f"{spec.name}.json"])
        assert data["name"] == "MLKnowledge"

    def test_generate_test_suite(self, generator):
        spec = _make_spec("APITests", "TestSuite")
        content = generator.generate(spec)
        assert content.files.get(f"test_{spec.name}.py") is not None

    def test_generate_integration(self, generator):
        spec = _make_spec("GitHubJira", "Integration")
        content = generator.generate(spec)
        assert f"{spec.name}.py" in content.files

    def test_generate_documentation(self, generator):
        spec = _make_spec("API Docs", "Documentation")
        content = generator.generate(spec)
        assert f"{spec.name}.md" in content.files

    def test_generated_content_has_init(self, generator):
        spec = _make_spec("MyAgent", "Agent")
        content = generator.generate(spec)
        assert "__init__.py" in content.files

    def test_generated_manifest(self, generator):
        spec = _make_spec("TestAgent", "Agent")
        content = generator.generate(spec)
        assert content.manifest["name"] == "TestAgent"
        assert content.manifest["version"] == "1.0.0"
        assert content.manifest["type"] == "Agent"

    def test_generate_all_types_have_templates(self):
        registry = ArtifactTypeRegistry()
        generator = ContentGenerator()
        for type_name in registry.list_types():
            if type_name in generator.TEMPLATES:
                spec = _make_spec(f"Test{type_name}", type_name)
                content = generator.generate(spec)
                assert len(content.files) >= 1, f"Failed for {type_name}"

    def test_write_content(self, generator, tmp_path):
        import tempfile
        import os
        generator._output_dir = tmp_path
        spec = _make_spec("TestWrite", "Agent")
        content = generator.generate(spec)
        base = generator.write(content)
        assert (base / f"{spec.name}.py").exists()
        assert (base / "manifest.json").exists()
        # Clean up
        import shutil
        shutil.rmtree(base, ignore_errors=True)

    def test_health(self, generator):
        h = generator.health()
        assert h["alive"] is True
