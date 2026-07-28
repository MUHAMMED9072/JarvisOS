from __future__ import annotations

from app.ads.capability_analysis import CapabilityAnalyzer
from app.ads.requirements import RequirementsAnalyzer
from app.knowledge_graph.store import GraphStore


class TestRequirementsAnalyzer:
    def test_detect_agent_type(self):
        ra = RequirementsAnalyzer()
        doc = ra.analyze("I need an agent that monitors servers")
        assert doc.artifact_type == "Agent"

    def test_detect_tool_type(self):
        ra = RequirementsAnalyzer()
        doc = ra.analyze("Build a tool for web scraping")
        assert doc.artifact_type == "Tool"

    def test_detect_plugin_type(self):
        ra = RequirementsAnalyzer()
        doc = ra.analyze("Create a plugin for slack integration")
        assert doc.artifact_type == "Plugin"

    def test_detect_skill_type(self):
        ra = RequirementsAnalyzer()
        doc = ra.analyze("I need a skill for data analysis")
        assert doc.artifact_type == "Skill"

    def test_detect_workflow_type(self):
        ra = RequirementsAnalyzer()
        doc = ra.analyze("Create a deployment workflow")
        assert doc.artifact_type == "Workflow"

    def test_detect_pipeline_type(self):
        ra = RequirementsAnalyzer()
        doc = ra.analyze("Build a data processing pipeline")
        assert doc.artifact_type == "Pipeline"

    def test_detect_knowledge_pack(self):
        ra = RequirementsAnalyzer()
        doc = ra.analyze("Create a knowledge pack about machine learning")
        assert doc.artifact_type == "KnowledgePack"

    def test_detect_test_suite(self):
        ra = RequirementsAnalyzer()
        doc = ra.analyze("Write a test suite for the API")
        assert doc.artifact_type == "TestSuite"

    def test_detect_integration(self):
        ra = RequirementsAnalyzer()
        doc = ra.analyze("Build an integration between GitHub and Jira")
        assert doc.artifact_type == "Integration"

    def test_detect_documentation(self):
        ra = RequirementsAnalyzer()
        doc = ra.analyze("Generate documentation for the API endpoints")
        assert doc.artifact_type == "Documentation"

    def test_detect_capabilities(self):
        ra = RequirementsAnalyzer()
        doc = ra.analyze("I need a web scraper that can extract and transform data")
        assert "web_scraping" in doc.capabilities_needed
        assert "data_extraction" in doc.capabilities_needed
        assert "data_transformation" in doc.capabilities_needed

    def test_detect_constraints(self):
        ra = RequirementsAnalyzer()
        doc = ra.analyze("The agent must use Python and must not access the network")
        assert len(doc.constraints) >= 1

    def test_ambiguity_detection(self):
        ra = RequirementsAnalyzer()
        doc = ra.analyze("I need something that does various things quickly")
        assert doc.is_ambiguous()
        assert len(doc.ambiguity_flags) >= 1

    def test_no_ambiguity_detected(self):
        ra = RequirementsAnalyzer()
        doc = ra.analyze("Create a web scraping agent with rate limiting and output to JSON")
        assert not doc.is_ambiguous()

    def test_name_extraction(self):
        ra = RequirementsAnalyzer()
        doc = ra.analyze("Create an agent called 'WebScraper' that scrapes websites")
        assert doc.name == "WebScraper"

    def test_default_name(self):
        ra = RequirementsAnalyzer()
        doc = ra.analyze("Create a monitoring tool")
        assert doc.name.startswith("tool_")

    def test_requirements_document_to_dict(self):
        ra = RequirementsAnalyzer()
        doc = ra.analyze("I need a web scraper tool")
        d = doc.to_dict()
        assert d["artifact_type"] == "Tool"
        assert "raw_request" in d
        assert "ambiguity_flags" in d

    def test_health(self):
        ra = RequirementsAnalyzer()
        h = ra.health()
        assert h["alive"] is True


class TestCapabilityAnalyzer:
    def test_without_graph_store(self):
        ca = CapabilityAnalyzer()
        ra = RequirementsAnalyzer()
        doc = ra.analyze("I need a web scraper")
        result = ca.analyze(doc)
        assert len(result.required_capabilities) >= 1
        # Without graph store, all required are considered existing

    def test_with_graph_store(self):
        g = GraphStore()
        g.clear()
        # Register a capability in KG
        g.create_entity(
            type="capability",
            name="web_scraping",
            properties={"description": "Web scraping capability"},
        )
        ca = CapabilityAnalyzer(graph_store=g)
        ra = RequirementsAnalyzer()
        doc = ra.analyze("I need a web scraper")
        result = ca.analyze(doc)
        assert "web_scraping" in result.required_capabilities
        assert "web_scraping" in result.existing_capabilities

    def test_missing_capability(self):
        g = GraphStore()
        g.clear()
        ca = CapabilityAnalyzer(graph_store=g)
        ra = RequirementsAnalyzer()
        doc = ra.analyze("Agent that translates text from English to French")
        result = ca.analyze(doc)
        assert "translation" in result.required_capabilities

    def test_capability_analysis_result_to_dict(self):
        from app.ads.capability_analysis import CapabilityAnalysisResult
        r = CapabilityAnalysisResult(
            required_capabilities=["a"],
            existing_capabilities=["a"],
        )
        d = r.to_dict()
        assert d["required_capabilities"] == ["a"]
        assert d["existing_capabilities"] == ["a"]

    def test_health(self):
        ca = CapabilityAnalyzer()
        h = ca.health()
        assert h["alive"] is True
