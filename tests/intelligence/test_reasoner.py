from __future__ import annotations

import pytest

from app.intelligence.reasoner import Reasoner


class TestReasoner:
    def test_initial_health(self):
        r = Reasoner()
        h = r.health()
        assert h["alive"]
        assert h["recommendations"] == 0

    def test_recommend_basic(self):
        r = Reasoner()
        result = r.recommend(
            context={"goal": "build a tool", "constraints": {}},
            strategies=[
                {"name": "fast_approach", "scores": {"speed": 0.9, "accuracy": 0.5}},
                {"name": "accurate_approach", "scores": {"speed": 0.3, "accuracy": 0.95}},
            ],
        )
        assert result["winner"] in ("fast_approach", "accurate_approach")
        assert 0.0 <= result["confidence"] <= 1.0
        assert "comparison" in result
        assert "justification" in result

    def test_recommend_returns_winner(self):
        r = Reasoner()
        result = r.recommend(
            context={"goal": "test"},
            strategies=[{"name": "only_one", "scores": {"speed": 0.8}}],
        )
        assert result["winner"] == "only_one"

    def test_recommend_empty_strategies(self):
        r = Reasoner()
        result = r.recommend(
            context={"goal": "test"},
            strategies=[],
        )
        assert result["winner"] == "no_viable_strategy"

    def test_recommend_includes_timestamp(self):
        r = Reasoner()
        result = r.recommend(
            context={"goal": "test"},
            strategies=[{"name": "s1", "scores": {"speed": 0.5}}],
        )
        assert result["timestamp"] > 0

    def test_list_recommendations(self):
        r = Reasoner()
        assert r.list_recommendations() == []
        r.recommend(context={"goal": "g1"}, strategies=[{"name": "s1", "scores": {"speed": 0.5}}])
        r.recommend(context={"goal": "g2"}, strategies=[{"name": "s2", "scores": {"speed": 0.6}}])
        assert len(r.list_recommendations()) == 2

    def test_get_recommendation_count(self):
        r = Reasoner()
        assert r.get_recommendation_count() == 0
        r.recommend(context={"goal": "g1"}, strategies=[{"name": "s1", "scores": {"speed": 0.5}}])
        assert r.get_recommendation_count() == 1

    def test_recommend_with_criteria_from_context(self):
        r = Reasoner()
        result = r.recommend(
            context={
                "goal": "test",
                "constraints": {"speed_weight": 2.0, "accuracy_weight": 0.5},
            },
            strategies=[
                {"name": "fast", "scores": {"speed": 0.9, "accuracy": 0.3}},
                {"name": "accurate", "scores": {"speed": 0.2, "accuracy": 0.9}},
            ],
        )
        # speed_weight is higher, so fast should win
        assert result["winner"] == "fast"

    def test_properties(self):
        r = Reasoner()
        assert r.comparator is not None
        assert r.justifier is not None

    def test_event_bus_publishing(self):
        from app.core.event_bus import EventBus
        bus = EventBus()
        received: list[dict] = []
        bus.subscribe("reasoner.recommendation", lambda d: received.append(d))
        r = Reasoner(event_bus=bus)
        r.recommend(
            context={"goal": "test"},
            strategies=[{"name": "s1", "scores": {"speed": 0.5}}],
        )
        assert len(received) == 1
        assert received[0]["winner"] == "s1"

    def test_thread_safe(self):
        import threading
        r = Reasoner()
        errors = []

        def recommend():
            try:
                for i in range(20):
                    r.recommend(
                        context={"goal": f"g{i}"},
                        strategies=[
                            {"name": "a", "scores": {"speed": 0.5}},
                            {"name": "b", "scores": {"speed": 0.8}},
                        ],
                    )
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=recommend) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
        assert r.get_recommendation_count() == 80
