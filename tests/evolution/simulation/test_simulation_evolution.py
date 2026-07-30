from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.evolution.simulation.simulation_evolution import (
    SimulationEvolutionManager,
    SimulationImprovement,
)


class TestSimulationImprovement:
    def test_to_dict(self):
        imp = SimulationImprovement(
            improvement_id="i1", component="performance_modeler",
            description="Improve accuracy", current_accuracy=0.6,
            target_accuracy=0.85, patch_generated=True, timestamp=100.0,
        )
        d = imp.to_dict()
        assert d["improvement_id"] == "i1"
        assert d["patch_generated"] is True
        assert d["current_accuracy"] == 0.6

    def test_to_dict_defaults(self):
        imp = SimulationImprovement()
        d = imp.to_dict()
        assert d["patch_generated"] is False


class TestSimulationEvolutionManager:
    @pytest.fixture
    def manager(self):
        return SimulationEvolutionManager()

    def test_health(self, manager):
        h = manager.health()
        assert h["alive"] is True
        assert h["components_tracked"] == 7

    def test_record_accuracy(self, manager):
        manager.record_accuracy("performance_modeler", 100.0, 90.0)
        acc = manager.get_component_accuracy("performance_modeler")
        assert acc > 0.8

    def test_get_accuracy_no_data(self, manager):
        acc = manager.get_component_accuracy("nonexistent")
        assert acc == 0.0

    def test_record_accuracy_zero_estimate(self, manager):
        manager.record_accuracy("performance_modeler", 0.0, 50.0)
        acc = manager.get_component_accuracy("performance_modeler")
        assert acc == 0.0

    def test_record_multiple_accuracies(self, manager):
        manager.record_accuracy("performance_modeler", 100.0, 100.0)
        manager.record_accuracy("performance_modeler", 100.0, 80.0)
        acc = manager.get_component_accuracy("performance_modeler")
        assert 0.8 < acc < 1.0

    def test_suggest_improvements_low_accuracy(self, manager):
        for _ in range(3):
            manager.record_accuracy("performance_modeler", 100.0, 200.0)
        improvements = manager.suggest_improvements()
        comps = [i.component for i in improvements]
        assert "performance_modeler" in comps

    def test_suggest_improvements_new_components(self, manager):
        improvements = manager.suggest_improvements()
        # Some components without data should get suggestions
        assert len(improvements) >= 1

    def test_evolve_component(self, manager):
        result = manager.evolve_component("performance_modeler")
        assert result.patch_generated is True
        assert result.component == "performance_modeler"
        assert result.target_accuracy > result.current_accuracy

    def test_get_result(self, manager):
        result = manager.evolve_component("dependency_analyzer")
        retrieved = manager.get_result(result.improvement_id)
        assert retrieved is not None
        assert retrieved.component == "dependency_analyzer"

    def test_statistics(self, manager):
        manager.evolve_component("performance_modeler")
        manager.evolve_component("security_analyzer")
        stats = manager.get_statistics()
        assert stats["total_improvements"] == 2
        assert "component_accuracies" in stats

    def test_with_graph_store(self):
        mock_graph = MagicMock()
        manager = SimulationEvolutionManager(graph_store=mock_graph)
        manager.evolve_component("performance_modeler")
        assert mock_graph.create_entity.called

    def test_with_event_bus(self):
        mock_bus = MagicMock()
        manager = SimulationEvolutionManager(event_bus=mock_bus)
        manager.evolve_component("performance_modeler")
        assert mock_bus.publish.called
