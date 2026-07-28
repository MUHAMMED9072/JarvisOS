from __future__ import annotations

import pytest

from app.intelligence.decision_engine import DecisionEngine, AgentInfo, DecisionRecord
from app.intelligence.decision_matrix import Candidate


@pytest.fixture
def engine():
    return DecisionEngine()


class TestDecisionEngine:
    def test_select_agent_picks_best(self, engine):
        agents = [
            AgentInfo(agent_id="a1", name="AgentA", capability=10, cost=1, load=1, reliability=0.9),
            AgentInfo(agent_id="a2", name="AgentB", capability=1, cost=9, load=9, reliability=0.1),
        ]
        record = engine.select_agent(agents, context={"task": "critical"})
        assert record.winner_id == "a1"
        assert record.winner_label == "AgentA"
        assert record.decision_type == "agent_selection"

    def test_select_agent_with_tie(self, engine):
        agents = [
            AgentInfo(agent_id="a1", name="A", capability=5, cost=5, load=5, reliability=0.5),
            AgentInfo(agent_id="a2", name="B", capability=5, cost=5, load=5, reliability=0.5),
        ]
        record = engine.select_agent(agents)
        # Both equal; first candidate wins
        assert record.winner_id in ("a1", "a2")

    def test_select_agent_empty(self, engine):
        record = engine.select_agent([])
        assert record.winner_id == ""
        assert record.winner_label == ""

    def test_select_strategy(self, engine):
        strategies = [
            Candidate(id="s1", label="Fast", attributes={"capability": 8, "cost": 3, "load": 2, "reliability": 0.6}),
            Candidate(id="s2", label="Safe", attributes={"capability": 5, "cost": 8, "load": 7, "reliability": 0.9}),
        ]
        record = engine.select_strategy(strategies, context={"goal": "test"})
        assert record.decision_type == "strategy_selection"
        assert record.winner_id in ("s1", "s2")

    def test_select_strategy_empty(self, engine):
        record = engine.select_strategy([])
        assert record.winner_id == ""

    def test_decision_logging(self, engine):
        assert engine.get_decision_count() == 0
        agents = [AgentInfo(agent_id="x", name="X", capability=5, cost=5, load=5, reliability=0.5)]
        engine.select_agent(agents)
        assert engine.get_decision_count() == 1

    def test_get_recent_decisions(self, engine):
        for i in range(5):
            agents = [AgentInfo(agent_id=f"a{i}", name=f"A{i}", capability=5, cost=5, load=5, reliability=0.5)]
            engine.select_agent(agents)
        assert len(engine.get_recent_decisions(limit=3)) == 3
        assert len(engine.get_recent_decisions(limit=10)) == 5

    def test_decision_record_to_dict(self):
        r = DecisionRecord(
            decision_type="agent_selection",
            context={"task": "test"},
            winner_id="w1",
            winner_label="Winner",
            scores={"w1": 0.9},
            explanation="Best score",
        )
        d = r.to_dict()
        assert d["decision_type"] == "agent_selection"
        assert d["winner_id"] == "w1"
        assert d["explanation"] == "Best score"

    def test_agent_info_to_candidate(self):
        agent = AgentInfo(agent_id="a1", name="Agent1", capability=8, cost=3, load=2, reliability=0.8)
        cand = agent.to_candidate()
        assert cand.id == "a1"
        assert cand.label == "Agent1"
        assert cand.attributes["capability"] == 8
        assert cand.attributes["cost"] == -3  # negated for maximize

    def test_health(self, engine):
        h = engine.health()
        assert h["alive"] is True
        assert h["decisions_made"] == 0

    def test_matrix_access(self, engine):
        m = engine.matrix()
        assert m.count() > 0
        assert m.get_criterion("capability") is not None

    def test_default_matrix_has_four_criteria(self, engine):
        m = engine.matrix()
        assert m.count() == 4

    def test_select_agent_logs_explanation(self, engine):
        agents = [
            AgentInfo(agent_id="a", name="A", capability=9, cost=2, load=1, reliability=0.9),
            AgentInfo(agent_id="b", name="B", capability=1, cost=9, load=9, reliability=0.1),
        ]
        record = engine.select_agent(agents)
        assert "Score" in record.explanation or "capability" in record.explanation

    def test_get_decision_log(self, engine):
        agents = [AgentInfo(agent_id="a", name="A", capability=5, cost=5, load=5, reliability=0.5)]
        engine.select_agent(agents)
        log = engine.get_decision_log()
        assert len(log) == 1
        assert log[0].winner_id == "a"
