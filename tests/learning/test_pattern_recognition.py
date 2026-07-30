from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from app.learning.pattern_recognition import (
    ExecutionRecord,
    Pattern,
    PatternCatalog,
    PatternRecommendation,
    PatternRecognizer,
)


class TestExecutionRecord:
    def test_to_dict(self):
        r = ExecutionRecord(
            agent_id="a1", task_type="code", success=True, latency=1.5,
            cpu_usage=0.3, memory_usage=0.4, token_count=500,
            error_message="", timestamp=1000.0, task_tags=["urgent"],
        )
        d = r.to_dict()
        assert d["agent_id"] == "a1"
        assert d["task_type"] == "code"
        assert d["success"] is True
        assert d["latency"] == 1.5
        assert d["token_count"] == 500

    def test_to_dict_defaults(self):
        r = ExecutionRecord()
        d = r.to_dict()
        assert d["agent_id"] == ""
        assert d["success"] is False


class TestPattern:
    def test_to_dict(self):
        p = Pattern(
            pattern_id="p1", name="test", pattern_type="success",
            task_type="code", confidence=0.85, sample_count=10,
            avg_latency=2.0, success_rate=0.9,
            common_tags=["fast"], common_errors=["err1"],
            typical_agents=["a1"],
        )
        d = p.to_dict()
        assert d["pattern_id"] == "p1"
        assert d["confidence"] == 0.85
        assert d["success_rate"] == 0.9

    def test_to_dict_defaults(self):
        p = Pattern()
        d = p.to_dict()
        assert d["pattern_id"] == ""


class TestPatternCatalog:
    def test_to_dict(self):
        sp = Pattern(pattern_id="s1", name="success", pattern_type="success")
        fp = Pattern(pattern_id="f1", name="failure", pattern_type="failure")
        cat = PatternCatalog(success_patterns=[sp], failure_patterns=[fp], last_updated=42.0)
        d = cat.to_dict()
        assert len(d["success_patterns"]) == 1
        assert len(d["failure_patterns"]) == 1
        assert d["last_updated"] == 42.0

    def test_to_dict_defaults(self):
        cat = PatternCatalog()
        d = cat.to_dict()
        assert d["success_patterns"] == []
        assert d["failure_patterns"] == []


class TestPatternRecommendation:
    def test_to_dict(self):
        p = Pattern(pattern_id="p1", name="rec", pattern_type="success")
        rec = PatternRecommendation(
            task_type="code", recommended_patterns=[p],
            predicted_success_rate=0.8, suggested_agents=["a1"],
            confidence=0.75,
        )
        d = rec.to_dict()
        assert d["task_type"] == "code"
        assert len(d["recommended_patterns"]) == 1
        assert d["predicted_success_rate"] == 0.8
        assert d["suggested_agents"] == ["a1"]
        assert d["confidence"] == 0.75


class TestPatternRecognizer:
    @pytest.fixture
    def recognizer(self):
        return PatternRecognizer()

    def test_initial_state(self, recognizer):
        cat = recognizer.analyze()
        assert cat.success_patterns == []
        assert cat.failure_patterns == []
        stats = recognizer.get_statistics()
        assert stats["total_records"] == 0

    def test_record_execution(self, recognizer):
        r = ExecutionRecord(agent_id="a1", task_type="code", success=True, latency=1.0)
        recognizer.record_execution(r)
        stats = recognizer.get_statistics()
        assert stats["total_records"] == 1
        assert stats["success_count"] == 1

    def test_record_from_metrics(self, recognizer):
        recognizer.record_from_metrics(
            agent_id="a1", success=True, latency=1.5,
            task_type="code", cpu=0.2, memory=0.3, tokens=100,
            error="", tags=["test"],
        )
        stats = recognizer.get_statistics()
        assert stats["total_records"] == 1
        assert stats["success_count"] == 1

    def test_analyze_success_pattern(self, recognizer):
        for _ in range(5):
            recognizer.record_from_metrics("a1", True, 1.0, task_type="code")
        cat = recognizer.analyze()
        assert len(cat.success_patterns) >= 1
        assert cat.success_patterns[0].task_type == "code"
        assert cat.success_patterns[0].success_rate == 1.0

    def test_analyze_failure_pattern(self, recognizer):
        for _ in range(5):
            recognizer.record_from_metrics("a1", False, 2.0, task_type="bug")
        cat = recognizer.analyze()
        assert len(cat.failure_patterns) >= 1
        assert cat.failure_patterns[0].task_type == "bug"

    def test_analyze_insufficient_data(self, recognizer):
        recognizer.record_from_metrics("a1", True, 1.0, task_type="rare")
        cat = recognizer.analyze()
        assert len(cat.success_patterns) == 0

    def test_recommend_with_matching(self, recognizer):
        for _ in range(5):
            recognizer.record_from_metrics("a1", True, 1.0, task_type="code", tags=["python"])
        rec = recognizer.recommend("code", tags=["python"])
        assert rec.task_type == "code"
        assert rec.predicted_success_rate > 0
        assert len(rec.recommended_patterns) > 0

    def test_recommend_no_match(self, recognizer):
        rec = recognizer.recommend("nonexistent")
        assert rec.task_type == "nonexistent"
        assert rec.predicted_success_rate == 0.5
        assert rec.confidence == 0.3

    def test_get_patterns_by_type(self, recognizer):
        for _ in range(5):
            recognizer.record_from_metrics("a1", True, 1.0, task_type="code")
        for _ in range(5):
            recognizer.record_from_metrics("a1", False, 2.0, task_type="bug")
        success = recognizer.get_patterns_by_type("success")
        failure = recognizer.get_patterns_by_type("failure")
        assert len(success) >= 1
        assert len(failure) >= 1

    def test_get_statistics(self, recognizer):
        for _ in range(3):
            recognizer.record_from_metrics("a1", True, 1.0, task_type="code")
        recognizer.record_from_metrics("a1", False, 2.0, task_type="debug")
        stats = recognizer.get_statistics()
        assert stats["total_records"] == 4
        assert stats["success_count"] == 3
        assert stats["failure_count"] == 1
        assert stats["task_types"] == 2

    def test_health(self, recognizer):
        h = recognizer.health()
        assert h["alive"] is True
        assert h["records_collected"] == 0

    def test_max_records(self, recognizer):
        recognizer._max_records = 5
        for i in range(10):
            recognizer.record_from_metrics(f"a{i}", True, 1.0, task_type="t")
        stats = recognizer.get_statistics()
        assert stats["total_records"] == 5

    def test_multiple_task_types(self, recognizer):
        types = ["code", "test", "deploy", "review"]
        for tt in types:
            for _ in range(5):
                recognizer.record_from_metrics("a1", True, 1.0, task_type=tt)
        cat = recognizer.analyze()
        assert len(cat.success_patterns) == 4

    def test_tags_in_patterns(self, recognizer):
        for _ in range(5):
            recognizer.record_from_metrics(
                "a1", True, 1.0, task_type="code", tags=["python", "fast"],
            )
        cat = recognizer.analyze()
        assert "python" in cat.success_patterns[0].common_tags

    def test_errors_in_failure_patterns(self, recognizer):
        for _ in range(5):
            recognizer.record_from_metrics(
                "a1", False, 2.0, task_type="crash", error="timeout error",
            )
        cat = recognizer.analyze()
        assert len(cat.failure_patterns) >= 1
        assert any("timeout" in e for e in cat.failure_patterns[0].common_errors)

    def test_recommend_with_tag_matching(self, recognizer):
        for _ in range(5):
            recognizer.record_from_metrics(
                "a1", True, 1.0, task_type="code", tags=["python", "fast"],
            )
        rec = recognizer.recommend("code", tags=["python"])
        assert rec.predicted_success_rate > 0

    def test_recommend_tag_partial_match(self, recognizer):
        for _ in range(5):
            recognizer.record_from_metrics(
                "a1", True, 1.0, task_type="code", tags=["python", "fast"],
            )
        rec = recognizer.recommend("code", tags=["python"])
        assert len(rec.recommended_patterns) > 0

    def test_concurrent_record_execution(self, recognizer):
        import threading
        errors = []

        def record():
            try:
                for _ in range(100):
                    recognizer.record_from_metrics("a1", True, 1.0, task_type="conc")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=record) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(errors) == 0
        stats = recognizer.get_statistics()
        assert stats["total_records"] == 500

    def test_with_graph_store(self):
        mock_graph = MagicMock()
        r = PatternRecognizer(graph_store=mock_graph)
        r.record_from_metrics("a1", True, 1.0, task_type="code")
        mock_graph.create_entity.assert_called_once()
        kwargs = mock_graph.create_entity.call_args.kwargs
        assert kwargs["name"].startswith("exec_a1_")
        assert kwargs["type"] == "execution_record"

    def test_graph_store_error_does_not_crash(self):
        mock_graph = MagicMock()
        mock_graph.create_entity.side_effect = RuntimeError("KG error")
        r = PatternRecognizer(graph_store=mock_graph)
        r.record_from_metrics("a1", True, 1.0, task_type="code")
        stats = r.get_statistics()
        assert stats["total_records"] == 1

    def test_analyze_empty_records(self, recognizer):
        cat = recognizer.analyze()
        assert len(cat.success_patterns) == 0
        assert len(cat.failure_patterns) == 0

    def test_pattern_id_contains_task_type(self, recognizer):
        for _ in range(5):
            recognizer.record_from_metrics("a1", True, 1.0, task_type="unique_task")
        cat = recognizer.analyze()
        assert "unique_task" in cat.success_patterns[0].pattern_id

    def test_statistics_after_analyze(self, recognizer):
        for _ in range(5):
            recognizer.record_from_metrics("a1", True, 1.0, task_type="code")
        recognizer.analyze()
        stats = recognizer.get_statistics()
        assert stats["patterns_identified"] >= 1
