from __future__ import annotations

import pytest

from app.simulation.impact_estimator import (
    ImpactEstimator,
    ImpactEstimate,
    ResourceImpact,
)


class TestResourceImpact:
    def test_defaults(self):
        r = ResourceImpact()
        assert r.cpu == 0.0
        assert r.memory_mb == 0.0
        assert r.disk_mb == 0.0
        assert r.network == 0.0

    def test_to_dict(self):
        r = ResourceImpact(cpu=0.5, memory_mb=256, disk_mb=50, network=0.1)
        d = r.to_dict()
        assert d["cpu"] == 0.5
        assert d["memory_mb"] == 256


class TestImpactEstimate:
    def test_to_dict(self):
        e = ImpactEstimate(
            artifact_id="a1",
            artifact_type="agent",
            artifact_name="test-agent",
            direct=ResourceImpact(cpu=0.3, memory_mb=256),
            dependency_count=5,
        )
        d = e.to_dict()
        assert d["artifact_id"] == "a1"
        assert d["direct"]["cpu"] == 0.3
        assert d["dependency_count"] == 5


class TestImpactEstimator:
    def test_estimate_agent(self):
        est = ImpactEstimator()
        result = est.estimate("agent", "my-agent")
        assert result.artifact_type == "agent"
        assert result.artifact_name == "my-agent"
        assert result.direct.cpu == 0.3
        assert result.direct.memory_mb == 256
        assert result.direct.disk_mb == 50
        assert result.direct.network == 0.2
        assert result.transitive.cpu == 0.0
        assert result.total.cpu == 0.3

    def test_estimate_tool(self):
        est = ImpactEstimator()
        result = est.estimate("tool")
        assert result.direct.cpu == 0.1
        assert result.direct.memory_mb == 64

    def test_estimate_unknown_type(self):
        est = ImpactEstimator()
        result = est.estimate("unknown_type")
        assert result.direct.cpu == 0.1
        assert result.direct.memory_mb == 64

    def test_estimate_with_dependencies(self):
        est = ImpactEstimator()
        dep_tree = [
            {"entity_type": "tool", "entity_name": "tool1"},
            {"entity_type": "skill", "entity_name": "skill1"},
        ]
        result = est.estimate("agent", "my-agent", dep_tree)
        assert result.dependency_count == 2
        # tool: cpu=0.1, skill: cpu=0.2
        assert result.transitive.cpu == pytest.approx(0.3)
        assert result.total.cpu == pytest.approx(0.6)

    def test_estimate_with_nested_dependencies(self):
        est = ImpactEstimator()
        dep_tree = [
            {
                "entity_type": "tool",
                "entity_name": "tool1",
                "dependencies": [
                    {"entity_type": "file", "entity_name": "file1"},
                ],
            },
        ]
        result = est.estimate("agent", "my-agent", dep_tree)
        assert result.dependency_count == 1
        # tool: cpu=0.1, file: cpu=0.01
        assert result.transitive.cpu == 0.11

    def test_set_type_estimate(self):
        est = ImpactEstimator()
        est.set_type_estimate("custom_type", {"cpu": 0.5, "memory_mb": 512, "disk_mb": 100, "network": 0.3})
        result = est.estimate("custom_type")
        assert result.direct.cpu == 0.5
        assert result.direct.memory_mb == 512

    def test_get_base_impact_known(self):
        est = ImpactEstimator()
        impact = est.get_base_impact("agent")
        assert impact["cpu"] == 0.3

    def test_get_base_impact_unknown(self):
        est = ImpactEstimator()
        impact = est.get_base_impact("nonexistent")
        assert impact["cpu"] == 0.1

    def test_get_base_impact_custom(self):
        est = ImpactEstimator()
        est.set_type_estimate("custom", {"cpu": 0.9, "memory_mb": 1000, "disk_mb": 200, "network": 0.5})
        impact = est.get_base_impact("custom")
        assert impact["cpu"] == 0.9

    def test_confidence_known_type(self):
        est = ImpactEstimator()
        result = est.estimate("agent")
        assert result.confidence == 0.7

    def test_confidence_unknown_type(self):
        est = ImpactEstimator()
        result = est.estimate("unknown")
        assert result.confidence == 0.3

    def test_confidence_low_with_many_deps(self):
        est = ImpactEstimator()
        dep_tree = [{"entity_type": "tool"} for _ in range(30)]
        result = est.estimate("agent", "test", dep_tree)
        # 30 deps -> base * 0.7
        assert result.confidence == pytest.approx(0.49)

    def test_health(self):
        est = ImpactEstimator()
        h = est.health()
        assert h["alive"]

    def test_thread_safe(self):
        import threading
        est = ImpactEstimator()
        errors = []

        def estimate():
            try:
                for _ in range(50):
                    est.estimate("agent", "test")
                    est.get_base_impact("tool")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=estimate) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
