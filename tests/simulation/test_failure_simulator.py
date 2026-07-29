import pytest

from app.simulation.failure_simulator import (
    FailureSimulator,
    FailureImpactReport,
    CascadeAnalysis,
    DegradationAnalysis,
    RecoveryAnalysis,
    CascadeNode,
)
from app.knowledge_graph.store import GraphStore


class TestFailureSimulator:
    @pytest.fixture
    def graph(self):
        g = GraphStore()
        g.clear()
        return g

    @pytest.fixture
    def sim(self, graph):
        return FailureSimulator(graph_store=graph)

    def test_simulate_empty(self, sim):
        report = sim.simulate("EmptyAgent")
        assert report.artifact_name == "EmptyAgent"
        assert report.failure_impact_score == 0.0
        assert report.passed is True

    def test_simulate_with_entity_no_dependents(self, sim, graph):
        entity = graph.create_entity(type="concept", name="Standalone")
        report = sim.simulate("Standalone", "agent", entity_id=entity.id)
        assert report.cascade.total_affected == 0

    def test_cascade_single_level(self, sim, graph):
        entity = graph.create_entity(type="concept", name="Core")
        dep = graph.create_entity(type="concept", name="Dependent")
        graph.create_relationship(type="depends_on", source_id=dep.id, target_id=entity.id)
        report = sim.simulate("Core", "agent", entity_id=entity.id)
        assert report.cascade.total_affected >= 1

    def test_cascade_multi_level(self, sim, graph):
        core = graph.create_entity(type="concept", name="Core")
        mid = graph.create_entity(type="concept", name="Mid")
        leaf = graph.create_entity(type="concept", name="Leaf")
        graph.create_relationship(type="depends_on", source_id=mid.id, target_id=core.id)
        graph.create_relationship(type="depends_on", source_id=leaf.id, target_id=mid.id)
        report = sim.simulate("Core", "agent", entity_id=core.id)
        assert report.cascade.total_affected >= 2
        assert report.cascade.max_depth >= 1

    def test_cascade_depth(self, sim, graph):
        entities = []
        for i in range(5):
            e = graph.create_entity(type="concept", name=f"Level{i}")
            entities.append(e)
        for i in range(4, 0, -1):
            graph.create_relationship(type="depends_on", source_id=entities[i].id, target_id=entities[i - 1].id)
        report = sim.simulate("Root", "agent", entity_id=entities[0].id)
        assert report.cascade.max_depth >= 3

    def test_degradation_no_impact(self, sim):
        report = sim.simulate("SafeArtifact")
        assert report.degradation.can_operate_without is True
        assert report.degradation.degradation_score == 0.0

    def test_degradation_with_cascade(self, sim, graph):
        entity = graph.create_entity(type="concept", name="Core")
        for _ in range(3):
            dep = graph.create_entity(type="concept", name=f"Dep{_}")
            graph.create_relationship(type="depends_on", source_id=dep.id, target_id=entity.id)
        report = sim.simulate("Core", "agent", entity_id=entity.id)
        assert report.degradation.degradation_score > 0

    def test_recovery_no_impact(self, sim):
        report = sim.simulate("Recoverable")
        assert report.recovery.can_recover is True
        assert report.recovery.estimated_recovery_time == "immediate"

    def test_recovery_with_cascade(self, sim, graph):
        entity = graph.create_entity(type="concept", name="Core")
        dep = graph.create_entity(type="concept", name="Dep")
        graph.create_relationship(type="depends_on", source_id=dep.id, target_id=entity.id)
        report = sim.simulate("Core", "agent", entity_id=entity.id)
        assert len(report.recovery.recovery_steps) >= 1

    def test_failure_impact_score_no_impact(self, sim):
        report = sim.simulate("NoImpact")
        assert report.failure_impact_score == 0.0

    def test_failure_impact_score_with_cascade(self, sim, graph):
        entity = graph.create_entity(type="concept", name="Core")
        for _ in range(5):
            dep = graph.create_entity(type="concept", name=f"Dep{_}")
            graph.create_relationship(type="depends_on", source_id=dep.id, target_id=entity.id)
        report = sim.simulate("Core", "agent", entity_id=entity.id)
        assert report.failure_impact_score > 0

    def test_critical_system_high_score(self, sim, graph):
        entity = graph.create_entity(type="concept", name="SysCore")
        for _ in range(10):
            dep = graph.create_entity(type="concept", name=f"CriDep{_}")
            graph.create_relationship(type="depends_on", source_id=dep.id, target_id=entity.id)
        report = sim.simulate("SysCore", "system", entity_id=entity.id)
        assert report.cascade.cascade_score > 0.3

    def test_cascade_node_to_dict(self):
        cn = CascadeNode(entity_id="id1", entity_name="Test", entity_type="agent", depth=2, failure_probability=0.5)
        d = cn.to_dict()
        assert d["entity_name"] == "Test"

    def test_cascade_analysis_to_dict(self):
        ca = CascadeAnalysis(
            affected_entities=[CascadeNode(entity_id="id1", entity_name="A")],
            total_affected=1, max_depth=1, critical_affected=0, cascade_score=0.3,
        )
        d = ca.to_dict()
        assert d["total_affected"] == 1

    def test_degradation_analysis_to_dict(self):
        da = DegradationAnalysis(
            can_operate_without=False,
            degraded_capabilities=["cap1"],
            critical_functions_lost=["func1"],
            degradation_score=0.6,
        )
        d = da.to_dict()
        assert d["can_operate_without"] is False

    def test_recovery_analysis_to_dict(self):
        ra = RecoveryAnalysis(
            can_recover=True,
            recovery_steps=["step1"],
            estimated_recovery_time="< 1 min",
            recovery_score=0.2,
        )
        d = ra.to_dict()
        assert d["estimated_recovery_time"] == "< 1 min"

    def test_report_to_dict(self):
        report = FailureImpactReport(
            artifact_name="Test", artifact_type="agent",
            failure_impact_score=0.5, passed=True,
        )
        d = report.to_dict()
        assert d["failure_impact_score"] == 0.5

    def test_health(self, sim):
        h = sim.health()
        assert h["alive"] is True
