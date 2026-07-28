from __future__ import annotations

import threading
import time

import pytest

from app.intelligence import (
    Goal,
    GoalInterpreter,
    GoalStatus,
    GoalType,
    Planner,
    Supervisor,
    Reasoner,
    Strategy,
    Criterion,
    DecisionEngine,
    AgentInfo,
    Reflection,
    Heuristic,
    TaskOutcome,
    IntelligencePipeline,
)
from app.knowledge_graph.store import GraphStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def graph():
    g = GraphStore()
    g.clear()
    return g


@pytest.fixture
def pipeline(graph):
    return IntelligencePipeline(graph_store=graph)


# ---------------------------------------------------------------------------
# Diverse goal type scenarios
# ---------------------------------------------------------------------------

class TestDiverseGoalScenarios:
    def test_create_goal_pipeline(self, pipeline):
        ctx = pipeline.run("Create a microservice for user authentication")
        assert ctx.session_data.get("goal_type") is not None

    def test_modify_goal_pipeline(self, pipeline):
        ctx = pipeline.run("Modify the login endpoint to support OAuth")
        assert ctx.session_data.get("goal_type") is not None

    def test_analyze_goal_pipeline(self, pipeline):
        ctx = pipeline.run("Analyze the performance of the database queries")
        assert ctx.session_data.get("goal_type") is not None

    def test_debug_goal_pipeline(self, pipeline):
        ctx = pipeline.run("Debug the memory leak in the worker process")
        assert ctx.session_data.get("goal_type") is not None

    def test_optimize_goal_pipeline(self, pipeline):
        ctx = pipeline.run("Optimize the image processing pipeline for speed")
        assert ctx.session_data.get("goal_type") is not None

    def test_learn_goal_pipeline(self, pipeline):
        ctx = pipeline.run("Learn about the new API framework")
        assert ctx.session_data.get("goal_type") is not None

    def test_explore_goal_pipeline(self, pipeline):
        ctx = pipeline.run("Explore the codebase to understand the architecture")
        assert isinstance(ctx.session_data.get("recommendation"), dict)

    def test_deploy_goal_pipeline(self, pipeline):
        ctx = pipeline.run("Deploy the latest build to staging")
        assert isinstance(ctx.session_data.get("recommendation"), dict)

    def test_monitor_goal_pipeline(self, pipeline):
        ctx = pipeline.run("Monitor system health metrics")
        assert isinstance(ctx.session_data.get("recommendation"), dict)


# ---------------------------------------------------------------------------
# Edge case scenarios
# ---------------------------------------------------------------------------

class TestEdgeCaseScenarios:
    def test_empty_goal_description(self, pipeline):
        ctx = pipeline.run("")
        assert len(ctx.stage_metrics) >= 1

    def test_very_long_goal(self, pipeline):
        long_text = "Perform " + "very " * 100 + "complex analysis"
        ctx = pipeline.run(long_text)
        assert isinstance(ctx.session_data.get("recommendation"), dict)

    def test_goal_with_special_chars(self, pipeline):
        ctx = pipeline.run("Analyze the @#$% system & debug it!")
        assert isinstance(ctx.session_data.get("recommendation"), dict)

    def test_goal_with_numbers(self, pipeline):
        ctx = pipeline.run("Process 5000 records in 3 batches of 1000 items")
        assert isinstance(ctx.session_data.get("recommendation"), dict)

    def test_multiple_goals_same_session(self, pipeline):
        ctx1 = pipeline.run("Create a module")
        ctx2 = pipeline.run("Debug the module", session_context=ctx1)
        assert ctx2.session_id == ctx1.session_id

    def test_pipeline_with_separate_sessions(self, pipeline):
        ctx1 = pipeline.run("First task")
        ctx2 = pipeline.run("Second task")
        assert ctx1.session_id != ctx2.session_id

    def test_goal_type_interpretation(self, graph):
        interpreter = GoalInterpreter()
        inputs_and_types = [
            ("create a new file", GoalType.CREATE),
            ("build a dashboard", GoalType.CREATE),
            ("modify the config", GoalType.MODIFY),
            ("update the database", GoalType.MODIFY),
            ("analyze the data", GoalType.ANALYZE),
            ("investigate the issue", GoalType.EXPLORE),
            ("debug the crash", GoalType.DEBUG),
            ("fix the bug", GoalType.DEBUG),
            ("optimize the query", GoalType.OPTIMIZE),
            ("tune performance", GoalType.OPTIMIZE),
            ("learn about python", GoalType.LEARN),
            ("study the docs", GoalType.LEARN),
            ("explore the repo", GoalType.EXPLORE),
            ("investigate the codebase", GoalType.EXPLORE),
            ("deploy the app", GoalType.DEPLOY),
            ("deploy the release", GoalType.DEPLOY),
            ("monitor the system", GoalType.MONITOR),
            ("watch the logs", GoalType.MONITOR),
            ("release the update", GoalType.MODIFY),
            ("find the user", GoalType.QUERY),
            ("search the records", GoalType.QUERY),
        ]
        for text, expected in inputs_and_types:
            goal = interpreter.interpret(text)
            assert goal.goal_type == expected, f"Failed for '{text}': expected {expected}, got {goal.goal_type}"


# ---------------------------------------------------------------------------
# Concurrent scenarios
# ---------------------------------------------------------------------------

class TestConcurrentScenarios:
    def test_concurrent_pipeline_runs(self, graph):
        results: list[str] = []
        errors: list[Exception] = []
        lock = threading.Lock()

        def run_pipeline(description: str) -> None:
            try:
                p = IntelligencePipeline(graph_store=GraphStore())
                ctx = p.run(description)
                with lock:
                    results.append(ctx.goal)
            except Exception as e:
                with lock:
                    errors.append(e)

        threads = [
            threading.Thread(target=run_pipeline, args=(f"Goal {i}",))
            for i in range(10)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert len(errors) == 0
        assert len(results) == 10


# ---------------------------------------------------------------------------
# Failure mode scenarios
# ---------------------------------------------------------------------------

class TestFailureModeScenarios:
    def test_planner_with_no_graph(self, graph):
        planner = Planner()
        goal = Goal(description="test", goal_type=GoalType.QUERY)
        plan = planner.create_plan(goal)
        assert plan is not None
        assert plan.count() > 0

    def test_reasoner_with_no_graph(self, graph):
        reasoner = Reasoner(graph_store=None)
        rec = reasoner.recommend(
            context={"goal": "test"},
            strategies=[
                {"name": "a", "description": "A", "scores": {"speed": 0.8, "accuracy": 0.6, "risk": 0.5}},
                {"name": "b", "description": "B", "scores": {"speed": 0.6, "accuracy": 0.9, "risk": 0.3}},
            ],
        )
        assert "winner" in rec
        assert "confidence" in rec

    def test_decision_engine_empty_pool(self):
        engine = DecisionEngine()
        record = engine.select_agent([])
        assert record.winner_id == ""

    def test_reflection_with_no_outcomes(self):
        reflection = Reflection()
        report = reflection.generate_report()
        assert report.total_outcomes == 0
        assert report.failure_rate == 0.0

    def test_planner_with_unknown_goal_type(self, graph):
        planner = Planner()
        goal = Goal(description="weird", goal_type=GoalType.CREATE)
        planner.set_template(GoalType.CREATE, [])
        plan = planner.create_plan(goal)
        assert plan is not None


# ---------------------------------------------------------------------------
# Performance scenarios
# ---------------------------------------------------------------------------

class TestPerformanceScenarios:
    def test_pipeline_latency(self, graph):
        pipeline = IntelligencePipeline(graph_store=graph)
        start = time.time()
        for _ in range(5):
            pipeline.run("Quick test goal")
        elapsed = time.time() - start
        avg_ms = (elapsed / 5) * 1000
        assert avg_ms < 1000, f"Pipeline too slow: {avg_ms:.1f}ms avg"

    def test_concurrent_latency(self, graph):
        start = time.time()
        threads = []
        for i in range(5):
            t = threading.Thread(
                target=lambda: IntelligencePipeline(graph_store=GraphStore()).run("concurrent test")
            )
            threads.append(t)
            t.start()
        for t in threads:
            t.join(timeout=15)
        elapsed = time.time() - start
        assert elapsed < 30


# ---------------------------------------------------------------------------
# Supervisor + Planner integration
# ---------------------------------------------------------------------------

class TestSupervisorPlannerIntegration:
    def test_supervisor_delegates_to_planner(self, graph):
        planner = Planner()
        supervisor = Supervisor(graph_store=graph)
        supervisor._planner_callback = lambda goal, ctx: planner.create_plan(goal)

        goal = supervisor.receive_goal("Create a new feature")
        plan = planner.get_plan(goal.id)
        assert plan is not None
        assert plan.count() > 0

    def test_supervisor_maintains_session(self, graph):
        supervisor = Supervisor(graph_store=graph)
        session = supervisor.create_session(session_id="session_1")
        goal1 = supervisor.receive_goal("First goal", session_id="session_1")
        goal2 = supervisor.receive_goal("Second goal", session_id="session_1")
        session = supervisor.get_session("session_1")
        assert session is not None
        assert len(session.goals) == 2


# ---------------------------------------------------------------------------
# Reflection integration
# ---------------------------------------------------------------------------

class TestReflectionIntegration:
    def test_reflection_tracks_heuristics(self):
        store = Reflection()
        h = Heuristic(name="perf", domain="speed")
        store.heuristic_store.register(h)
        store.heuristic_store.record_success(h.id)
        store.heuristic_store.record_success(h.id)
        assert store.heuristic_store.get(h.id).reliability == 1.0

    def test_reflection_pattern_detection(self):
        reflection = Reflection()
        reflection.analyze(TaskOutcome(task_id="a", success=False, error_message="timeout"))
        reflection.analyze(TaskOutcome(task_id="b", success=False, error_message="timeout"))
        reflection.analyze(TaskOutcome(task_id="c", success=False, error_message="not found"))
        patterns = reflection.outcome_analyzer.get_patterns()
        assert len(patterns) == 2
        timeout_pattern = [p for p in patterns if p.pattern == "timeout"][0]
        assert timeout_pattern.count == 2


# ---------------------------------------------------------------------------
# Decision engine integration
# ---------------------------------------------------------------------------

class TestDecisionEngineIntegration:
    def test_agent_selection_with_weights(self):
        engine = DecisionEngine()
        agents = [
            AgentInfo(agent_id="a1", name="FastAgent", capability=9, cost=1, load=1, reliability=0.9),
            AgentInfo(agent_id="a2", name="CheapAgent", capability=3, cost=9, load=9, reliability=0.5),
            AgentInfo(agent_id="a3", name="ReliableAgent", capability=6, cost=5, load=5, reliability=0.95),
        ]
        record = engine.select_agent(agents)
        assert record.winner_id in ("a1", "a2", "a3")

    def test_all_agents_equal(self):
        engine = DecisionEngine()
        agents = [
            AgentInfo(agent_id="a1", name="A1", capability=5, cost=5, load=5, reliability=0.5),
            AgentInfo(agent_id="a2", name="A2", capability=5, cost=5, load=5, reliability=0.5),
        ]
        record = engine.select_agent(agents)
        # First candidate wins on tie
        assert record.winner_id == "a1"


# ---------------------------------------------------------------------------
# Knowledge Graph integration
# ---------------------------------------------------------------------------

class TestKnowledgeGraphIntegration:
    def test_entity_relationship_roundtrip(self, graph):
        e1 = graph.create_entity(type="agent", name="Bot1")
        e2 = graph.create_entity(type="concept", name="Data")
        rel = graph.create_relationship(type="uses", source_id=e1.id, target_id=e2.id)
        assert rel is not None
        assert graph.entity_count() == 2
        assert graph.relationship_count() == 1

    def test_traversal_from_supervisor_graph(self, graph):
        a = graph.create_entity(type="agent", name="A")
        b = graph.create_entity(type="concept", name="B")
        c = graph.create_entity(type="concept", name="C")
        graph.create_relationship(type="uses", source_id=a.id, target_id=b.id)
        graph.create_relationship(type="uses", source_id=b.id, target_id=c.id)
        paths = graph.bfs(a.id)
        assert len(paths) > 0
