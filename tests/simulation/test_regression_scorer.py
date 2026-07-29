import pytest

from app.simulation.regression_scorer import (
    RegressionScorer,
    RegressionRiskReport,
    DependencyDepthAnalysis,
    ScopeAnalysis,
    HistoricalMatch,
)
from app.knowledge_graph.store import GraphStore


class TestRegressionScorer:
    @pytest.fixture
    def graph(self):
        g = GraphStore()
        g.clear()
        return g

    @pytest.fixture
    def scorer(self, graph):
        return RegressionScorer(graph_store=graph)

    def test_score_empty(self, scorer):
        report = scorer.score("EmptyAgent", "agent")
        assert report.artifact_name == "EmptyAgent"
        assert report.risk_score == 0.0
        assert report.passed is True

    def test_score_with_dependencies_shallow(self, scorer):
        deps = [
            {"entity_id": "dep1", "entity_type": "tool", "depth": 1},
            {"entity_id": "dep2", "entity_type": "library", "depth": 1},
        ]
        report = scorer.score("ShallowAgent", "agent", dependencies=deps)
        assert report.risk_score <= 0.5

    def test_score_with_dependencies_deep(self, scorer):
        deps = [
            {"entity_id": "a", "dependencies": [
                {"entity_id": "b", "dependencies": [
                    {"entity_id": "c", "dependencies": [
                        {"entity_id": "d"},
                    ]},
                ]},
            ]},
        ]
        report = scorer.score("DeepAgent", "agent", dependencies=deps)
        assert report.dependency_depth.max_depth >= 4
        assert report.risk_score > 0

    def test_score_with_many_dependencies(self, scorer):
        deps = [{"entity_id": f"dep{i}", "depth": 1} for i in range(25)]
        report = scorer.score("ManyAgent", "agent", dependencies=deps)
        assert report.dependency_depth.total_dependencies >= 25

    def test_scope_analysis_affected_entities(self, scorer, graph):
        entity = graph.create_entity(type="agent", name="TargetAgent")
        consumer = graph.create_entity(type="tool", name="ConsumerTool")
        graph.create_relationship(type="depends_on", source_id=consumer.id, target_id=entity.id)
        report = scorer.score("TargetAgent", "agent", entity_id=entity.id)
        assert report.scope.affected_entities >= 1

    def test_scope_analysis_multiple_types(self, scorer, graph):
        entity = graph.create_entity(type="agent", name="MultiAgent")
        for i in range(3):
            t = graph.create_entity(type="tool" if i % 2 == 0 else "skill", name=f"Consumer{i}")
            graph.create_relationship(type="depends_on", source_id=t.id, target_id=entity.id)
        report = scorer.score("MultiAgent", "agent", entity_id=entity.id)
        assert len(report.scope.affected_types) >= 1

    def test_historical_matches(self, scorer):
        scorer.record_regression("AgentA", "agent", caused_regression=True)
        scorer.record_regression("AgentB", "agent", caused_regression=False)
        report = scorer.score("NewAgent", "agent")
        assert len(report.historical_matches) >= 1

    def test_historical_match_score(self, scorer):
        scorer.record_regression("BrokenAgent", "agent", caused_regression=True)
        report = scorer.score("TestAgent", "agent")
        any_positive = any(m.score > 0 for m in report.historical_matches)
        assert any_positive

    def test_record_regression(self, scorer):
        scorer.record_regression("AgentX", "agent", caused_regression=True)
        history = scorer.get_history()
        assert len(history) >= 1
        assert history[0]["regression_count"] >= 1

    def test_record_regression_no_regression(self, scorer):
        scorer.record_regression("AgentY", "tool", caused_regression=False)
        history = scorer.get_history()
        assert history[0]["regression_count"] == 0

    def test_get_history_empty(self, scorer):
        assert scorer.get_history() == []

    def test_score_system_type_high_risk(self, scorer, graph):
        entity = graph.create_entity(type="concept", name="CoreModule")
        consumer = graph.create_entity(type="concept", name="KernelDep")
        graph.create_relationship(type="depends_on", source_id=consumer.id, target_id=entity.id)
        report = scorer.score("CoreModule", "system", entity_id=entity.id)
        assert report.scope.scope_score >= 0.9

    def test_score_unknown_type_low_base(self, scorer, graph):
        entity = graph.create_entity(type="concept", name="UnknownEntity")
        consumer = graph.create_entity(type="concept", name="Consumer")
        graph.create_relationship(type="depends_on", source_id=consumer.id, target_id=entity.id)
        report = scorer.score("Unknown", "unknown", entity_id=entity.id)
        assert report.scope.scope_score == 0.4

    def test_dependency_depth_to_dict(self):
        dd = DependencyDepthAnalysis(max_depth=5, avg_depth=2.5, total_dependencies=10, depth_score=0.4)
        d = dd.to_dict()
        assert d["max_depth"] == 5

    def test_scope_analysis_to_dict(self):
        sa = ScopeAnalysis(affected_entities=3, affected_types={"tool": 2, "skill": 1}, scope_score=0.5)
        d = sa.to_dict()
        assert d["affected_entities"] == 3

    def test_historical_match_to_dict(self):
        hm = HistoricalMatch(pattern="agent", match_count=10, regression_count=2, regression_rate=0.2, score=0.3)
        d = hm.to_dict()
        assert d["regression_rate"] == 0.2

    def test_report_to_dict(self):
        report = RegressionRiskReport(artifact_name="Test", artifact_type="agent", risk_score=0.5, passed=True)
        d = report.to_dict()
        assert d["risk_score"] == 0.5

    def test_health(self, scorer):
        h = scorer.health()
        assert h["alive"] is True

    def test_health_with_history(self, scorer):
        scorer.record_regression("A", "agent", True)
        h = scorer.health()
        assert h["historical_entries"] >= 1
