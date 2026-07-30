from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from app.learning.quality_scoring import (
    CapabilityQualityScorer,
    QualityAlert,
    QualityScoreEntry,
)


class TestQualityScoreEntry:
    def test_to_dict(self):
        e = QualityScoreEntry(
            capability_name="code_gen", provider_id="p1", provider_name="Provider1",
            score=0.85, success_rate=0.9, avg_latency=1.5,
            resource_efficiency=0.8, sample_count=100, last_updated=1000.0,
            trend="improving",
        )
        d = e.to_dict()
        assert d["capability_name"] == "code_gen"
        assert d["score"] == 0.85
        assert d["trend"] == "improving"

    def test_to_dict_defaults(self):
        e = QualityScoreEntry()
        d = e.to_dict()
        assert d["capability_name"] == ""


class TestQualityAlert:
    def test_to_dict(self):
        a = QualityAlert(
            alert_id="a1", capability_name="code_gen", provider_name="P1",
            previous_score=0.8, current_score=0.5, threshold=0.2,
            message="Score dropped", timestamp=1000.0,
        )
        d = a.to_dict()
        assert d["alert_id"] == "a1"
        assert d["previous_score"] == 0.8
        assert d["current_score"] == 0.5

    def test_to_dict_defaults(self):
        a = QualityAlert()
        d = a.to_dict()
        assert d["alert_id"] == ""


class TestCapabilityQualityScorer:
    @pytest.fixture
    def scorer(self):
        return CapabilityQualityScorer()

    def test_initial_state(self, scorer):
        stats = scorer.get_statistics()
        assert stats["total_entries"] == 0
        assert stats["active_alerts"] == 0

    def test_update_score_creates_entry(self, scorer):
        entry = scorer.update_score(
            capability_name="code_gen", provider_id="p1", provider_name="P1",
            success=True, latency=1.0, cpu_usage=0.2, memory_usage=0.3,
        )
        assert entry.capability_name == "code_gen"
        assert entry.provider_id == "p1"
        assert entry.sample_count == 1
        assert entry.score > 0

    def test_update_score_accumulates(self, scorer):
        for _ in range(5):
            scorer.update_score("code_gen", "p1", "P1", True, 1.0, 0.2, 0.3)
        entry = scorer.get_score("code_gen", "p1")
        assert entry is not None
        assert entry.sample_count == 5

    def test_get_score_nonexistent(self, scorer):
        entry = scorer.get_score("nonexistent", "nope")
        assert entry is None

    def test_get_scores_for_capability(self, scorer):
        scorer.update_score("code_gen", "p1", "P1", True, 1.0)
        scorer.update_score("code_gen", "p2", "P2", True, 2.0)
        entries = scorer.get_scores_for_capability("code_gen")
        assert len(entries) == 2

    def test_get_scores_for_provider(self, scorer):
        scorer.update_score("code_gen", "p1", "P1", True, 1.0)
        scorer.update_score("test_gen", "p1", "P1", True, 1.0)
        entries = scorer.get_scores_for_provider("p1")
        assert len(entries) == 2

    def test_trend_improving(self, scorer):
        scorer.update_score("code_gen", "p1", "P1", False, 5.0, 0.5, 0.5)
        scorer.update_score("code_gen", "p1", "P1", True, 0.5, 0.1, 0.1)
        scorer.update_score("code_gen", "p1", "P1", True, 0.5, 0.1, 0.1)
        entry = scorer.get_score("code_gen", "p1")
        assert entry is not None
        # After two good runs, trend should not be declining
        assert entry.trend in ("improving", "stable")

    def test_trend_declining(self, scorer):
        scorer.update_score("code_gen", "p1", "P1", True, 0.5, 0.1, 0.1)
        scorer.update_score("code_gen", "p1", "P1", False, 5.0, 0.8, 0.8)
        scorer.update_score("code_gen", "p1", "P1", False, 5.0, 0.8, 0.8)
        entry = scorer.get_score("code_gen", "p1")
        assert entry is not None
        assert entry.trend in ("declining", "stable")

    def test_alert_generated_on_drop(self, scorer):
        scorer.set_decay_factor(0.5)
        for _ in range(10):
            scorer.update_score("code_gen", "p1", "P1", True, 0.5, 0.1, 0.1)
        scorer.update_score("code_gen", "p1", "P1", False, 10.0, 0.9, 0.9)
        alerts = scorer.get_alerts()
        assert len(alerts) >= 1
        assert alerts[0].capability_name == "code_gen"

    def test_alert_not_generated_on_small_drop(self, scorer):
        scorer.update_score("code_gen", "p1", "P1", True, 0.5, 0.1, 0.1)
        # Small degradation shouldn't trigger alert
        scorer.update_score("code_gen", "p1", "P1", True, 0.6, 0.15, 0.15)
        alerts = scorer.get_alerts()
        assert len(alerts) == 0

    def test_alert_callback(self):
        callback = MagicMock()
        scorer = CapabilityQualityScorer(alert_callback=callback)
        scorer.set_decay_factor(0.5)
        for _ in range(10):
            scorer.update_score("code_gen", "p1", "P1", True, 0.5, 0.1, 0.1)
        scorer.update_score("code_gen", "p1", "P1", False, 10.0, 0.9, 0.9)
        callback.assert_called_once()

    def test_callback_error_does_not_crash(self):
        callback = MagicMock()
        callback.side_effect = RuntimeError("callback error")
        scorer = CapabilityQualityScorer(alert_callback=callback)
        scorer.update_score("code_gen", "p1", "P1", True, 0.5, 0.1, 0.1)
        scorer.update_score("code_gen", "p1", "P1", True, 0.5, 0.1, 0.1)
        scorer.update_score("code_gen", "p1", "P1", False, 10.0, 0.9, 0.9)
        scorer.update_score("code_gen", "p1", "P1", False, 10.0, 0.9, 0.9)
        # Should not raise
        assert True

    def test_set_decay_factor(self, scorer):
        scorer.set_decay_factor(0.99)
        assert scorer._decay_factor == 0.99

    def test_set_decay_factor_clamps(self, scorer):
        scorer.set_decay_factor(0.1)
        assert scorer._decay_factor == 0.5
        scorer.set_decay_factor(1.0)
        assert scorer._decay_factor == 0.999

    def test_health(self, scorer):
        h = scorer.health()
        assert h["alive"] is True
        assert h["entries_tracked"] == 0

    def test_health_with_entries(self, scorer):
        scorer.update_score("code_gen", "p1", "P1", True, 1.0)
        h = scorer.health()
        assert h["entries_tracked"] == 1
        assert h["avg_quality_score"] > 0

    def test_get_statistics(self, scorer):
        scorer.update_score("code_gen", "p1", "P1", True, 1.0)
        scorer.update_score("test_gen", "p1", "P1", True, 2.0)
        stats = scorer.get_statistics()
        assert stats["total_entries"] == 2
        assert stats["avg_score"] > 0
        assert stats["decay_factor"] == 0.95

    def test_score_range(self, scorer):
        entry = scorer.update_score(
            "code_gen", "p1", "P1", True, 1.0, 0.2, 0.3,
        )
        assert 0.0 <= entry.score <= 1.0

    def test_multiple_providers_same_capability(self, scorer):
        e1 = scorer.update_score("code_gen", "p1", "P1", True, 1.0)
        e2 = scorer.update_score("code_gen", "p2", "P2", True, 1.0)
        assert e1.provider_id == "p1"
        assert e2.provider_id == "p2"

    def test_with_capability_registry(self):
        mock_reg = MagicMock()
        scorer = CapabilityQualityScorer(capability_registry=mock_reg)
        scorer.update_score("code_gen", "p1", "P1", True, 1.0)
        mock_reg.update_quality_score.assert_called_once_with("p1", scorer.get_score("code_gen", "p1").score)

    def test_registry_error_does_not_crash(self):
        mock_reg = MagicMock()
        mock_reg.update_quality_score.side_effect = RuntimeError("registry error")
        scorer = CapabilityQualityScorer(capability_registry=mock_reg)
        scorer.update_score("code_gen", "p1", "P1", True, 1.0)
        assert True

    def test_get_alerts_limit(self, scorer):
        # Trigger multiple alerts
        for i in range(5):
            cap = f"cap_{i}"
            scorer.update_score(cap, "p1", "P1", True, 0.5, 0.1, 0.1)
            scorer.update_score(cap, "p1", "P1", True, 0.5, 0.1, 0.1)
            scorer.update_score(cap, "p1", "P1", False, 10.0, 0.9, 0.9)
            scorer.update_score(cap, "p1", "P1", False, 10.0, 0.9, 0.9)
        alerts = scorer.get_alerts(limit=3)
        assert len(alerts) <= 3

    def test_max_alerts(self, scorer):
        for i in range(200):
            cap = f"cap_{i}"
            scorer.update_score(cap, "p1", "P1", True, 0.5, 0.1, 0.1)
            scorer.update_score(cap, "p1", "P1", True, 0.5, 0.1, 0.1)
            scorer.update_score(cap, "p1", "P1", False, 10.0, 0.9, 0.9)
            scorer.update_score(cap, "p1", "P1", False, 10.0, 0.9, 0.9)
        assert len(scorer._alerts) <= scorer._max_alerts

    def test_concurrent_updates(self, scorer):
        import threading
        errors = []

        def update():
            try:
                for _ in range(50):
                    scorer.update_score(
                        "code_gen", "p1", "P1",
                        success=True, latency=1.0, cpu_usage=0.2, memory_usage=0.3,
                    )
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=update) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(errors) == 0
        entry = scorer.get_score("code_gen", "p1")
        assert entry is not None
        assert entry.sample_count == 200
