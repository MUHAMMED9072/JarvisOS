from __future__ import annotations

import threading
import time
from typing import Any, Callable

from app.core.event_bus import EventBus
from app.intelligence.goal_model import Goal, GoalType
from app.intelligence.task_graph import (
    ResourceEstimate,
    Task,
    TaskGraph,
    TaskPriority,
    TaskStatus,
)

_SUBGOAL_TEMPLATES: dict[GoalType, list[dict[str, Any]]] = {
    GoalType.CREATE: [
        {"name": "requirements_analysis", "description": "Analyze requirements", "compute": 0.2, "time": 30.0},
        {"name": "design_architecture", "description": "Design the architecture", "compute": 0.3, "time": 60.0},
        {"name": "implement_core", "description": "Implement core functionality", "compute": 0.5, "time": 300.0},
        {"name": "write_tests", "description": "Write unit and integration tests", "compute": 0.3, "time": 180.0},
        {"name": "verify_quality", "description": "Verify code quality and standards", "compute": 0.2, "time": 60.0},
    ],
    GoalType.MODIFY: [
        {"name": "understand_existing", "description": "Understand existing implementation", "compute": 0.2, "time": 60.0},
        {"name": "plan_changes", "description": "Plan the changes needed", "compute": 0.2, "time": 30.0},
        {"name": "apply_changes", "description": "Apply the changes", "compute": 0.4, "time": 180.0},
        {"name": "verify_changes", "description": "Verify changes work correctly", "compute": 0.2, "time": 60.0},
    ],
    GoalType.QUERY: [
        {"name": "parse_query", "description": "Parse the query", "compute": 0.1, "time": 5.0},
        {"name": "execute_query", "description": "Execute the query", "compute": 0.2, "time": 30.0},
        {"name": "format_results", "description": "Format query results", "compute": 0.1, "time": 10.0},
    ],
    GoalType.ANALYZE: [
        {"name": "gather_data", "description": "Gather data for analysis", "compute": 0.2, "time": 60.0},
        {"name": "perform_analysis", "description": "Perform the analysis", "compute": 0.4, "time": 120.0},
        {"name": "generate_report", "description": "Generate analysis report", "compute": 0.2, "time": 60.0},
    ],
    GoalType.DEBUG: [
        {"name": "reproduce_issue", "description": "Reproduce the issue", "compute": 0.2, "time": 60.0},
        {"name": "identify_root_cause", "description": "Identify root cause", "compute": 0.3, "time": 120.0},
        {"name": "implement_fix", "description": "Implement the fix", "compute": 0.3, "time": 180.0},
        {"name": "verify_fix", "description": "Verify the fix resolves the issue", "compute": 0.2, "time": 60.0},
    ],
    GoalType.OPTIMIZE: [
        {"name": "profile_current", "description": "Profile current performance", "compute": 0.3, "time": 120.0},
        {"name": "identify_bottlenecks", "description": "Identify bottlenecks", "compute": 0.3, "time": 60.0},
        {"name": "apply_optimizations", "description": "Apply optimizations", "compute": 0.3, "time": 300.0},
        {"name": "measure_improvement", "description": "Measure improvement", "compute": 0.1, "time": 60.0},
    ],
    GoalType.LEARN: [
        {"name": "gather_knowledge", "description": "Gather knowledge", "compute": 0.2, "time": 120.0},
        {"name": "analyze_information", "description": "Analyze information", "compute": 0.3, "time": 180.0},
        {"name": "synthesize_findings", "description": "Synthesize findings", "compute": 0.3, "time": 120.0},
    ],
    GoalType.MONITOR: [
        {"name": "configure_monitoring", "description": "Configure monitoring", "compute": 0.2, "time": 30.0},
        {"name": "start_monitoring", "description": "Start monitoring", "compute": 0.1, "time": 10.0},
        {"name": "analyze_metrics", "description": "Analyze metrics", "compute": 0.3, "time": 60.0},
    ],
    GoalType.EXPLORE: [
        {"name": "survey_area", "description": "Survey the area", "compute": 0.2, "time": 60.0},
        {"name": "deep_dive", "description": "Deep dive into specifics", "compute": 0.3, "time": 180.0},
        {"name": "document_findings", "description": "Document findings", "compute": 0.2, "time": 60.0},
    ],
    GoalType.DEPLOY: [
        {"name": "prepare_environment", "description": "Prepare deployment environment", "compute": 0.2, "time": 60.0},
        {"name": "run_validation", "description": "Run pre-deployment validation", "compute": 0.2, "time": 30.0},
        {"name": "execute_deployment", "description": "Execute deployment", "compute": 0.3, "time": 120.0},
        {"name": "verify_deployment", "description": "Verify deployment", "compute": 0.2, "time": 60.0},
    ],
}

_DEFAULT_SUBGOALS: list[dict[str, Any]] = [
    {"name": "analyze_request", "description": "Analyze the request", "compute": 0.2, "time": 30.0},
    {"name": "execute", "description": "Execute the request", "compute": 0.3, "time": 120.0},
    {"name": "verify", "description": "Verify the results", "compute": 0.2, "time": 30.0},
]


class Planner:
    """Decomposes goals into directed task graphs with resource estimation
    and dependency resolution.

    Uses goal-type-specific templates to generate sub-goals and tasks,
    applies topological sort for execution ordering, identifies critical
    paths, and estimates resources per task.

    Never executes work directly — produces task graphs for downstream
    execution by Agent Manager.

    Thread-safe.
    """

    def __init__(self, event_bus: EventBus | None = None) -> None:
        self._event_bus = event_bus
        self._lock = threading.RLock()
        self._custom_templates: dict[GoalType, list[dict[str, Any]]] = {}
        self._plans: dict[str, TaskGraph] = {}
        self._reasoner_callback: Callable[[TaskGraph], None] | None = None
        self._started_at: float = time.time()

    # ------------------------------------------------------------------
    # Template customization
    # ------------------------------------------------------------------

    def set_template(self, goal_type: GoalType, subgoals: list[dict[str, Any]]) -> None:
        with self._lock:
            self._custom_templates[goal_type] = list(subgoals)

    def get_template(self, goal_type: GoalType) -> list[dict[str, Any]]:
        with self._lock:
            if goal_type in self._custom_templates:
                return list(self._custom_templates[goal_type])
            return list(_SUBGOAL_TEMPLATES.get(goal_type, _DEFAULT_SUBGOALS))

    # ------------------------------------------------------------------
    # Planning
    # ------------------------------------------------------------------

    def create_plan(self, goal: Goal) -> TaskGraph:
        """Create a task graph from a goal.

        Breaks the goal down into tasks based on its type, wires
        dependencies, estimates resources, and computes the critical path.
        """
        with self._lock:
            graph = TaskGraph()
            template = self.get_template(goal.goal_type)

            prev_task_id: str | None = None
            first_task_id: str | None = None

            for i, subgoal in enumerate(template):
                task = Task(
                    name=subgoal["name"],
                    description=subgoal.get("description", ""),
                    priority=TaskPriority.MEDIUM if i > 0 else TaskPriority.HIGH,
                    resource_estimate=ResourceEstimate(
                        compute=subgoal.get("compute", 0.2),
                        memory_mb=subgoal.get("memory", 64.0),
                        time_seconds=subgoal.get("time", 60.0),
                        network=subgoal.get("network", 0.0),
                    ),
                    metadata={"goal_id": goal.id, "step_index": i},
                )

                if prev_task_id is not None:
                    task.depends_on.append(prev_task_id)

                graph.add_task(task)
                prev_task_id = task.id
                if first_task_id is None:
                    first_task_id = task.id

            self._plans[goal.id] = graph

            self._publish("plan.created", {
                "goal_id": goal.id,
                "task_count": graph.count(),
                "critical_path": graph.critical_path(),
                "critical_path_duration": graph.critical_path_duration(),
                "parallel_groups": len(graph.find_parallelizable()),
            })

            return graph

    def get_plan(self, goal_id: str) -> TaskGraph | None:
        with self._lock:
            return self._plans.get(goal_id)

    def list_plans(self) -> list[tuple[str, TaskGraph]]:
        with self._lock:
            return list(self._plans.items())

    # ------------------------------------------------------------------
    # Resource estimation
    # ------------------------------------------------------------------

    def estimate_total_resources(self, graph: TaskGraph) -> ResourceEstimate:
        total = ResourceEstimate()
        for task in graph.list_tasks():
            total.compute += task.resource_estimate.compute
            total.memory_mb += task.resource_estimate.memory_mb
            total.time_seconds += task.resource_estimate.time_seconds
            total.network += task.resource_estimate.network
        return total

    # ------------------------------------------------------------------
    # Reasoner integration
    # ------------------------------------------------------------------

    def set_reasoner_callback(self, callback: Callable[[TaskGraph], None]) -> None:
        with self._lock:
            self._reasoner_callback = callback

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    def health(self) -> dict[str, Any]:
        with self._lock:
            return {
                "alive": True,
                "uptime_seconds": time.time() - self._started_at,
                "plans_created": len(self._plans),
            }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _publish(self, event: str, data: dict[str, Any]) -> None:
        if self._event_bus:
            try:
                self._event_bus.publish(f"planner.{event}", data)
            except Exception:
                pass
