from __future__ import annotations

import pytest

from app.governance.risk_scoring import RiskScorer, RiskScore, RISK_FACTORS


class TestRiskScorer:
    def test_default_weights(self):
        scorer = RiskScorer()
        for factor in RISK_FACTORS:
            assert scorer.get_weight(factor) > 0

    def test_set_weight_clamps(self):
        scorer = RiskScorer()
        scorer.set_weight("scope_impact", -0.5)
        assert scorer.get_weight("scope_impact") == 0.0
        scorer.set_weight("scope_impact", 1.5)
        assert scorer.get_weight("scope_impact") == 1.0

    def test_compute_minimal_risk(self):
        scorer = RiskScorer()
        ctx = {
            "affected_systems": 1,
            "requests_new_permissions": False,
            "estimated_cpu": 5,
            "estimated_memory_mb": 64,
            "dependency_depth": 0,
            "modifies_existing": False,
            "irreversible": False,
            "historical_failure_rate": 0.0,
        }
        result = scorer.compute(ctx)
        assert 0.0 <= result.total <= 1.0
        assert result.level in ("minimal", "low")

    def test_compute_high_risk(self):
        scorer = RiskScorer()
        ctx = {
            "affected_systems": 10,
            "requests_new_permissions": True,
            "estimated_cpu": 90,
            "estimated_memory_mb": 8192,
            "dependency_depth": 8,
            "modifies_existing": True,
            "irreversible": True,
            "historical_failure_rate": 0.8,
        }
        result = scorer.compute(ctx)
        assert result.total > 0.4
        assert result.level in ("medium", "high", "critical")

    def test_compute_risk_score_levels(self):
        scorer = RiskScorer()
        assert scorer.compute({}).total >= 0.0

    def test_risk_score_level_critical(self):
        rs = RiskScore(total=0.9)
        assert rs.level == "critical"

    def test_risk_score_level_high(self):
        rs = RiskScore(total=0.7)
        assert rs.level == "high"

    def test_risk_score_level_medium(self):
        rs = RiskScore(total=0.5)
        assert rs.level == "medium"

    def test_risk_score_level_low(self):
        rs = RiskScore(total=0.3)
        assert rs.level == "low"

    def test_risk_score_level_minimal(self):
        rs = RiskScore(total=0.1)
        assert rs.level == "minimal"

    def test_risk_score_to_dict(self):
        rs = RiskScore(total=0.5, factors={"scope_impact": 0.5})
        d = rs.to_dict()
        assert d["total"] == 0.5
        assert d["level"] == "medium"

    def test_risk_factor_weighted_score(self):
        from app.governance.risk_scoring import RiskFactor
        rf = RiskFactor(name="test", score=0.8, weight=0.25)
        assert rf.weighted_score == 0.2

    def test_risk_factor_to_dict(self):
        from app.governance.risk_scoring import RiskFactor
        rf = RiskFactor(name="test", score=0.5, weight=0.2, evidence="test")
        d = rf.to_dict()
        assert d["name"] == "test"
        assert d["weighted_score"] == 0.1

    def test_custom_scorer_overrides_default(self):
        scorer = RiskScorer()
        scorer.register_scorer("scope_impact", lambda ctx: 1.0)
        result = scorer.compute({"affected_systems": 1})
        scope_factor = [f for f in result.breakdown if f.name == "scope_impact"][0]
        assert scope_factor.score == 1.0

    def test_health(self):
        scorer = RiskScorer()
        h = scorer.health()
        assert h["alive"]
        assert "scope_impact" in h["factors"]

    def test_thread_safe(self):
        import threading
        scorer = RiskScorer()
        errors = []

        def score():
            try:
                for _ in range(50):
                    scorer.compute({"affected_systems": 5})
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=score) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
