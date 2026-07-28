from __future__ import annotations

from typing import Any

import pytest

from app.intelligence.goal_model import Goal, GoalStatus, GoalType
from app.intelligence.supervisor import Session, Delegation, Supervisor


class TestSession:
    def test_defaults(self):
        s = Session()
        assert s.goals == []
        assert s.id == ""

    def test_to_dict(self):
        s = Session(id="s1")
        s.goals.append(Goal(description="test"))
        d = s.to_dict()
        assert d["id"] == "s1"
        assert d["goal_count"] == 1


class TestDelegation:
    def test_defaults(self):
        d = Delegation()
        assert d.target == ""

    def test_to_dict(self):
        d = Delegation(target="planner", goal_id="g1")
        data = d.to_dict()
        assert data["target"] == "planner"
        assert data["goal_id"] == "g1"


class TestSupervisor:
    def test_initial_state(self, supervisor):
        assert supervisor.health()["alive"]
        assert supervisor.get_stats()["total_sessions"] == 0

    def test_create_session(self, supervisor):
        session = supervisor.create_session()
        assert session.id.startswith("session_")
        assert supervisor.get_session(session.id) is session

    def test_create_session_with_id(self, supervisor):
        session = supervisor.create_session("custom-id")
        assert session.id == "custom-id"

    def test_get_session_missing(self, supervisor):
        assert supervisor.get_session("nonexistent") is None

    def test_list_sessions(self, supervisor):
        supervisor.create_session()
        supervisor.create_session()
        assert len(supervisor.list_sessions()) == 2

    def test_receive_goal_creates_goal(self, supervisor):
        goal = supervisor.receive_goal("Build a trading bot")
        assert goal.description == "Build a trading bot"
        assert goal.goal_type == GoalType.CREATE
        assert goal.status == GoalStatus.PLANNING

    def test_receive_goal_creates_session(self, supervisor):
        goal = supervisor.receive_goal("Test goal")
        assert goal.session_id != ""
        session = supervisor.get_session(goal.session_id)
        assert session is not None
        assert len(session.goals) == 1

    def test_receive_goal_existing_session(self, supervisor):
        session = supervisor.create_session("s1")
        goal1 = supervisor.receive_goal("Goal 1", session_id="s1")
        goal2 = supervisor.receive_goal("Goal 2", session_id="s1")
        assert goal1.session_id == "s1"
        assert goal2.session_id == "s1"
        assert len(session.goals) == 2

    def test_receive_goal_with_metadata(self, supervisor):
        goal = supervisor.receive_goal("Test", metadata={"source": "user", "priority": "high"})
        assert goal.metadata.get("source") == "user"
        assert goal.metadata.get("priority") == "high"

    def test_get_goal(self, supervisor):
        goal = supervisor.receive_goal("Test goal")
        assert supervisor.get_goal(goal.id) is goal

    def test_get_goal_missing(self, supervisor):
        assert supervisor.get_goal("nonexistent") is None

    def test_list_goals(self, supervisor):
        supervisor.receive_goal("Goal 1")
        supervisor.receive_goal("Goal 2")
        assert len(supervisor.list_goals()) == 2

    def test_list_goals_by_session(self, supervisor):
        s1 = supervisor.create_session("s1")
        s2 = supervisor.create_session("s2")
        supervisor.receive_goal("G1", session_id="s1")
        supervisor.receive_goal("G2", session_id="s1")
        supervisor.receive_goal("G3", session_id="s2")
        assert len(supervisor.list_goals(session_id="s1")) == 2
        assert len(supervisor.list_goals(session_id="s2")) == 1

    def test_list_goals_invalid_session(self, supervisor):
        assert supervisor.list_goals(session_id="nonexistent") == []

    def test_update_goal_status(self, supervisor):
        goal = supervisor.receive_goal("Test")
        assert supervisor.update_goal_status(goal.id, GoalStatus.COMPLETED)
        assert supervisor.get_goal(goal.id).status == GoalStatus.COMPLETED

    def test_update_goal_status_missing(self, supervisor):
        assert not supervisor.update_goal_status("nonexistent", GoalStatus.COMPLETED)

    def test_set_planner_callback(self, supervisor):
        captured: list[tuple] = []

        def callback(goal: Goal, context: Any) -> None:
            captured.append((goal, context))

        supervisor.set_planner_callback(callback)
        goal = supervisor.receive_goal("Test goal")
        assert len(captured) == 1
        assert captured[0][0].id == goal.id

    def test_list_delegations(self, supervisor):
        assert supervisor.list_delegations() == []
        supervisor.receive_goal("Test")
        delegations = supervisor.list_delegations()
        assert len(delegations) == 0  # no planner callback set

    def test_delegation_count(self, supervisor):
        assert supervisor.get_delegation_count() == 0

    def test_delegation_created_with_callback(self, supervisor):
        supervisor.set_planner_callback(lambda g, c: None)
        supervisor.receive_goal("Test")
        assert supervisor.get_delegation_count() == 1
        d = supervisor.list_delegations()[0]
        assert d.target == "planner"

    def test_get_working_memory(self, supervisor):
        session = supervisor.create_session("s1")
        supervisor.receive_goal("G1", session_id="s1")
        supervisor.receive_goal("G2", session_id="s1")
        mem = supervisor.get_working_memory("s1")
        assert mem["session_id"] == "s1"
        assert mem["goal_count"] == 2

    def test_get_working_memory_unknown_session(self, supervisor):
        assert supervisor.get_working_memory("nonexistent") == {}

    def test_health(self, supervisor):
        h = supervisor.health()
        assert h["alive"]
        assert h["uptime_seconds"] >= 0
        assert h["sessions"] >= 0

    def test_stats(self, supervisor):
        supervisor.receive_goal("Test")
        stats = supervisor.get_stats()
        assert stats["total_sessions"] == 1
        assert stats["total_goals"] == 1

    def test_interpreter_property(self, supervisor):
        assert supervisor.interpreter is not None

    def test_context_assembler_property(self, supervisor):
        assert supervisor.context_assembler is not None

    def test_event_bus_publishing(self, graph_store):
        from app.core.event_bus import EventBus
        bus = EventBus()
        received: list[dict] = []
        bus.subscribe("supervisor.goal.received", lambda d: received.append(d))
        supervisor = Supervisor(graph_store, event_bus=bus)
        supervisor.receive_goal("Test goal")
        assert len(received) >= 1
        assert received[0]["description"] == "Test goal"

    def test_thread_safe(self, graph_store):
        import threading
        supervisor = Supervisor(graph_store)
        errors = []

        def work():
            try:
                for i in range(20):
                    supervisor.receive_goal(f"Goal {i}")
                    supervisor.list_sessions()
                    supervisor.health()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=work) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
