from __future__ import annotations

import pytest

from app.intelligence.heuristic_store import HeuristicStore, Heuristic
from app.intelligence.outcome_analyzer import OutcomeAnalyzer, TaskOutcome
from app.intelligence.reflection import Reflection


@pytest.fixture
def heuristic_store():
    return HeuristicStore()


@pytest.fixture
def outcome_analyzer():
    return OutcomeAnalyzer()


@pytest.fixture
def reflection(outcome_analyzer, heuristic_store):
    return Reflection(outcome_analyzer=outcome_analyzer, heuristic_store=heuristic_store)


class TestHeuristicStore:
    def test_register_and_get(self, heuristic_store):
        h = Heuristic(name="test", domain="planning", weight=0.8)
        hid = heuristic_store.register(h)
        assert heuristic_store.get(hid) is h
        assert heuristic_store.get("nonexistent") is None

    def test_get_by_name(self, heuristic_store):
        h = Heuristic(name="by_name", domain="reasoning")
        heuristic_store.register(h)
        assert heuristic_store.get_by_name("by_name") is h
        assert heuristic_store.get_by_name("missing") is None

    def test_update(self, heuristic_store):
        h = Heuristic(name="updatable", weight=0.5)
        hid = heuristic_store.register(h)
        h.weight = 0.9
        assert heuristic_store.update(h) is True
        assert heuristic_store.get(hid).weight == 0.9

    def test_update_nonexistent(self, heuristic_store):
        h = Heuristic(name="orphan")
        assert heuristic_store.update(h) is False

    def test_delete(self, heuristic_store):
        h = Heuristic(name="deletable")
        hid = heuristic_store.register(h)
        assert heuristic_store.delete(hid) is True
        assert heuristic_store.get(hid) is None

    def test_delete_nonexistent(self, heuristic_store):
        assert heuristic_store.delete("nope") is False

    def test_list_heuristics(self, heuristic_store):
        for i in range(5):
            heuristic_store.register(Heuristic(name=f"h{i}", domain="planning"))
        assert len(heuristic_store.list_heuristics()) == 5
        assert len(heuristic_store.list_heuristics(domain="planning")) == 5
        assert len(heuristic_store.list_heuristics(domain="other")) == 0

    def test_find_by_domain(self, heuristic_store):
        heuristic_store.register(Heuristic(name="a", domain="x"))
        heuristic_store.register(Heuristic(name="b", domain="y"))
        assert len(heuristic_store.find_by_domain("x")) == 1
        assert len(heuristic_store.find_by_domain("y")) == 1

    def test_record_success(self, heuristic_store):
        h = Heuristic(name="s")
        hid = heuristic_store.register(h)
        assert heuristic_store.record_success(hid) is True
        assert heuristic_store.get(hid).success_count == 1
        assert heuristic_store.get(hid).reliability == 1.0

    def test_record_failure(self, heuristic_store):
        h = Heuristic(name="f")
        hid = heuristic_store.register(h)
        assert heuristic_store.record_failure(hid) is True
        assert heuristic_store.get(hid).failure_count == 1
        assert heuristic_store.get(hid).reliability == 0.0

    def test_record_nonexistent(self, heuristic_store):
        assert heuristic_store.record_success("nope") is False
        assert heuristic_store.record_failure("nope") is False

    def test_reliability_no_events(self):
        h = Heuristic(name="r")
        assert h.reliability == 0.5

    def test_count_and_clear(self, heuristic_store):
        assert heuristic_store.count() == 0
        for i in range(3):
            heuristic_store.register(Heuristic(name=f"c{i}"))
        assert heuristic_store.count() == 3
        heuristic_store.clear()
        assert heuristic_store.count() == 0

    def test_health(self, heuristic_store):
        assert heuristic_store.health()["alive"] is True
        assert heuristic_store.health()["heuristic_count"] == 0

    def test_heuristic_to_dict(self):
        h = Heuristic(name="d", domain="test", weight=0.7, success_count=3, failure_count=1)
        d = h.to_dict()
        assert d["name"] == "d"
        assert d["domain"] == "test"
        assert d["weight"] == 0.7
        assert d["reliability"] == 0.75

    def test_list_sorted_by_reliability(self, heuristic_store):
        h1 = Heuristic(name="low", domain="x")
        h2 = Heuristic(name="high", domain="x")
        id1 = heuristic_store.register(h1)
        id2 = heuristic_store.register(h2)
        heuristic_store.record_success(id2)
        heuristic_store.record_success(id2)
        heuristic_store.record_failure(id1)
        sorted_h = heuristic_store.list_heuristics(domain="x")
        assert sorted_h[0].name == "high"
        assert sorted_h[1].name == "low"


class TestOutcomeAnalyzer:
    def test_success_outcome(self, outcome_analyzer):
        outcome = TaskOutcome(task_id="t1", task_name="ok", success=True)
        analyzed = outcome_analyzer.analyze(outcome)
        assert analyzed.success is True
        assert analyzed.root_cause == ""
        assert outcome_analyzer.get_outcome_count() == 1

    def test_failure_with_pattern(self, outcome_analyzer):
        outcome = TaskOutcome(
            task_id="t2", task_name="fail", success=False,
            error_message="timeout occurred",
        )
        analyzed = outcome_analyzer.analyze(outcome)
        assert analyzed.success is False
        assert analyzed.root_cause == "execution_timeout"
        assert analyzed.failure_pattern == "timeout"

    def test_failure_unknown_pattern(self, outcome_analyzer):
        outcome = TaskOutcome(
            task_id="t3", task_name="weird", success=False,
            error_message="something strange happened",
        )
        analyzed = outcome_analyzer.analyze(outcome)
        assert analyzed.root_cause == "unknown"
        assert analyzed.failure_pattern == "unknown"

    def test_complex_error_root_cause(self, outcome_analyzer):
        outcome = TaskOutcome(
            task_id="t4", success=False,
            error_message="x" * 120,
        )
        analyzed = outcome_analyzer.analyze(outcome)
        assert analyzed.root_cause == "complex_error"

    def test_outcome_to_dict(self):
        o = TaskOutcome(task_id="t1", success=True, duration_seconds=1.5)
        d = o.to_dict()
        assert d["task_id"] == "t1"
        assert d["duration_seconds"] == 1.5

    def test_list_outcomes_filter_success(self, outcome_analyzer):
        outcome_analyzer.analyze(TaskOutcome(task_id="a", success=True))
        outcome_analyzer.analyze(TaskOutcome(task_id="b", success=False))
        assert len(outcome_analyzer.list_outcomes(success=True)) == 1
        assert len(outcome_analyzer.list_outcomes(success=False)) == 1

    def test_failure_rate(self, outcome_analyzer):
        assert outcome_analyzer.get_failure_rate() == 0.0
        outcome_analyzer.analyze(TaskOutcome(task_id="a", success=True))
        outcome_analyzer.analyze(TaskOutcome(task_id="b", success=False))
        assert outcome_analyzer.get_failure_rate() == 0.5

    def test_get_patterns(self, outcome_analyzer):
        outcome_analyzer.analyze(TaskOutcome(
            task_id="a", success=False, error_message="timeout",
        ))
        outcome_analyzer.analyze(TaskOutcome(
            task_id="b", success=False, error_message="timeout",
        ))
        patterns = outcome_analyzer.get_patterns()
        assert len(patterns) == 1
        assert patterns[0].pattern == "timeout"
        assert patterns[0].count == 2

    def test_get_common_failures(self, outcome_analyzer):
        outcome_analyzer.analyze(TaskOutcome(
            task_id="a", success=False, error_message="timeout",
        ))
        assert len(outcome_analyzer.get_common_failures(min_count=2)) == 0
        outcome_analyzer.analyze(TaskOutcome(
            task_id="b", success=False, error_message="timeout",
        ))
        assert len(outcome_analyzer.get_common_failures(min_count=2)) == 1

    def test_many_patterns(self, outcome_analyzer):
        for error in ["timeout", "not found", "permission denied"]:
            outcome_analyzer.analyze(TaskOutcome(
                task_id="t", success=False, error_message=error,
            ))
        assert len(outcome_analyzer.get_patterns()) == 3

    def test_health(self, outcome_analyzer):
        h = outcome_analyzer.health()
        assert h["alive"] is True
        assert h["outcomes_analyzed"] == 0

    def test_pattern_record_to_dict(self):
        from app.intelligence.outcome_analyzer import PatternRecord
        p = PatternRecord(pattern="timeout", cause="execution_timeout", count=3, severity="high")
        d = p.to_dict()
        assert d["pattern"] == "timeout"
        assert d["count"] == 3

    def test_error_message_not_mutated(self, outcome_analyzer):
        outcome_analyzer.analyze(TaskOutcome(
            task_id="t", success=False, error_message="not found in database",
        ))
        patterns = outcome_analyzer.get_patterns()
        assert patterns[0].pattern == "not found"
        assert patterns[0].cause == "resource_not_found"


class TestReflection:
    def test_analyze_success(self, reflection):
        outcome = TaskOutcome(task_id="t1", task_name="ok", success=True)
        result = reflection.analyze(outcome)
        assert result.success is True
        assert reflection.outcome_analyzer.get_outcome_count() == 1

    def test_analyze_failure_updates_heuristics(self, reflection):
        h = Heuristic(name="test_heur", domain="timeout")
        reflection.heuristic_store.register(h)
        outcome = TaskOutcome(
            task_id="t2", success=False,
            error_message="timeout occurred",
        )
        result = reflection.analyze(outcome)
        assert result.success is False
        assert reflection.heuristic_store.get(h.id).failure_count == 1

    def test_generate_report(self, reflection):
        reflection.analyze(TaskOutcome(task_id="a", success=True))
        report = reflection.generate_report()
        assert report.total_outcomes == 1
        assert report.failure_rate == 0.0

    def test_report_with_failures(self, reflection):
        reflection.analyze(TaskOutcome(task_id="a", success=False, error_message="timeout"))
        reflection.analyze(TaskOutcome(task_id="b", success=False, error_message="timeout"))
        report = reflection.generate_report()
        assert report.total_outcomes == 2
        assert report.failure_rate == 1.0
        assert "timeout" in report.common_failures
        assert len(report.recommendations) > 0

    def test_report_to_dict(self, reflection):
        report = reflection.generate_report()
        d = report.to_dict()
        assert "id" in d
        assert "recommendations" in d

    def test_feedback_for_planner(self, reflection):
        analysis = reflection.feedback_for_planner()
        assert "adjusted_weights" in analysis
        assert "avoid_patterns" in analysis
        assert "failure_rate" in analysis

    def test_feedback_for_reasoner(self, reflection):
        analysis = reflection.feedback_for_reasoner()
        assert "heuristic_reliability" in analysis
        assert "total_failures" in analysis

    def test_list_reports(self, reflection):
        assert len(reflection.list_reports()) == 0
        reflection.generate_report()
        reflection.generate_report()
        assert len(reflection.list_reports()) == 2

    def test_health(self, reflection):
        h = reflection.health()
        assert h["alive"] is True

    def test_interface_consistency(self, reflection):
        assert hasattr(reflection, "outcome_analyzer")
        assert hasattr(reflection, "heuristic_store")
        outcome = TaskOutcome(task_id="test", success=False, error_message="timeout")
        reflection.analyze(outcome)
        report = reflection.generate_report()
        planner_fb = reflection.feedback_for_planner()
        reasoner_fb = reflection.feedback_for_reasoner()
        assert isinstance(report, object)
        assert "adjusted_weights" in planner_fb
        assert "heuristic_reliability" in reasoner_fb
