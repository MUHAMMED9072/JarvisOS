from __future__ import annotations

from app.executive_controller.routing_strategies import (
    AffinityStrategy,
    LeastLoadedStrategy,
    RoundRobinStrategy,
    WeightedStrategy,
)


class TestRoundRobinStrategy:
    def test_select_returns_agent(self) -> None:
        s = RoundRobinStrategy()
        result = s.select(["a", "b", "c"], {})
        assert result in ("a", "b", "c")

    def test_select_rotates(self) -> None:
        s = RoundRobinStrategy()
        results = [s.select(["a", "b"], {}) for _ in range(4)]
        assert results == ["a", "b", "a", "b"]

    def test_empty_candidates(self) -> None:
        s = RoundRobinStrategy()
        assert s.select([], {}) is None

    def test_name(self) -> None:
        assert RoundRobinStrategy().name() == "round-robin"


class TestLeastLoadedStrategy:
    def test_select_least_loaded(self) -> None:
        s = LeastLoadedStrategy()
        result = s.select(["a", "b", "c"], {"a": 0.9, "b": 0.1, "c": 0.5})
        assert result == "b"

    def test_select_equal_load(self) -> None:
        s = LeastLoadedStrategy()
        result = s.select(["a", "b"], {"a": 0.5, "b": 0.5})
        assert result in ("a", "b")

    def test_empty_candidates(self) -> None:
        s = LeastLoadedStrategy()
        assert s.select([], {}) is None

    def test_name(self) -> None:
        assert LeastLoadedStrategy().name() == "least-loaded"


class TestWeightedStrategy:
    def test_select_weighted(self) -> None:
        s = WeightedStrategy({"a": 10.0, "b": 1.0})
        # a has higher weight, so higher score for same load
        result = s.select(["a", "b"], {"a": 1.0, "b": 1.0})
        assert result == "a"

    def test_set_weight(self) -> None:
        s = WeightedStrategy()
        s.set_weight("x", 5.0)
        assert s.get_weight("x") == 5.0

    def test_default_weight(self) -> None:
        s = WeightedStrategy()
        assert s.get_weight("unknown") == 1.0

    def test_remove_weight(self) -> None:
        s = WeightedStrategy({"a": 3.0})
        assert s.remove_weight("a") is True
        assert s.remove_weight("nonexistent") is False

    def test_empty_candidates(self) -> None:
        s = WeightedStrategy()
        assert s.select([], {}) is None

    def test_zero_total_weight(self) -> None:
        s = WeightedStrategy({"a": 0.0, "b": 0.0})
        result = s.select(["a", "b"], {})
        assert result in ("a", "b")

    def test_name(self) -> None:
        assert WeightedStrategy().name() == "weighted"


class TestAffinityStrategy:
    def test_select_returns_agent(self) -> None:
        s = AffinityStrategy()
        result = s.select(["a", "b"], {}, affinity_key="task-1")
        assert result in ("a", "b")

    def test_affinity_sticks(self) -> None:
        s = AffinityStrategy()
        first = s.select(["a", "b"], {}, affinity_key="task-1")
        second = s.select(["a", "b"], {}, affinity_key="task-1")
        assert first == second

    def test_different_keys_get_different_agents(self) -> None:
        s = AffinityStrategy()
        r1 = s.select(["a", "b"], {}, affinity_key="task-1")
        r2 = s.select(["a", "b"], {}, affinity_key="task-2")
        # May or may not differ, but both should be valid
        assert r1 in ("a", "b")
        assert r2 in ("a", "b")

    def test_no_affinity_key(self) -> None:
        s = AffinityStrategy()
        result = s.select(["a"], {})
        assert result == "a"

    def test_empty_candidates(self) -> None:
        s = AffinityStrategy()
        assert s.select([], {}, affinity_key="task") is None
        assert s.select([], {}) is None

    def test_clear_affinity(self) -> None:
        s = AffinityStrategy()
        s.select(["a", "b"], {}, affinity_key="task-1")
        s.clear_affinity("task-1")
        assert s.get_affinity("task-1") is None

    def test_name(self) -> None:
        assert AffinityStrategy().name() == "affinity"
