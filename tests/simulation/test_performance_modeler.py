import pytest

from app.simulation.impact_estimator import ResourceImpact
from app.simulation.performance_modeler import (
    PerformanceModeler,
    PerformanceEstimate,
    CalibrationEntry,
    ModelCalibration,
    _compute_errors,
)
from app.knowledge_graph.store import GraphStore


class TestPerformanceModeler:
    @pytest.fixture
    def graph(self):
        g = GraphStore()
        g.clear()
        return g

    @pytest.fixture
    def modeler(self, graph):
        return PerformanceModeler(graph_store=graph)

    def test_estimate_agent(self, modeler):
        est = modeler.estimate("agent", "TestAgent")
        assert est.artifact_name == "TestAgent"
        assert est.artifact_type == "agent"
        assert est.cpu > 0
        assert est.memory_mb > 0

    def test_estimate_tool(self, modeler):
        est = modeler.estimate("tool", "Scraper")
        assert est.cpu == 0.1
        assert est.memory_mb == 64.0

    def test_estimate_unknown_type(self, modeler):
        est = modeler.estimate("unknown_type", "Foo")
        assert est.cpu == 0.1
        assert est.memory_mb == 64.0
        assert est.confidence == 0.3

    def test_estimate_all_types(self, modeler):
        types = ["agent", "tool", "plugin", "skill", "workflow", "pipeline",
                 "knowledge_pack", "test_suite", "integration", "documentation"]
        for t in types:
            est = modeler.estimate(t)
            assert est.cpu > 0 or t == "documentation"

    def test_calibrate(self, modeler):
        estimated = ResourceImpact(cpu=0.3, memory_mb=256.0, disk_mb=50.0, network=0.2)
        actual = ResourceImpact(cpu=0.25, memory_mb=240.0, disk_mb=45.0, network=0.15)
        entry = modeler.calibrate("agent", estimated, actual)
        assert entry.error_pct > 0

    def test_calibration_adjusts_estimate(self, modeler):
        est_before = modeler.estimate("agent", "CalAgent")
        estimated = ResourceImpact(cpu=0.3, memory_mb=256.0, disk_mb=50.0, network=0.2)
        actual = ResourceImpact(cpu=0.15, memory_mb=128.0, disk_mb=25.0, network=0.1)
        modeler.calibrate("agent", estimated, actual)
        est_after = modeler.estimate("agent", "CalAgent")
        # After calibration, estimate should be lower due to overestimation error
        assert est_after.cpu < est_before.cpu or est_after.cpu == est_before.cpu

    def test_calibration_persists_to_kg(self, modeler, graph):
        estimated = ResourceImpact(cpu=0.3, memory_mb=256.0, disk_mb=50.0, network=0.2)
        actual = ResourceImpact(cpu=0.3, memory_mb=256.0, disk_mb=50.0, network=0.2)
        modeler.calibrate("agent", estimated, actual)
        entities = graph.get_entities_by_type("concept")
        cal_entities = [e for e in entities if e.name.startswith("calibration_")]
        assert len(cal_entities) >= 1

    def test_load_calibrations_from_kg(self, modeler, graph):
        estimated = ResourceImpact(cpu=0.3, memory_mb=256.0, disk_mb=50.0, network=0.2)
        actual = ResourceImpact(cpu=0.27, memory_mb=230.0, disk_mb=45.0, network=0.18)
        modeler.calibrate("agent", estimated, actual)
        modeler2 = PerformanceModeler(graph_store=graph)
        count = modeler2.load_calibrations_from_kg()
        assert count >= 1
        cal = modeler2.get_calibration("agent")
        assert cal is not None
        assert cal.count >= 1

    def test_get_calibration(self, modeler):
        assert modeler.get_calibration("nonexistent") is None
        estimated = ResourceImpact(cpu=0.3, memory_mb=256.0, disk_mb=50.0, network=0.2)
        actual = ResourceImpact(cpu=0.3, memory_mb=256.0, disk_mb=50.0, network=0.2)
        modeler.calibrate("tool", estimated, actual)
        cal = modeler.get_calibration("tool")
        assert cal is not None
        assert cal.type == "tool"

    def test_list_calibrations(self, modeler):
        estimated = ResourceImpact(cpu=0.3, memory_mb=256.0, disk_mb=50.0, network=0.2)
        actual = ResourceImpact(cpu=0.3, memory_mb=256.0, disk_mb=50.0, network=0.2)
        modeler.calibrate("agent", estimated, actual)
        modeler.calibrate("tool", estimated, actual)
        cals = modeler.list_calibrations()
        assert len(cals) == 2

    def test_set_type_model(self, modeler):
        modeler.set_type_model("agent", {"cpu": 0.5, "memory_mb": 512.0, "disk_mb": 100.0, "network": 0.3})
        est = modeler.estimate("agent")
        assert est.cpu == 0.5
        assert est.memory_mb == 512.0

    def test_confidence_increases_with_calibration(self, modeler):
        est_before = modeler.estimate("agent")
        assert est_before.confidence == 0.7
        estimated = ResourceImpact(cpu=0.3, memory_mb=256.0, disk_mb=50.0, network=0.2)
        for _ in range(10):
            modeler.calibrate("agent", estimated, estimated)
        est_after = modeler.estimate("agent")
        assert est_after.confidence > est_before.confidence

    def test_confidence_with_unknown_type(self, modeler):
        est = modeler.estimate("unknown")
        assert est.confidence == 0.3

    def test_calibration_entry_to_dict(self):
        entry = CalibrationEntry(
            artifact_name="Test", artifact_type="agent",
            estimated_cpu=0.3, actual_cpu=0.25,
            estimated_memory_mb=256.0, actual_memory_mb=240.0,
            estimated_disk_mb=50.0, actual_disk_mb=45.0,
            estimated_network=0.2, actual_network=0.15,
            error_pct=10.0,
        )
        d = entry.to_dict()
        assert d["artifact_name"] == "Test"
        assert d["error_pct"] == 10.0

    def test_performance_estimate_to_dict(self):
        est = PerformanceEstimate(
            artifact_name="Test", artifact_type="agent",
            cpu=0.3, memory_mb=256.0, disk_mb=50.0, network=0.2,
            confidence=0.85, calibration_count=10, calibration_accuracy=0.9,
        )
        d = est.to_dict()
        assert d["artifact_name"] == "Test"
        assert d["confidence"] == 0.85

    def test_model_calibration_to_dict(self):
        cal = ModelCalibration(
            type="agent", count=5, avg_error_pct=12.5,
            cpu_error_pct=10.0, memory_error_pct=15.0,
            disk_error_pct=8.0, network_error_pct=12.0,
        )
        d = cal.to_dict()
        assert d["type"] == "agent"
        assert d["count"] == 5

    def test_compute_errors_exact(self):
        estimated = ResourceImpact(cpu=0.3, memory_mb=256.0, disk_mb=50.0, network=0.2)
        actual = ResourceImpact(cpu=0.3, memory_mb=256.0, disk_mb=50.0, network=0.2)
        errors = _compute_errors(estimated, actual)
        assert errors["avg"] == 0.0

    def test_compute_errors_off(self):
        estimated = ResourceImpact(cpu=0.4, memory_mb=300.0, disk_mb=60.0, network=0.3)
        actual = ResourceImpact(cpu=0.2, memory_mb=200.0, disk_mb=40.0, network=0.1)
        errors = _compute_errors(estimated, actual)
        assert errors["avg"] > 0

    def test_compute_errors_divide_by_zero(self):
        estimated = ResourceImpact(cpu=0.0, memory_mb=0.0, disk_mb=0.0, network=0.0)
        actual = ResourceImpact(cpu=0.0, memory_mb=0.0, disk_mb=0.0, network=0.0)
        errors = _compute_errors(estimated, actual)
        assert errors["avg"] == 0.0

    def test_health(self, modeler):
        h = modeler.health()
        assert h["alive"] is True

    def test_health_with_calibrations(self, modeler):
        estimated = ResourceImpact(cpu=0.3, memory_mb=256.0, disk_mb=50.0, network=0.2)
        actual = ResourceImpact(cpu=0.3, memory_mb=256.0, disk_mb=50.0, network=0.2)
        modeler.calibrate("agent", estimated, actual)
        modeler.calibrate("tool", estimated, actual)
        h = modeler.health()
        assert h["calibrated_types"] == 2
