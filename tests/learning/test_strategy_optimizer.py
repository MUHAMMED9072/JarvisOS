from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.learning.strategy_optimizer import (
    ABTestResult,
    OptimizationSuggestion,
    StrategyOptimizer,
)


class TestABTestResult:
    def test_to_dict(self):
        r = ABTestResult(
            test_id="t1", strategy_a_name="A", strategy_b_name="B",
            a_success_rate=0.8, b_success_rate=0.6,
            a_avg_latency=1.0, b_avg_latency=2.0,
            a_sample_count=100, b_sample_count=100,
            winner="A", confidence=0.9, duration_hours=24.0,
        )
        d = r.to_dict()
        assert d["test_id"] == "t1"
        assert d["winner"] == "A"
        assert d["a_success_rate"] == 0.8
        assert d["b_success_rate"] == 0.6

    def test_to_dict_defaults(self):
        r = ABTestResult()
        d = r.to_dict()
        assert d["test_id"] == ""


class TestOptimizationSuggestion:
    def test_to_dict(self):
        s = OptimizationSuggestion(
            suggestion_id="s1", target="planner", metric="success_rate",
            current_value=0.5, suggested_value=0.65,
            expected_improvement=0.15, rationale="Improve planning",
            priority="high",
        )
        d = s.to_dict()
        assert d["suggestion_id"] == "s1"
        assert d["priority"] == "high"
        assert d["current_value"] == 0.5

    def test_to_dict_defaults(self):
        s = OptimizationSuggestion()
        d = s.to_dict()
        assert d["suggestion_id"] == ""


class TestStrategyOptimizer:
    @pytest.fixture
    def optimizer(self):
        return StrategyOptimizer()

    def test_initial_state(self, optimizer):
        stats = optimizer.get_statistics()
        assert stats["total_decisions"] == 0
        assert stats["ab_tests_performed"] == 0

    def test_record_decision(self, optimizer):
        optimizer.record_decision(
            decision_type="planner", strategy="hierarchical",
            outcome=True, latency=1.0,
        )
        stats = optimizer.get_statistics()
        assert stats["total_decisions"] == 1

    def test_record_decision_with_context(self, optimizer):
        optimizer.record_decision(
            decision_type="reasoner", strategy="weighted",
            outcome=True, latency=0.5,
            context={"criteria": "accuracy"},
        )
        stats = optimizer.get_statistics()
        assert stats["total_decisions"] == 1

    def test_analyze_planner_optimization_insufficient_data(self, optimizer):
        suggestions = optimizer.analyze_planner_optimization()
        assert suggestions == []

    def test_analyze_planner_optimization_low_success(self, optimizer):
        for _ in range(5):
            optimizer.record_decision("planner", "hierarchical", False, 1.0)
        suggestions = optimizer.analyze_planner_optimization()
        assert len(suggestions) >= 1
        assert suggestions[0].target == "planner"
        assert suggestions[0].metric == "success_rate"

    def test_analyze_planner_optimization_high_latency(self, optimizer):
        for _ in range(5):
            optimizer.record_decision("planner", "slow_strat", True, 6.0)
        suggestions = optimizer.analyze_planner_optimization()
        latency_suggestions = [s for s in suggestions if s.metric == "latency"]
        assert len(latency_suggestions) >= 1

    def test_analyze_planner_optimization_good_performance(self, optimizer):
        for _ in range(5):
            optimizer.record_decision("planner", "fast_strat", True, 0.5)
        suggestions = optimizer.analyze_planner_optimization()
        assert len(suggestions) == 0

    def test_analyze_reasoner_optimization_insufficient_data(self, optimizer):
        suggestions = optimizer.analyze_reasoner_optimization()
        assert suggestions == []

    def test_analyze_reasoner_optimization_low_accuracy(self, optimizer):
        for _ in range(5):
            optimizer.record_decision(
                "reasoner", "logical", False, 1.0,
                context={"criteria": "deductive"},
            )
        suggestions = optimizer.analyze_reasoner_optimization()
        assert len(suggestions) >= 1
        assert suggestions[0].target == "reasoner"

    def test_analyze_decision_optimization_insufficient_data(self, optimizer):
        suggestions = optimizer.analyze_decision_optimization()
        assert suggestions == []

    def test_analyze_decision_optimization_low_weight(self, optimizer):
        for _ in range(5):
            optimizer.record_decision(
                "decision_engine", "agent_x", False, 1.0,
                context={"selected_agent": "agent_x"},
            )
        suggestions = optimizer.analyze_decision_optimization()
        assert len(suggestions) >= 1
        assert suggestions[0].target == "decision_engine"

    def test_run_ab_test_with_data(self, optimizer):
        for _ in range(10):
            optimizer.record_decision("planner", "strategy_a", True, 1.0)
        for _ in range(10):
            optimizer.record_decision("planner", "strategy_b", False, 2.0)
        result = optimizer.run_ab_test("strategy_a", "strategy_b")
        assert result.winner == "strategy_a"
        assert result.a_success_rate == 1.0
        assert result.b_success_rate == 0.0

    def test_run_ab_test_tie(self, optimizer):
        for _ in range(4):
            optimizer.record_decision("planner", "strat_a", True, 1.0)
            optimizer.record_decision("planner", "strat_b", True, 1.0)
        result = optimizer.run_ab_test("strat_a", "strat_b")
        assert result.winner in ("tie", "strat_a", "strat_b")

    def test_run_ab_test_no_data(self, optimizer):
        result = optimizer.run_ab_test("nonexistent_a", "nonexistent_b")
        assert result.winner == "tie"
        assert result.a_sample_count == 0
        assert result.b_sample_count == 0

    def test_get_ab_test_results(self, optimizer):
        for _ in range(5):
            optimizer.record_decision("planner", "A", True, 1.0)
            optimizer.record_decision("planner", "B", False, 1.0)
        optimizer.run_ab_test("A", "B")
        results = optimizer.get_ab_test_results()
        assert len(results) == 1

    def test_get_optimization_suggestions(self, optimizer):
        for _ in range(5):
            optimizer.record_decision("planner", "bad", False, 1.0)
        for _ in range(5):
            optimizer.record_decision(
                "reasoner", "bad", False, 1.0,
                context={"criteria": "weak"},
            )
        for _ in range(3):
            optimizer.record_decision(
                "decision_engine", "bad_agent", False, 1.0,
                context={"selected_agent": "bad_agent"},
            )
        suggestions = optimizer.get_optimization_suggestions()
        assert len(suggestions) >= 1

    def test_health(self, optimizer):
        h = optimizer.health()
        assert h["alive"] is True
        assert h["decisions_recorded"] == 0

    def test_health_after_records(self, optimizer):
        optimizer.record_decision("planner", "test", True, 1.0)
        h = optimizer.health()
        assert h["decisions_recorded"] == 1

    def test_max_decisions(self, optimizer):
        optimizer._max_decisions = 5
        for i in range(20):
            optimizer.record_decision("planner", "t", True, 1.0)
        stats = optimizer.get_statistics()
        assert stats["total_decisions"] == 5

    def test_decisions_by_type(self, optimizer):
        optimizer.record_decision("planner", "p1", True, 1.0)
        optimizer.record_decision("reasoner", "r1", True, 1.0)
        optimizer.record_decision("decision_engine", "d1", True, 1.0)
        stats = optimizer.get_statistics()
        assert stats["decisions_by_type"]["planner"] == 1
        assert stats["decisions_by_type"]["reasoner"] == 1
        assert stats["decisions_by_type"]["decision_engine"] == 1

    def test_concurrent_recording(self, optimizer):
        import threading
        errors = []

        def record():
            try:
                for _ in range(50):
                    optimizer.record_decision("planner", "conc", True, 1.0)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=record) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(errors) == 0
        stats = optimizer.get_statistics()
        assert stats["total_decisions"] == 200

    def test_has_pattern_recognizer(self):
        mock_pr = MagicMock()
        opt = StrategyOptimizer(pattern_recognizer=mock_pr)
        assert opt._recognizer is mock_pr
