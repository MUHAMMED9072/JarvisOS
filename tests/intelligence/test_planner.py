from __future__ import annotations

import pytest

from app.intelligence.goal_model import Goal, GoalType
from app.intelligence.planner import Planner


class TestPlanner:
    def test_initial_health(self):
        p = Planner()
        h = p.health()
        assert h["alive"]
        assert h["plans_created"] == 0

    def test_create_plan_returns_task_graph(self):
        p = Planner()
        goal = Goal(description="Build a trading bot", goal_type=GoalType.CREATE)
        graph = p.create_plan(goal)
        assert graph.count() > 0
        assert goal.id in [gid for gid, _ in p.list_plans()]

    def test_create_plan_create_type(self):
        p = Planner()
        goal = Goal(description="Build a tool", goal_type=GoalType.CREATE)
        graph = p.create_plan(goal)
        assert graph.count() >= 4

    def test_create_plan_query_type(self):
        p = Planner()
        goal = Goal(description="Find data", goal_type=GoalType.QUERY)
        graph = p.create_plan(goal)
        assert graph.count() == 3

    def test_create_plan_debug_type(self):
        p = Planner()
        goal = Goal(description="Fix bug", goal_type=GoalType.DEBUG)
        graph = p.create_plan(goal)
        assert graph.count() == 4

    def test_create_plan_unknown_type(self):
        p = Planner()
        goal = Goal(description="Hello", goal_type=GoalType.UNKNOWN)
        graph = p.create_plan(goal)
        assert graph.count() == 3

    def test_create_plan_wires_dependencies(self):
        p = Planner()
        goal = Goal(description="test", goal_type=GoalType.CREATE)
        graph = p.create_plan(goal)
        levels = graph.topological_sort()
        # Should have multiple levels (sequential dependencies)
        assert len(levels) >= 2

    def test_create_plan_has_resource_estimates(self):
        p = Planner()
        goal = Goal(description="test", goal_type=GoalType.CREATE)
        graph = p.create_plan(goal)
        for task in graph.list_tasks():
            assert task.resource_estimate.time_seconds > 0

    def test_create_plan_has_critical_path(self):
        p = Planner()
        goal = Goal(description="test", goal_type=GoalType.CREATE)
        graph = p.create_plan(goal)
        path = graph.critical_path()
        assert len(path) > 0

    def test_get_plan(self):
        p = Planner()
        goal = Goal(description="test", goal_type=GoalType.CREATE)
        p.create_plan(goal)
        graph = p.get_plan(goal.id)
        assert graph is not None
        assert graph.count() > 0

    def test_get_plan_missing(self):
        p = Planner()
        assert p.get_plan("nonexistent") is None

    def test_list_plans(self):
        p = Planner()
        g1 = Goal(description="g1", goal_type=GoalType.CREATE)
        g2 = Goal(description="g2", goal_type=GoalType.QUERY)
        p.create_plan(g1)
        p.create_plan(g2)
        plans = p.list_plans()
        assert len(plans) == 2

    def test_set_template(self):
        p = Planner()
        goal = Goal(description="test", goal_type=GoalType.CREATE)
        p.set_template(GoalType.CREATE, [
            {"name": "custom_step", "description": "Custom", "compute": 0.5, "time": 100},
        ])
        graph = p.create_plan(goal)
        assert graph.count() == 1
        task = graph.list_tasks()[0]
        assert task.name == "custom_step"

    def test_get_template_custom(self):
        p = Planner()
        custom = [{"name": "step1", "description": "S1", "compute": 0.1, "time": 10}]
        p.set_template(GoalType.CREATE, custom)
        tmpl = p.get_template(GoalType.CREATE)
        assert tmpl == custom

    def test_get_template_default(self):
        p = Planner()
        tmpl = p.get_template(GoalType.CREATE)
        assert len(tmpl) >= 4

    def test_get_template_unknown(self):
        p = Planner()
        tmpl = p.get_template(GoalType.UNKNOWN)
        assert len(tmpl) == 3

    def test_estimate_total_resources(self):
        p = Planner()
        goal = Goal(description="test", goal_type=GoalType.CREATE)
        graph = p.create_plan(goal)
        total = p.estimate_total_resources(graph)
        assert total.compute > 0
        assert total.time_seconds > 0

    def test_event_bus_publishing(self):
        from app.core.event_bus import EventBus
        bus = EventBus()
        received: list[dict] = []
        bus.subscribe("planner.plan.created", lambda d: received.append(d))
        p = Planner(event_bus=bus)
        goal = Goal(description="test", goal_type=GoalType.CREATE)
        p.create_plan(goal)
        assert len(received) == 1
        assert received[0]["task_count"] > 0

    def test_thread_safe(self):
        import threading
        p = Planner()
        goals = [Goal(description=f"Goal {i}", goal_type=GoalType.CREATE) for i in range(10)]
        errors = []

        def plan(goal):
            try:
                g = p.create_plan(goal)
                g.topological_sort()
                g.critical_path()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=plan, args=(g,)) for g in goals]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
