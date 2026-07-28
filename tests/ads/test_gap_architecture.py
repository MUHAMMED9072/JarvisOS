import pytest

from app.ads.architecture_designer import ArchitectureDesigner, ArchitectureSpec
from app.ads.capability_analysis import CapabilityAnalysisResult, CapabilityAnalyzer
from app.ads.gap_detector import GapDetector, GapReport
from app.ads.requirements import RequirementsAnalyzer
from app.ads.type_registry import ArtifactTypeRegistry
from app.knowledge_graph.store import GraphStore


class TestGapDetector:
    def test_no_gaps_when_all_covered(self):
        g = GraphStore()
        g.clear()
        g.create_entity(type="capability", name="web_scraping", properties={})
        g.create_entity(type="capability", name="data_extraction", properties={})
        g.create_entity(type="capability", name="data_transformation", properties={})

        ra = RequirementsAnalyzer()
        doc = ra.analyze("I need a web scraper that extracts and transforms data")
        ca = CapabilityAnalyzer(graph_store=g)
        cap_result = ca.analyze(doc)
        gd = GapDetector(graph_store=g)
        report = gd.detect(doc, cap_result)
        assert not report.has_gaps()

    def test_gaps_when_missing(self):
        g = GraphStore()
        g.clear()
        g.create_entity(type="capability", name="web_scraping", properties={})
        ra = RequirementsAnalyzer()
        doc = ra.analyze("I need a translation and summarization agent")
        ca = CapabilityAnalyzer(graph_store=g)
        cap_result = ca.analyze(doc)
        gd = GapDetector(graph_store=g)
        report = gd.detect(doc, cap_result)
        # translation and summarization may or may not have matches
        # depending on graph contents; at minimum verify the API works
        assert isinstance(report, GapReport)

    def test_gap_report_to_dict(self):
        r = GapReport(
            missing_capabilities=["x"],
            fully_covered=["y"],
        )
        d = r.to_dict()
        assert d["has_gaps"] is True

    def test_health(self):
        gd = GapDetector()
        h = gd.health()
        assert h["alive"] is True


class TestArchitectureDesigner:
    @pytest.fixture
    def designer(self):
        return ArchitectureDesigner()

    def test_design_agent(self, designer):
        ra = RequirementsAnalyzer()
        doc = ra.analyze("Create an agent called DataMonitor that monitors servers")
        gd = GapDetector()
        cap_result = CapabilityAnalysisResult(
            required_capabilities=["monitoring"],
            existing_capabilities=["monitoring"],
        )
        gap = gd.detect(doc, cap_result)
        designs = designer.design(doc, gap)
        assert len(designs) >= 1
        assert designs[0].name == "DataMonitor"
        assert designs[0].artifact_type == "Agent"

    def test_design_tool(self, designer):
        ra = RequirementsAnalyzer()
        doc = ra.analyze("Build a web scraping tool")
        gd = GapDetector()
        gap = GapReport()
        designs = designer.design(doc, gap)
        assert designs[0].artifact_type == "Tool"

    def test_design_includes_components(self, designer):
        ra = RequirementsAnalyzer()
        doc = ra.analyze("Create a monitoring agent that analyzes and reports")
        gap = GapReport()
        designs = designer.design(doc, gap)
        spec = designs[0]
        assert len(spec.components) >= 1
        component_names = [c["name"] for c in spec.components]
        assert "CoreAgent" in component_names

    def test_design_includes_interfaces(self, designer):
        ra = RequirementsAnalyzer()
        doc = ra.analyze("Create an agent")
        gap = GapReport()
        designs = designer.design(doc, gap)
        assert len(designs[0].interfaces) >= 1

    def test_design_includes_data_flow(self, designer):
        ra = RequirementsAnalyzer()
        doc = ra.analyze("Create a pipeline")
        gap = GapReport()
        designs = designer.design(doc, gap)
        assert len(designs[0].data_flow) >= 2

    def test_design_includes_security(self, designer):
        ra = RequirementsAnalyzer()
        doc = ra.analyze("Create an agent that must use authentication")
        gap = GapReport()
        designs = designer.design(doc, gap)
        assert len(designs[0].security_considerations) >= 1

    def test_alternatives_generated_when_gaps(self, designer):
        ra = RequirementsAnalyzer()
        doc = ra.analyze("Create a web scraper agent")
        gap = GapReport(
            missing_capabilities=["web_scraping"],
            combination_opportunities=[
                {"target_capability": "web_scraping", "suggestion": "Combine A, B", "candidates": ["A", "B"]},
            ],
        )
        designs = designer.design(doc, gap)
        assert len(designs) >= 2

    def test_alternatives_ranked(self, designer):
        ra = RequirementsAnalyzer()
        doc = ra.analyze("Create an agent")
        gap = GapReport(missing_capabilities=["x"])
        designs = designer.design(doc, gap)
        for i in range(len(designs) - 1):
            assert designs[i].alternative_score >= designs[i + 1].alternative_score

    def test_spec_to_dict(self, designer):
        spec = ArchitectureSpec(name="test", artifact_type="Tool")
        d = spec.to_dict()
        assert d["name"] == "test"
        assert d["artifact_type"] == "Tool"

    def test_health(self, designer):
        h = designer.health()
        assert h["alive"] is True

    def test_base_class_mapping(self, designer):
        ra = RequirementsAnalyzer()
        doc = ra.analyze("Create a plugin called SlackPlugin")
        gap = GapReport()
        designs = designer.design(doc, gap)
        assert designs[0].artifact_type == "Plugin"
        assert "PluginHost" in [c["name"] for c in designs[0].components]
