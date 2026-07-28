from __future__ import annotations

import pytest

from app.intelligence.strategy_comparator import (
    StrategyComparator,
    Strategy,
    Criterion,
    ComparisonResult,
)


class TestCriterion:
    def test_defaults(self):
        c = Criterion()
        assert c.name == ""
        assert c.weight == 1.0

    def test_to_dict(self):
        c = Criterion(name="speed", weight=0.8)
        d = c.to_dict()
        assert d["name"] == "speed"
        assert d["weight"] == 0.8


class TestStrategy:
    def test_defaults(self):
        s = Strategy()
        assert s.weighted_score == 0.0

    def test_weighted_score(self):
        s = Strategy(name="a", scores={"speed": 0.8, "accuracy": 0.9})
        assert s.weighted_score == pytest.approx(1.7)

    def test_to_dict(self):
        s = Strategy(name="fast", scores={"speed": 0.9})
        d = s.to_dict()
        assert d["name"] == "fast"
        assert d["weighted_score"] == 0.9


class TestComparisonResult:
    def test_defaults(self):
        r = ComparisonResult()
        assert r.winner == ""

    def test_to_dict(self):
        r = ComparisonResult(
            strategies=[Strategy(name="a")],
            criteria=[Criterion(name="speed")],
            winner="a",
            summary="a wins",
        )
        d = r.to_dict()
        assert d["winner"] == "a"
        assert len(d["strategies"]) == 1


class TestStrategyComparator:
    def test_compare_two_strategies(self):
        c = StrategyComparator()
        strategies = [
            Strategy(name="fast", scores={"speed": 0.9, "accuracy": 0.5}),
            Strategy(name="accurate", scores={"speed": 0.4, "accuracy": 0.95}),
        ]
        result = c.compare(strategies)
        assert len(result.strategies) == 2
        assert result.winner in ("fast", "accurate")

    def test_compare_with_custom_criteria(self):
        c = StrategyComparator()
        strategies = [
            Strategy(name="cheap", scores={"speed": 0.3, "risk": 0.2}),
            Strategy(name="robust", scores={"speed": 0.8, "risk": 0.9}),
        ]
        criteria = [Criterion(name="speed", weight=1.0), Criterion(name="risk", weight=2.0)]
        result = c.compare(strategies, criteria)
        # robust has higher risk score, which is weighted more
        assert result.winner == "robust"

    def test_compare_single_strategy(self):
        c = StrategyComparator()
        strategies = [Strategy(name="only", scores={"speed": 0.5})]
        result = c.compare(strategies)
        assert result.winner == "only"

    def test_compare_empty(self):
        c = StrategyComparator()
        result = c.compare([])
        assert result.winner == ""

    def test_compare_ranking_order(self):
        c = StrategyComparator()
        strategies = [
            Strategy(name="low", scores={"speed": 0.2}),
            Strategy(name="high", scores={"speed": 0.9}),
            Strategy(name="mid", scores={"speed": 0.5}),
        ]
        result = c.compare(strategies)
        assert result.strategies[0].name == "high"
        assert result.strategies[1].name == "mid"
        assert result.strategies[2].name == "low"

    def test_health(self):
        c = StrategyComparator()
        h = c.health()
        assert h["alive"]

    def test_thread_safe(self):
        import threading
        c = StrategyComparator()
        errors = []

        def compare():
            try:
                for _ in range(30):
                    strategies = [
                        Strategy(name=f"s{i}", scores={"speed": i / 10.0})
                        for i in range(5)
                    ]
                    c.compare(strategies)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=compare) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
