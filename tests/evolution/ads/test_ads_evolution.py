from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.evolution.ads.improver import ADSStageImprover, StageImprovementResult
from app.evolution.ads.manager import ADSEvolutionManager
from app.evolution.ads.optimizer import ADSPipelineOptimizer, OptimizationPlan
from app.evolution.ads.scanner import ADSBottleneck, ADSEvolutionScanner
from app.evolution.ads.self_improve import SelfImprovementEngine, SelfImprovementResult


class TestADSBottleneck:
    def test_to_dict(self):
        b = ADSBottleneck(
            stage_name="test_generation", metric="avg_duration_ms",
            current_value=10000.0, suggested_value=5000.0,
            impact="high", description="Slow stage", suggestion="Optimize",
        )
        d = b.to_dict()
        assert d["stage_name"] == "test_generation"
        assert d["impact"] == "high"


class TestStageImprovementResult:
    def test_to_dict(self):
        r = StageImprovementResult(
            improvement_id="i1", stage_name="governance_check",
            applied=True, verified=True, timestamp=100.0,
        )
        d = r.to_dict()
        assert d["improvement_id"] == "i1"
        assert d["applied"] is True


class TestOptimizationPlan:
    def test_to_dict(self):
        p = OptimizationPlan(
            plan_id="p1", description="Optimize",
            stage_order=["a", "b"], parallel_stages=[["c", "d"]],
            estimated_improvement=0.3, applied=True,
        )
        d = p.to_dict()
        assert d["plan_id"] == "p1"
        assert d["estimated_improvement"] == 0.3


class TestSelfImprovementResult:
    def test_to_dict(self):
        r = SelfImprovementResult(
            improvement_id="si1", target="content_generator",
            description="Improve quality", patch_generated=True,
            verified=True, timestamp=100.0,
        )
        d = r.to_dict()
        assert d["improvement_id"] == "si1"
        assert d["patch_generated"] is True


class TestADSEvolutionScanner:
    @pytest.fixture
    def scanner(self):
        return ADSEvolutionScanner()

    def test_health(self, scanner):
        h = scanner.health()
        assert h["alive"] is True
        assert h["stages_tracked"] == 18

    def test_initial_no_bottlenecks(self, scanner):
        bottlenecks = scanner.scan_bottlenecks()
        assert bottlenecks == []

    def test_record_execution(self, scanner):
        scanner.record_execution("governance_check", 1000.0, True)
        stats = scanner.get_stage_statistics()
        assert "governance_check" in stats
        assert stats["governance_check"]["total_executions"] == 1

    def test_bottleneck_high_duration(self, scanner):
        scanner.record_execution("test_generation", 10000.0, True)
        scanner.record_execution("test_generation", 12000.0, True)
        scanner.record_execution("test_generation", 15000.0, True)
        bottlenecks = scanner.scan_bottlenecks()
        assert len(bottlenecks) >= 1
        assert bottlenecks[0].stage_name == "test_generation"
        assert bottlenecks[0].metric == "avg_duration_ms"

    def test_bottleneck_low_success_rate(self, scanner):
        for _ in range(3):
            scanner.record_execution("approval", 500.0, False)
        bottlenecks = scanner.scan_bottlenecks()
        assert len(bottlenecks) >= 1
        assert bottlenecks[0].metric == "success_rate"

    def test_bottleneck_insufficient_data(self, scanner):
        scanner.record_execution("approval", 1000.0, True)
        scanner.record_execution("approval", 1000.0, True)
        bottlenecks = scanner.scan_bottlenecks()
        approval_bottlenecks = [b for b in bottlenecks if b.stage_name == "approval"]
        assert len(approval_bottlenecks) == 0

    def test_statistics(self, scanner):
        scanner.record_execution("approval", 1000.0, True)
        scanner.record_execution("approval", 10000.0, True)
        scanner.record_execution("approval", 10000.0, False)
        stats = scanner.get_statistics()
        assert stats["total_executions"] == 3
        assert stats["stages_with_data"] == 1


class TestADSStageImprover:
    @pytest.fixture
    def improver(self):
        return ADSStageImprover()

    def test_health(self, improver):
        assert improver.health()["alive"] is True

    def test_improve_governance(self, improver):
        result = improver.improve_stage("governance_check", "Add evolution policies")
        assert result.applied is True
        assert result.stage_name == "governance_check"
        assert "ADDITIONAL_POLICIES" in result.patch_content

    def test_improve_sandbox(self, improver):
        result = improver.improve_stage("sandbox_execution", "Add blocking rules")
        assert result.applied is True
        assert "ADDITIONAL_BLOCKED_MODULES" in result.patch_content

    def test_improve_test_gen(self, improver):
        result = improver.improve_stage("test_generation", "Increase coverage")
        assert result.applied is True
        assert "COVERAGE_THRESHOLD" in result.patch_content

    def test_improve_unknown_stage(self, improver):
        result = improver.improve_stage("unknown_stage", "Test")
        assert result.applied is True
        assert "STAGE_CONFIG" in result.patch_content

    def test_get_result(self, improver):
        result = improver.improve_stage("approval", "Test")
        retrieved = improver.get_result(result.improvement_id)
        assert retrieved is not None
        assert retrieved.stage_name == "approval"

    def test_statistics(self, improver):
        improver.improve_stage("governance_check", "Test")
        improver.improve_stage("sandbox_execution", "Test")
        stats = improver.get_statistics()
        assert stats["total_improvements"] == 2
        assert stats["stages_improved"] == 2

    def test_with_verify_hook(self):
        verify = MagicMock()
        verify.return_value = True
        improver = ADSStageImprover(verify_hook=verify)
        result = improver.improve_stage("governance_check", "Test")
        assert result.verified is True
        verify.assert_called_once_with(result.improvement_id)


class TestADSPipelineOptimizer:
    @pytest.fixture
    def optimizer(self):
        return ADSPipelineOptimizer()

    def test_health(self, optimizer):
        assert optimizer.health()["alive"] is True

    def test_suggest_parallelization(self, optimizer):
        suggestions = optimizer.suggest_parallelization()
        assert len(suggestions) >= 1

    def test_suggest_skip_conditions(self, optimizer):
        conditions = optimizer.suggest_skip_conditions()
        assert "simulation" in conditions

    def test_create_optimization_plan(self, optimizer):
        plan = optimizer.create_optimization_plan()
        assert plan.plan_id is not None
        assert plan.estimated_improvement > 0

    def test_apply_plan(self, optimizer):
        plan = optimizer.create_optimization_plan()
        assert optimizer.apply_plan(plan.plan_id) is True

    def test_apply_nonexistent(self, optimizer):
        assert optimizer.apply_plan("no-such-plan") is False

    def test_get_plan(self, optimizer):
        plan = optimizer.create_optimization_plan()
        retrieved = optimizer.get_plan(plan.plan_id)
        assert retrieved is not None
        assert retrieved.plan_id == plan.plan_id

    def test_statistics(self, optimizer):
        optimizer.create_optimization_plan()
        stats = optimizer.get_statistics()
        assert stats["total_plans"] >= 1


class TestSelfImprovementEngine:
    @pytest.fixture
    def engine(self):
        return SelfImprovementEngine()

    def test_health(self, engine):
        assert engine.health()["alive"] is True

    def test_improve_code_generation(self, engine):
        result = engine.improve_code_generation()
        assert result.patch_generated is True
        assert result.target == "content_generator"

    def test_improve_test_generation(self, engine):
        result = engine.improve_test_generation()
        assert result.patch_generated is True
        assert result.target == "test_generator"

    def test_improve_architecture_design(self, engine):
        result = engine.improve_architecture_design()
        assert result.patch_generated is True
        assert "architecture" in result.target

    def test_get_result(self, engine):
        result = engine.improve_code_generation()
        retrieved = engine.get_result(result.improvement_id)
        assert retrieved is not None

    def test_statistics(self, engine):
        engine.improve_code_generation()
        engine.improve_test_generation()
        stats = engine.get_statistics()
        assert stats["total_improvements"] == 2
        assert stats["by_target"]["content_generator"] == 1
        assert stats["by_target"]["test_generator"] == 1


class TestADSEvolutionManager:
    @pytest.fixture
    def manager(self):
        return ADSEvolutionManager()

    def test_health(self, manager):
        h = manager.health()
        assert h["alive"] is True

    def test_scan(self, manager):
        bottlenecks = manager.scan()
        assert isinstance(bottlenecks, list)

    def test_record_execution(self, manager):
        manager.record_execution("approval", 1000.0, True)
        stats = manager._scanner.get_statistics()
        assert stats["total_executions"] == 1

    def test_improve_stage(self, manager):
        result = manager.improve_stage("governance_check")
        assert result.applied is True

    def test_optimize_pipeline(self, manager):
        plan = manager.optimize_pipeline()
        assert plan.applied is True

    def test_self_improve(self, manager):
        result = manager.self_improve("content_generator")
        assert result.patch_generated is True

    def test_statistics(self, manager):
        stats = manager.get_statistics()
        assert "bottlenecks_found" in stats

    def test_with_graph_store(self):
        mock_graph = MagicMock()
        manager = ADSEvolutionManager(graph_store=mock_graph)
        manager.improve_stage("governance_check")
        assert mock_graph.create_entity.called

    def test_with_event_bus(self):
        mock_bus = MagicMock()
        manager = ADSEvolutionManager(event_bus=mock_bus)
        manager.optimize_pipeline()
        assert mock_bus.publish.called
