from __future__ import annotations

import threading
import time
from typing import Any, Callable

from app.intelligence.context import SessionContext, StageMetrics
from app.intelligence.decision_engine import AgentInfo, DecisionEngine
from app.intelligence.goal_model import Goal, GoalStatus
from app.intelligence.planner import Planner
from app.intelligence.reasoner import Reasoner
from app.intelligence.reflection import Reflection
from app.intelligence.supervisor import Supervisor
from app.knowledge_graph.store import GraphStore


class IntelligencePipeline:
    """Orchestrates the complete intelligence pipeline:

    Goal → Supervisor → Planner → Reasoner → DecisionEngine → output

    With feedback loop: output → Reflection → Planner/Reasoner updates.

    Thread-safe.  Each pipeline run creates a SessionContext that
    propagates through all stages and collects performance metrics.
    """

    def __init__(
        self,
        graph_store: GraphStore,
        supervisor: Supervisor | None = None,
        planner: Planner | None = None,
        reasoner: Reasoner | None = None,
        decision_engine: DecisionEngine | None = None,
        reflection: Reflection | None = None,
    ) -> None:
        self._graph = graph_store
        self._lock = threading.RLock()

        self.supervisor = supervisor or Supervisor(graph_store)
        self.planner = planner or Planner()
        self.reasoner = reasoner or Reasoner(graph_store)
        self.decision_engine = decision_engine or DecisionEngine()
        self.reflection = reflection or Reflection()

        self._before_stage: dict[str, Callable[[SessionContext], None]] = {}
        self._after_stage: dict[str, Callable[[SessionContext, StageMetrics], None]] = {}

        # Wire supervisor callback to planner
        self.supervisor._planner_callback = self._on_supervisor_delegate

    # ------------------------------------------------------------------
    # Hooks
    # ------------------------------------------------------------------

    def on_before_stage(self, stage: str, callback: Callable[[SessionContext], None]) -> None:
        with self._lock:
            self._before_stage[stage] = callback

    def on_after_stage(self, stage: str, callback: Callable[[SessionContext, StageMetrics], None]) -> None:
        with self._lock:
            self._after_stage[stage] = callback

    def _fire_before(self, stage: str, ctx: SessionContext) -> None:
        cb = self._before_stage.get(stage)
        if cb:
            cb(ctx)

    def _fire_after(self, stage: str, ctx: SessionContext, metrics: StageMetrics) -> None:
        cb = self._after_stage.get(stage)
        if cb:
            cb(ctx, metrics)

    # ------------------------------------------------------------------
    # Pipeline execution
    # ------------------------------------------------------------------

    def run(
        self,
        goal_description: str,
        session_context: SessionContext | None = None,
        agent_pool: list[AgentInfo] | None = None,
    ) -> SessionContext:
        """Execute the full intelligence pipeline for a goal.

        Returns the SessionContext with all stage metrics, plan data,
        and recommendations populated in session_data.
        """
        ctx = session_context or SessionContext(goal=goal_description)
        ctx.goal = goal_description
        goal: Goal | None = None

        # Stage 1: Supervisor (interpret & gather context)
        metrics = ctx.record_stage("supervisor")
        self._fire_before("supervisor", ctx)
        try:
            goal = self.supervisor.receive_goal(goal_description)
            ctx.session_data["goal_id"] = goal.id
            ctx.session_data["goal_type"] = goal.goal_type.value
            ctx.goal_type = goal.goal_type.value
        except Exception as e:
            metrics.success = False
            metrics.error = str(e)
        finally:
            ctx.complete_stage(metrics)
            self._fire_after("supervisor", ctx, metrics)

        if not metrics.success or not goal:
            return ctx

        # Stage 2: Planner (retrieve plan created by supervisor callback)
        metrics = ctx.record_stage("planner")
        self._fire_before("planner", ctx)
        try:
            plan = self.planner.get_plan(goal.id)
            if plan is None:
                plan = self.planner.create_plan(goal)
            ctx.session_data["plan"] = plan.to_dict()
        except Exception as e:
            metrics.success = False
            metrics.error = str(e)
        finally:
            ctx.complete_stage(metrics)
            self._fire_after("planner", ctx, metrics)

        # Stage 3: Reasoner (evaluate strategies)
        metrics = ctx.record_stage("reasoner")
        self._fire_before("reasoner", ctx)
        try:
            strategies = self._build_strategies(goal)
            recommendation = self.reasoner.recommend(
                context={"goal": goal_description, "goal_type": goal.goal_type.value},
                strategies=strategies,
            )
            ctx.session_data["recommendation"] = recommendation
        except Exception as e:
            metrics.success = False
            metrics.error = str(e)
        finally:
            ctx.complete_stage(metrics)
            self._fire_after("reasoner", ctx, metrics)

        # Stage 4: Decision Engine (select agent / strategy)
        if agent_pool:
            metrics = ctx.record_stage("decision_engine")
            self._fire_before("decision_engine", ctx)
            try:
                decision = self.decision_engine.select_agent(
                    agent_pool,
                    context={"goal": goal_description, "goal_type": goal.goal_type.value},
                )
                ctx.session_data["agent_decision"] = decision.to_dict()
            except Exception as e:
                metrics.success = False
                metrics.error = str(e)
            finally:
                ctx.complete_stage(metrics)
                self._fire_after("decision_engine", ctx, metrics)

        return ctx

    def _on_supervisor_delegate(self, goal: Goal, context: Any) -> None:
        """Callback invoked by Supervisor when it delegates to the Planner."""
        self.planner.create_plan(goal)

    def _build_strategies(self, goal: Goal) -> list[dict[str, Any]]:
        return [
            {
                "name": "direct",
                "description": f"Direct execution of {goal.goal_type.value} goal",
                "scores": {"speed": 0.9, "accuracy": 0.7, "risk": 0.6},
            },
            {
                "name": "cautious",
                "description": f"Cautious approach with verification for {goal.goal_type.value} goal",
                "scores": {"speed": 0.5, "accuracy": 0.9, "risk": 0.3},
            },
        ]

    # ------------------------------------------------------------------
    # Feedback loop
    # ------------------------------------------------------------------

    def feedback_loop(self, task_outcome: Any) -> dict[str, Any]:
        """Run the feedback loop with Reflection to update heuristics.

        Returns a report with adjusted weights and recommendations.
        """
        analyzed = self.reflection.analyze(task_outcome)
        report = self.reflection.generate_report()
        return {
            "analyzed_outcome": analyzed,
            "report": report.to_dict(),
            "planner_feedback": self.reflection.feedback_for_planner(),
            "reasoner_feedback": self.reflection.feedback_for_reasoner(),
        }

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    def health(self) -> dict[str, Any]:
        return {
            "alive": True,
            "pipeline_ready": True,
            "modules": {
                "supervisor": True,
                "planner": True,
                "reasoner": True,
                "decision_engine": True,
                "reflection": True,
            },
        }
