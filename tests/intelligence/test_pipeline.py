from __future__ import annotations

import pytest

from app.intelligence.context import SessionContext
from app.intelligence.decision_engine import AgentInfo
from app.intelligence.pipeline import IntelligencePipeline
from app.intelligence.outcome_analyzer import TaskOutcome
from app.knowledge_graph.store import GraphStore


@pytest.fixture
def graph():
    g = GraphStore()
    g.clear()
    return g


@pytest.fixture
def pipeline(graph):
    return IntelligencePipeline(graph_store=graph)


class TestIntelligencePipeline:
    def test_run_full_pipeline(self, pipeline):
        ctx = pipeline.run("Create a test module")
        assert ctx.goal == "Create a test module"
        assert "goal_id" in ctx.session_data
        assert ctx.session_data.get("goal_type") == "create"
        assert len(ctx.stage_metrics) >= 3  # supervisor, planner, reasoner

    def test_run_with_agent_pool(self, pipeline):
        agents = [
            AgentInfo(agent_id="a1", name="Agent1", capability=8, cost=3, load=2, reliability=0.8),
        ]
        ctx = pipeline.run("Analyze the system", agent_pool=agents)
        assert "agent_decision" in ctx.session_data

    def test_run_sets_session_data(self, pipeline):
        ctx = pipeline.run("Debug issue #42")
        assert ctx.goal == "Debug issue #42"
        assert isinstance(ctx.session_data.get("recommendation"), dict)

    def test_run_returns_ctx(self, pipeline):
        ctx = pipeline.run("Query user data")
        assert isinstance(ctx, SessionContext)

    def test_multiple_runs(self, pipeline):
        ctx1 = pipeline.run("First goal")
        ctx2 = pipeline.run("Second goal")
        assert ctx1.session_id != ctx2.session_id

    def test_feedback_loop(self, pipeline):
        outcome = TaskOutcome(task_id="t1", task_name="test", success=True)
        result = pipeline.feedback_loop(outcome)
        assert "analyzed_outcome" in result
        assert "report" in result
        assert "planner_feedback" in result
        assert "reasoner_feedback" in result

    def test_feedback_loop_failure(self, pipeline):
        outcome = TaskOutcome(
            task_id="t2", task_name="fail", success=False,
            error_message="timeout",
        )
        result = pipeline.feedback_loop(outcome)
        assert result["analyzed_outcome"].success is False

    def test_health(self, pipeline):
        h = pipeline.health()
        assert h["alive"] is True
        assert h["pipeline_ready"] is True

    def test_before_stage_hook(self, pipeline):
        calls = []
        pipeline.on_before_stage("supervisor", lambda ctx: calls.append("before"))
        pipeline.run("Test")
        assert len(calls) >= 1

    def test_after_stage_hook(self, pipeline):
        calls = []
        pipeline.on_after_stage("supervisor", lambda ctx, m: calls.append("after"))
        pipeline.run("Test")
        assert len(calls) >= 1

    def test_run_goal_type_populated(self, pipeline):
        ctx = pipeline.run("A test goal")
        assert ctx.session_data.get("goal_type") is not None

    def test_run_create_goal_type(self, pipeline):
        ctx = pipeline.run("Create a new service")
        assert "goal_type" in ctx.session_data
