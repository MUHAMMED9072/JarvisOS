from __future__ import annotations

import pytest

from app.intelligence.decision_matrix import DecisionMatrix, Candidate, CriterionDef


@pytest.fixture
def matrix():
    m = DecisionMatrix()
    m.add_criterion("speed", weight=2.0, maximize=True, description="Speed score")
    m.add_criterion("accuracy", weight=3.0, maximize=True, description="Accuracy score")
    m.add_criterion("cost", weight=1.0, maximize=False, description="Cost (lower better)")
    return m


class TestDecisionMatrix:
    def test_add_and_list_criteria(self):
        m = DecisionMatrix()
        m.add_criterion("a", weight=1.0)
        m.add_criterion("b", weight=2.0)
        criteria = m.list_criteria()
        assert len(criteria) == 2
        names = {c.name for c in criteria}
        assert names == {"a", "b"}

    def test_remove_criterion(self):
        m = DecisionMatrix()
        m.add_criterion("x")
        assert m.remove_criterion("x") is True
        assert m.count() == 0

    def test_remove_nonexistent(self):
        m = DecisionMatrix()
        assert m.remove_criterion("nope") is False

    def test_get_criterion(self):
        m = DecisionMatrix()
        m.add_criterion("test", weight=0.8, maximize=False, description="Test criterion")
        c = m.get_criterion("test")
        assert c is not None
        assert c.weight == 0.8
        assert c.maximize is False

    def test_get_criterion_nonexistent(self):
        assert DecisionMatrix().get_criterion("nope") is None

    def test_evaluate_single_candidate(self, matrix):
        c = Candidate(label="only", attributes={"speed": 10, "accuracy": 8, "cost": 5})
        result = matrix.evaluate([c])
        assert result.winner is not None
        assert result.winner.label == "only"

    def test_evaluate_selects_best(self, matrix):
        low = Candidate(label="low", attributes={"speed": 1, "accuracy": 1, "cost": 10})
        high = Candidate(label="high", attributes={"speed": 10, "accuracy": 10, "cost": 1})
        result = matrix.evaluate([low, high])
        assert result.winner is not None
        assert result.winner.label == "high"

    def test_evaluate_runner_up(self, matrix):
        a = Candidate(label="A", attributes={"speed": 10, "accuracy": 10, "cost": 1})
        b = Candidate(label="B", attributes={"speed": 5, "accuracy": 5, "cost": 5})
        c = Candidate(label="C", attributes={"speed": 1, "accuracy": 1, "cost": 10})
        result = matrix.evaluate([a, b, c])
        assert result.winner.label == "A"
        assert result.runner_up.label == "B"

    def test_empty_candidates(self, matrix):
        result = matrix.evaluate([])
        assert result.winner is None

    def test_no_criteria(self):
        m = DecisionMatrix()
        c = Candidate(label="x", attributes={"a": 1})
        result = m.evaluate([c])
        assert result.winner is not None

    def test_criterion_def_to_dict(self):
        cd = CriterionDef(name="test", weight=0.5, maximize=False, description="desc")
        d = cd.to_dict()
        assert d["name"] == "test"
        assert d["weight"] == 0.5
        assert d["maximize"] is False

    def test_candidate_to_dict(self):
        cand = Candidate(label="c1", attributes={"a": 1.0, "b": 2.0})
        d = cand.to_dict()
        assert d["label"] == "c1"
        assert d["attributes"] == {"a": 1.0, "b": 2.0}

    def test_decision_result_to_dict(self, matrix):
        cand = Candidate(label="w", attributes={"speed": 5})
        result = matrix.evaluate([cand])
        d = result.to_dict()
        assert d["winner_label"] == "w"
        assert "scores" in d

    def test_custom_scorer(self):
        m = DecisionMatrix()
        m.add_criterion("combo")
        m.set_custom_scorer("combo", lambda attrs: attrs.get("a", 0) * 2 + attrs.get("b", 0))
        a = Candidate(label="A", attributes={"a": 5, "b": 3})
        b = Candidate(label="B", attributes={"a": 1, "b": 10})
        result = m.evaluate([a, b])
        assert result.winner.label == "A"

    def test_custom_scorer_error_returns_zero(self):
        m = DecisionMatrix()
        m.add_criterion("risky")
        m.set_custom_scorer("risky", lambda attrs: 1 / 0)
        c = Candidate(label="x", attributes={})
        result = m.evaluate([c])
        assert result.winner is not None

    def test_custom_scorer_unknown_criterion(self):
        m = DecisionMatrix()
        with pytest.raises(ValueError, match="Unknown criterion"):
            m.set_custom_scorer("missing", lambda a: 1.0)

    def test_multiple_criteria_weights(self):
        m = DecisionMatrix()
        m.add_criterion("a", weight=10.0)
        m.add_criterion("b", weight=1.0)
        high_a = Candidate(label="high_a", attributes={"a": 10, "b": 0})
        high_b = Candidate(label="high_b", attributes={"a": 0, "b": 10})
        result = m.evaluate([high_a, high_b])
        assert result.winner.label == "high_a"

    def test_clear(self):
        m = DecisionMatrix()
        m.add_criterion("x")
        m.add_criterion("y")
        m.set_custom_scorer("x", lambda a: 1.0)
        m.clear()
        assert m.count() == 0

    def test_health(self):
        m = DecisionMatrix()
        assert m.health()["alive"] is True
        assert m.health()["criterion_count"] == 0

    def test_descriptive_explanations(self, matrix):
        a = Candidate(label="A", attributes={"speed": 10, "accuracy": 10, "cost": 1})
        b = Candidate(label="B", attributes={"speed": 1, "accuracy": 1, "cost": 10})
        result = matrix.evaluate([a, b])
        expl = result.explanations.get(a.id, "")
        assert "speed" in expl
        assert "cost" in expl

    def test_all_scores_present(self, matrix):
        a = Candidate(label="A", attributes={"speed": 8, "accuracy": 7, "cost": 3})
        b = Candidate(label="B", attributes={"speed": 6, "accuracy": 9, "cost": 4})
        result = matrix.evaluate([a, b])
        assert a.id in result.scores
        assert b.id in result.scores
