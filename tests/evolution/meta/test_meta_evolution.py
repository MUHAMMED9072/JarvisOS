from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.evolution.meta.analyzer import AnalysisResult, MetaEvolutionAnalyzer
from app.evolution.meta.improver import ImprovementPlan, MetaImprovementEngine
from app.evolution.meta.manager import MetaEvolutionManager, MetaEvolutionResult
from app.evolution.meta.scorer import MetaQualityScorer, QualityScore
from app.evolution.meta.strategy import (
    EvolutionStrategy,
    MetaStrategySelector,
    PREDEFINED_STRATEGIES,
)


class TestAnalysisResult:
    def test_to_dict(self):
        r = AnalysisResult(
            analysis_id="a1", target_area="system_evolution",
            issues_found=2, improvement_potential=0.6,
            details=[{"severity": "high", "description": "test"}],
            timestamp=100.0,
        )
        d = r.to_dict()
        assert d["issues_found"] == 2
        assert d["details"][0]["severity"] == "high"

    def test_to_dict_defaults(self):
        r = AnalysisResult()
        d = r.to_dict()
        assert d["issues_found"] == 0


class TestMetaEvolutionAnalyzer:
    @pytest.fixture
    def analyzer(self):
        return MetaEvolutionAnalyzer()

    def test_health(self, analyzer):
        assert analyzer.health()["alive"] is True

    def test_analyze_area_no_metrics(self, analyzer):
        result = analyzer.analyze_area("system_evolution")
        assert result.target_area == "system_evolution"
        assert result.issues_found >= 0
        assert result.improvement_potential >= 0.0

    def test_analyze_area_low_success_rate(self, analyzer):
        analyzer.record_metric("system_evolution", "patch_success_rate", 0.3)
        result = analyzer.analyze_area("system_evolution")
        assert result.issues_found > 0
        sevs = [d["severity"] for d in result.details]
        assert "high" in sevs

    def test_analyze_area_high_iterations(self, analyzer):
        analyzer.record_metric("system_evolution", "avg_iterations", 15)
        result = analyzer.analyze_area("system_evolution")
        assert result.issues_found > 0

    def test_analyze_area_high_test_failure(self, analyzer):
        analyzer.record_metric("system_evolution", "test_failure_rate", 0.5)
        result = analyzer.analyze_area("system_evolution")
        assert result.issues_found > 0

    def test_analyze_area_high_rollback(self, analyzer):
        analyzer.record_metric("system_evolution", "rollback_rate", 0.8)
        result = analyzer.analyze_area("system_evolution")
        sevs = [d["severity"] for d in result.details]
        assert "critical" in sevs

    def test_analyze_all(self, analyzer):
        results = analyzer.analyze_all()
        assert len(results) == 6
        areas = [r.target_area for r in results]
        assert "system_evolution" in areas

    def test_get_result(self, analyzer):
        result = analyzer.analyze_area("system_evolution")
        retrieved = analyzer.get_result(result.analysis_id)
        assert retrieved is not None
        assert retrieved.target_area == "system_evolution"

    def test_statistics(self, analyzer):
        analyzer.analyze_area("system_evolution")
        stats = analyzer.get_statistics()
        assert stats["total_analyses"] == 1


class TestImprovementPlan:
    def test_to_dict(self):
        p = ImprovementPlan(
            plan_id="p1", target_area="system_evolution",
            changes=["Fix issue A"], expected_gain=0.5,
            risk_score=0.3, timestamp=100.0,
        )
        d = p.to_dict()
        assert d["changes"] == ["Fix issue A"]
        assert d["expected_gain"] == 0.5

    def test_to_dict_defaults(self):
        p = ImprovementPlan()
        d = p.to_dict()
        assert d["changes"] == []


class TestMetaImprovementEngine:
    @pytest.fixture
    def engine(self):
        return MetaImprovementEngine()

    def test_health(self, engine):
        assert engine.health()["alive"] is True

    def test_generate_plan_no_issues(self, engine):
        analysis = AnalysisResult(
            target_area="system_evolution",
            improvement_potential=0.1,
        )
        plan = engine.generate_plan(analysis)
        assert plan.target_area == "system_evolution"
        assert any("No critical issues" in c for c in plan.changes)

    def test_generate_plan_with_issues(self, engine):
        analysis = AnalysisResult(
            target_area="system_evolution",
            improvement_potential=0.8,
            details=[
                {"severity": "critical", "description": "High rollback rate"},
                {"severity": "high", "description": "Low success rate"},
            ],
        )
        plan = engine.generate_plan(analysis)
        assert len(plan.changes) == 2
        assert any("CRITICAL" in c for c in plan.changes)

    def test_generate_plan_risk_scores(self, engine):
        analysis = AnalysisResult(
            target_area="system_evolution",
            improvement_potential=0.5,
            details=[
                {"severity": "critical", "description": "Issue A"},
                {"severity": "medium", "description": "Issue B"},
            ],
        )
        plan = engine.generate_plan(analysis)
        assert plan.risk_score > 0.3

    def test_get_plan(self, engine):
        analysis = AnalysisResult(target_area="system_evolution")
        plan = engine.generate_plan(analysis)
        retrieved = engine.get_plan(plan.plan_id)
        assert retrieved is not None
        assert retrieved.target_area == "system_evolution"

    def test_statistics(self, engine):
        analysis = AnalysisResult(target_area="system_evolution")
        engine.generate_plan(analysis)
        engine.generate_plan(analysis)
        stats = engine.get_statistics()
        assert stats["total_plans"] == 2

    def test_with_graph_store(self):
        mock_graph = MagicMock()
        engine = MetaImprovementEngine(graph_store=mock_graph)
        engine.generate_plan(AnalysisResult(target_area="system_evolution"))
        assert mock_graph.create_entity.called

    def test_with_event_bus(self):
        mock_bus = MagicMock()
        engine = MetaImprovementEngine(event_bus=mock_bus)
        engine.generate_plan(AnalysisResult(target_area="system_evolution"))
        assert mock_bus.publish.called


class TestEvolutionStrategy:
    def test_to_dict(self):
        s = EvolutionStrategy(
            strategy_id="s1", name="balanced",
            description="Mix improvements",
            target_areas=["a", "b"], expected_impact=0.5,
            execution_order=["a", "b"], timestamp=100.0,
        )
        d = s.to_dict()
        assert d["expected_impact"] == 0.5
        assert d["execution_order"] == ["a", "b"]

    def test_to_dict_defaults(self):
        s = EvolutionStrategy()
        d = s.to_dict()
        assert d["target_areas"] == []


class TestMetaStrategySelector:
    @pytest.fixture
    def selector(self):
        return MetaStrategySelector()

    def test_health(self, selector):
        assert selector.health()["alive"] is True

    def test_select_conservative(self, selector):
        strategy = selector.select_strategy(risk_tolerance=0.1)
        assert strategy.name == "conservative"

    def test_select_balanced(self, selector):
        strategy = selector.select_strategy(risk_tolerance=0.5)
        assert strategy.name == "balanced"

    def test_select_aggressive(self, selector):
        strategy = selector.select_strategy(risk_tolerance=0.9)
        assert strategy.name == "aggressive"

    def test_select_area_focus(self, selector):
        strategy = selector.select_strategy(risk_tolerance=0.7)
        assert strategy.name == "area_focus"

    def test_predefined_strategies(self, selector):
        for s in PREDEFINED_STRATEGIES:
            strategy = selector.select_strategy(risk_tolerance={
                "conservative": 0.1, "balanced": 0.5,
                "aggressive": 0.9, "area_focus": 0.7,
                "cross_area": 0.75,
            }.get(s["name"], 0.5))
            assert strategy is not None

    def test_record_performance(self, selector):
        selector.record_performance("conservative", 0.3)
        selector.record_performance("conservative", 0.5)
        assert selector.get_best_strategy() == "conservative"

    def test_get_best_strategy_default(self, selector):
        assert selector.get_best_strategy() == "balanced"

    def test_get_statistics(self, selector):
        selector.select_strategy(0.5)
        stats = selector.get_statistics()
        assert stats["total_strategies"] >= 1

    def test_with_event_bus(self):
        mock_bus = MagicMock()
        selector = MetaStrategySelector(event_bus=mock_bus)
        selector.select_strategy(0.5)
        assert mock_bus.publish.called


class TestQualityScore:
    def test_to_dict(self):
        s = QualityScore(
            score_id="s1", target_area="system_evolution",
            overall_score=0.75,
            dimensions={"correctness": 0.8},
            recommendations=["Improve tests"],
            timestamp=100.0,
        )
        d = s.to_dict()
        assert d["overall_score"] == 0.75
        assert d["recommendations"] == ["Improve tests"]

    def test_to_dict_defaults(self):
        s = QualityScore()
        d = s.to_dict()
        assert d["dimensions"] == {}


class TestMetaQualityScorer:
    @pytest.fixture
    def scorer(self):
        return MetaQualityScorer()

    def test_health(self, scorer):
        assert scorer.health()["alive"] is True

    def test_score_area_defaults(self, scorer):
        score = scorer.score_area("system_evolution")
        assert score.target_area == "system_evolution"
        assert score.overall_score == 0.5
        assert len(score.dimensions) == 5

    def test_score_area_with_records(self, scorer):
        scorer.record_dimension_score("system_evolution", "correctness", 0.9)
        score = scorer.score_area("system_evolution")
        assert score.dimensions["correctness"] == 0.9

    def test_score_area_low_dimension(self, scorer):
        scorer.record_dimension_score("system_evolution", "correctness", 0.2)
        score = scorer.score_area("system_evolution")
        recs = " ".join(score.recommendations)
        assert "correctness" in recs

    def test_get_score(self, scorer):
        score = scorer.score_area("system_evolution")
        retrieved = scorer.get_score(score.score_id)
        assert retrieved is not None
        assert retrieved.target_area == "system_evolution"

    def test_statistics(self, scorer):
        scorer.record_dimension_score("system_evolution", "correctness", 0.9)
        scorer.score_area("system_evolution")
        stats = scorer.get_statistics()
        assert stats["total_scores"] == 1
        assert "correctness" in stats["dimension_averages"]

    def test_with_graph_store(self):
        mock_graph = MagicMock()
        scorer = MetaQualityScorer(graph_store=mock_graph)
        scorer.score_area("system_evolution")
        assert mock_graph.create_entity.called

    def test_with_event_bus(self):
        mock_bus = MagicMock()
        scorer = MetaQualityScorer(event_bus=mock_bus)
        scorer.score_area("system_evolution")
        assert mock_bus.publish.called


class TestMetaEvolutionResult:
    def test_to_dict(self):
        r = MetaEvolutionResult(
            meta_id="m1", selected_strategy="balanced",
            areas_analyzed=6, plans_generated=6, quality_scores=6,
            overall_improvement=0.5,
            details={"key": "value"},
            timestamp=100.0,
        )
        d = r.to_dict()
        assert d["areas_analyzed"] == 6
        assert d["details"]["key"] == "value"

    def test_to_dict_defaults(self):
        r = MetaEvolutionResult()
        d = r.to_dict()
        assert d["details"] == {}


class TestMetaEvolutionManager:
    @pytest.fixture
    def manager(self):
        return MetaEvolutionManager()

    def test_health(self, manager):
        assert manager.health()["alive"] is True

    def test_run_meta_no_components(self, manager):
        result = manager.run_meta_evolution()
        assert result.selected_strategy == "none"
        assert result.overall_improvement == 0.0

    def test_run_with_all_components(self, manager):
        mock_analyzer = MagicMock()
        mock_analyzer.analyze_all.return_value = [
            AnalysisResult(target_area="system_evolution", improvement_potential=0.5),
        ]
        mock_improver = MagicMock()
        mock_improver.generate_plan.return_value = ImprovementPlan(
            plan_id="p1", expected_gain=0.4,
        )
        mock_strategy = MagicMock()
        mock_strategy.select_strategy.return_value = EvolutionStrategy(
            strategy_id="s1", name="balanced", expected_impact=0.5,
        )
        mock_scorer = MagicMock()
        mock_scorer.score_area.return_value = QualityScore(
            score_id="q1", overall_score=0.7,
        )

        manager = MetaEvolutionManager(
            analyzer=mock_analyzer,
            improver=mock_improver,
            strategy_selector=mock_strategy,
            quality_scorer=mock_scorer,
        )
        result = manager.run_meta_evolution(risk_tolerance=0.5)
        assert result.selected_strategy == "balanced"
        assert result.areas_analyzed >= 1
        assert result.plans_generated >= 1
        assert result.quality_scores >= 1
        assert result.overall_improvement > 0

    def test_statistics(self, manager):
        manager.run_meta_evolution()
        stats = manager.get_statistics()
        assert stats["total_meta_evolutions"] == 1

    def test_get_result(self, manager):
        result = manager.run_meta_evolution()
        retrieved = manager.get_result(result.meta_id)
        assert retrieved is not None
        assert retrieved.meta_id == result.meta_id

    def test_with_graph_store(self):
        mock_graph = MagicMock()
        manager = MetaEvolutionManager(graph_store=mock_graph)
        manager.run_meta_evolution()
        assert mock_graph.create_entity.called

    def test_with_event_bus(self):
        mock_bus = MagicMock()
        manager = MetaEvolutionManager(event_bus=mock_bus)
        manager.run_meta_evolution()
        assert mock_bus.publish.called
