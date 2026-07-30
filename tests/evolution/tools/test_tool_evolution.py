from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.evolution.tools.tool_evolution import (
    CrossToolOptimization,
    CrossToolOptimizer,
    ToolEvolutionManager,
    ToolEvolutionResult,
)


class TestToolEvolutionResult:
    def test_to_dict(self):
        r = ToolEvolutionResult(
            evolution_id="e1", tool_name="python_tool",
            improvement_category="performance", patch_generated=True,
            benchmark_improvement=0.15, timestamp=100.0,
        )
        d = r.to_dict()
        assert d["evolution_id"] == "e1"
        assert d["benchmark_improvement"] == 0.15

    def test_to_dict_defaults(self):
        r = ToolEvolutionResult()
        d = r.to_dict()
        assert d["patch_generated"] is False


class TestCrossToolOptimization:
    def test_to_dict(self):
        o = CrossToolOptimization(
            optimization_id="o1", tools=["git", "file"],
            description="Optimize", expected_improvement=0.2,
            pattern="workflow",
        )
        d = o.to_dict()
        assert d["optimization_id"] == "o1"
        assert d["tools"] == ["git", "file"]


class TestToolEvolutionManager:
    @pytest.fixture
    def manager(self):
        return ToolEvolutionManager()

    def test_health(self, manager):
        h = manager.health()
        assert h["alive"] is True
        assert h["tools_tracked"] == 15

    def test_record_metric(self, manager):
        manager.record_tool_metric("python_tool", "avg_latency", 2.0)
        assert manager._tool_metrics["python_tool"]["avg_latency"] == 2.0

    def test_suggest_improvements_base(self, manager):
        suggestions = manager.suggest_improvements("python_tool")
        assert len(suggestions) >= 3

    def test_suggest_improvements_high_latency(self, manager):
        manager.record_tool_metric("slow_tool", "avg_latency", 5.0)
        suggestions = manager.suggest_improvements("slow_tool")
        categories = [s["category"] for s in suggestions]
        assert "latency" in categories

    def test_suggest_improvements_low_success(self, manager):
        manager.record_tool_metric("unreliable", "success_rate", 0.8)
        suggestions = manager.suggest_improvements("unreliable")
        categories = [s["category"] for s in suggestions]
        assert "reliability" in categories

    def test_evolve_tool(self, manager):
        result = manager.evolve_tool("python_tool")
        assert result.patch_generated is True
        assert result.tool_name == "python_tool"
        assert result.benchmark_improvement > 0

    def test_get_result(self, manager):
        result = manager.evolve_tool("git_tool")
        retrieved = manager.get_result(result.evolution_id)
        assert retrieved is not None
        assert retrieved.tool_name == "git_tool"

    def test_statistics(self, manager):
        manager.evolve_tool("python_tool")
        manager.evolve_tool("git_tool")
        stats = manager.get_statistics()
        assert stats["total_evolutions"] == 2
        assert stats["tools_evolved"] == 2

    def test_with_graph_store(self):
        mock_graph = MagicMock()
        manager = ToolEvolutionManager(graph_store=mock_graph)
        manager.evolve_tool("python_tool")
        assert mock_graph.create_entity.called

    def test_with_event_bus(self):
        mock_bus = MagicMock()
        manager = ToolEvolutionManager(event_bus=mock_bus)
        manager.evolve_tool("python_tool")
        assert mock_bus.publish.called


class TestCrossToolOptimizer:
    @pytest.fixture
    def optimizer(self):
        return CrossToolOptimizer()

    def test_health(self, optimizer):
        assert optimizer.health()["alive"] is True

    def test_record_sequence(self, optimizer):
        optimizer.record_tool_sequence(["git", "file", "python"])
        stats = optimizer.get_statistics()
        assert stats["total_patterns"] == 1

    def test_analyze_optimizations_base(self, optimizer):
        optimizations = optimizer.analyze_optimizations()
        assert len(optimizations) >= 3

    def test_analyze_optimizations_with_frequent(self, optimizer):
        for _ in range(5):
            optimizer.record_tool_sequence(["custom_a", "custom_b"])
        optimizations = optimizer.analyze_optimizations()
        assert len(optimizations) >= 4
        assert any("frequent_sequence" in o.pattern for o in optimizations)

    def test_statistics(self, optimizer):
        optimizer.record_tool_sequence(["a", "b"])
        optimizer.record_tool_sequence(["a", "b"])
        stats = optimizer.get_statistics()
        assert stats["total_occurrences"] == 2
