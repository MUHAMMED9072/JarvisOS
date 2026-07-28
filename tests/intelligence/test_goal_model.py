from __future__ import annotations

import pytest

from app.intelligence.goal_model import Goal, GoalInterpreter, GoalStatus, GoalType


class TestGoal:
    def test_default_id_generated(self):
        g = Goal()
        assert len(g.id) == 16

    def test_default_status_pending(self):
        g = Goal()
        assert g.status == GoalStatus.PENDING

    def test_default_type_unknown(self):
        g = Goal()
        assert g.goal_type == GoalType.UNKNOWN

    def test_to_dict(self):
        g = Goal(
            description="build a trading bot",
            goal_type=GoalType.CREATE,
            intent="create a trading bot",
            parameters={"language": "python"},
            constraints={"urgent": True},
            session_id="s1",
        )
        d = g.to_dict()
        assert d["description"] == "build a trading bot"
        assert d["goal_type"] == "create"
        assert d["parameters"]["language"] == "python"


class TestGoalInterpreter:
    def test_interpret_create(self):
        interpreter = GoalInterpreter()
        goal = interpreter.interpret("Create a new trading bot")
        assert goal.goal_type == GoalType.CREATE
        assert "trading bot" in goal.description

    def test_interpret_modify(self):
        interpreter = GoalInterpreter()
        goal = interpreter.interpret("Update the authentication module")
        assert goal.goal_type == GoalType.MODIFY

    def test_interpret_query(self):
        interpreter = GoalInterpreter()
        goal = interpreter.interpret("Find all agents with high memory usage")
        assert goal.goal_type == GoalType.QUERY

    def test_interpret_analyze(self):
        interpreter = GoalInterpreter()
        goal = interpreter.interpret("Analyze the performance logs")
        assert goal.goal_type == GoalType.ANALYZE

    def test_interpret_debug(self):
        interpreter = GoalInterpreter()
        goal = interpreter.interpret("Fix the memory leak in the scheduler")
        assert goal.goal_type == GoalType.DEBUG

    def test_interpret_deploy(self):
        interpreter = GoalInterpreter()
        goal = interpreter.interpret("Deploy the new monitoring agent")
        assert goal.goal_type == GoalType.DEPLOY

    def test_interpret_unknown(self):
        interpreter = GoalInterpreter()
        goal = interpreter.interpret("Hello world")
        assert goal.goal_type == GoalType.UNKNOWN

    def test_interpret_extracts_intent(self):
        interpreter = GoalInterpreter()
        goal = interpreter.interpret("I want to build a trading bot using python")
        assert goal.goal_type == GoalType.CREATE
        assert "build a trading bot" in goal.intent

    def test_interpret_intent_with_phrase(self):
        interpreter = GoalInterpreter()
        goal = interpreter.interpret("Could you please analyze the database queries")
        assert "analyze the database queries" in goal.intent

    def test_interpret_extracts_parameters(self):
        interpreter = GoalInterpreter()
        goal = interpreter.interpret("Create agent --name worker --type task")
        assert goal.parameters.get("name") == "worker"
        assert goal.parameters.get("type") == "task"

    def test_interpret_extracts_constraints_urgent(self):
        interpreter = GoalInterpreter()
        goal = interpreter.interpret("Fix this urgently")
        assert goal.constraints.get("urgent") is True

    def test_interpret_extracts_constraints_fast(self):
        interpreter = GoalInterpreter()
        goal = interpreter.interpret("Build it fast")
        assert goal.constraints.get("fast") is True

    def test_add_custom_keywords(self):
        interpreter = GoalInterpreter()
        interpreter.add_keywords(GoalType.MONITOR, ["watchdog", "heartbeat"])
        goal = interpreter.interpret("Set up heartbeat monitoring")
        assert goal.goal_type == GoalType.MONITOR

    def test_supported_types(self):
        interpreter = GoalInterpreter()
        types = interpreter.supported_types()
        assert "create" in types
        assert "unknown" in types

    def test_thread_safe(self):
        import threading
        interpreter = GoalInterpreter()
        errors = []

        def interpret():
            try:
                for _ in range(30):
                    interpreter.interpret("Create a new tool")
                    interpreter.add_keywords(GoalType.LEARN, ["train"])
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=interpret) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
