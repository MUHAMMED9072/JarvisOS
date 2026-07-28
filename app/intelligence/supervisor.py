from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from app.core.event_bus import EventBus
from app.intelligence.context_assembler import Context, ContextAssembler
from app.intelligence.goal_model import Goal, GoalInterpreter, GoalStatus, GoalType
from app.knowledge_graph.store import GraphStore


@dataclass
class Session:
    id: str = ""
    goals: list[Goal] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "goals": [g.to_dict() for g in self.goals],
            "goal_count": len(self.goals),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": dict(self.metadata),
        }


@dataclass
class Delegation:
    target: str = ""
    goal_id: str = ""
    context: dict[str, Any] = field(default_factory=dict)
    delegated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "goal_id": self.goal_id,
            "context": dict(self.context),
            "delegated_at": self.delegated_at,
        }


class Supervisor:
    """Top-level intelligence that interprets user goals, gathers context
    from the Knowledge Graph, and delegates to the Planner.

    Key design rules:
      - Never executes work directly (verified by static analysis guideline)
      - All delegation decisions are auditable
      - Maintains session context across multiple goal iterations
      - Uses working memory (current session) and long-term memory (KG)

    Thread-safe.
    """

    def __init__(
        self,
        graph_store: GraphStore,
        event_bus: EventBus | None = None,
    ) -> None:
        self._graph = graph_store
        self._event_bus = event_bus
        self._interpreter = GoalInterpreter()
        self._context_assembler = ContextAssembler(graph_store)
        self._lock = threading.RLock()

        self._sessions: dict[str, Session] = {}
        self._goals: dict[str, Goal] = {}
        self._delegations: list[Delegation] = []
        self._planner_callback: Callable[[Goal, Context], None] | None = None
        self._started_at: float = time.time()

    @property
    def interpreter(self) -> GoalInterpreter:
        return self._interpreter

    @property
    def context_assembler(self) -> ContextAssembler:
        return self._context_assembler

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    def __init__(
        self,
        graph_store: GraphStore,
        event_bus: EventBus | None = None,
    ) -> None:
        self._graph = graph_store
        self._event_bus = event_bus
        self._interpreter = GoalInterpreter()
        self._context_assembler = ContextAssembler(graph_store)
        self._lock = threading.RLock()

        self._sessions: dict[str, Session] = {}
        self._goals: dict[str, Goal] = {}
        self._delegations: list[Delegation] = []
        self._planner_callback: Callable[[Goal, Context], None] | None = None
        self._started_at: float = time.time()
        self._session_counter: int = 0

    def create_session(self, session_id: str = "") -> Session:
        with self._lock:
            self._session_counter += 1
            sid = session_id or f"session_{int(time.time() * 1000)}_{self._session_counter}"
            session = Session(id=sid)
            self._sessions[sid] = session
            self._publish("session.created", {"session_id": sid})
            return session

    def get_session(self, session_id: str) -> Session | None:
        with self._lock:
            return self._sessions.get(session_id)

    def list_sessions(self) -> list[Session]:
        with self._lock:
            return list(self._sessions.values())

    # ------------------------------------------------------------------
    # Goal processing
    # ------------------------------------------------------------------

    def receive_goal(
        self,
        description: str,
        session_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> Goal:
        """Receive and process a goal from the Executive Controller.

        Steps:
          1. Interpret the goal description (type, intent, parameters)
          2. Gather context from the Knowledge Graph
          3. Create/update session
          4. Delegate to the Planner via callback
          5. Return the Goal
        """
        with self._lock:
            goal = self._interpreter.interpret(description)
            if metadata:
                goal.metadata.update(metadata)

            if session_id:
                goal.session_id = session_id
                session = self._sessions.get(session_id)
                if session:
                    session.goals.append(goal)
                    session.updated_at = time.time()
            else:
                session = self.create_session()
                goal.session_id = session.id
                session.goals.append(goal)

            self._goals[goal.id] = goal
            goal.status = GoalStatus.INTERPRETING
            self._publish("goal.received", goal.to_dict())

            context = self._context_assembler.assemble(goal.description, goal.goal_type.value)

            goal.status = GoalStatus.PLANNING
            self._publish("goal.context_gathered", {
                "goal_id": goal.id,
                "context": context.to_dict(),
            })

            if self._planner_callback:
                self._planner_callback(goal, context)
                self._delegations.append(Delegation(
                    target="planner",
                    goal_id=goal.id,
                    context={"entity_count": len(context.relevant_entities)},
                ))

            self._publish("goal.delegated", {
                "goal_id": goal.id,
                "target": "planner",
                "context_size": len(context.relevant_entities),
            })

            return goal

    def get_goal(self, goal_id: str) -> Goal | None:
        with self._lock:
            return self._goals.get(goal_id)

    def list_goals(self, session_id: str | None = None) -> list[Goal]:
        with self._lock:
            if session_id:
                session = self._sessions.get(session_id)
                if session:
                    return list(session.goals)
                return []
            return list(self._goals.values())

    def update_goal_status(self, goal_id: str, status: GoalStatus) -> bool:
        with self._lock:
            goal = self._goals.get(goal_id)
            if goal is None:
                return False
            goal.status = status
            goal.updated_at = time.time()
            self._publish("goal.status_changed", {"goal_id": goal_id, "status": status.value})
            return True

    # ------------------------------------------------------------------
    # Delegation
    # ------------------------------------------------------------------

    def set_planner_callback(self, callback: Callable[[Goal, Context], None]) -> None:
        with self._lock:
            self._planner_callback = callback

    def list_delegations(self) -> list[Delegation]:
        with self._lock:
            return list(self._delegations)

    def get_delegation_count(self) -> int:
        with self._lock:
            return len(self._delegations)

    # ------------------------------------------------------------------
    # Working memory
    # ------------------------------------------------------------------

    def get_working_memory(self, session_id: str) -> dict[str, Any]:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return {}
            return {
                "session_id": session.id,
                "goal_count": len(session.goals),
                "recent_goals": [g.to_dict() for g in session.goals[-5:]],
                "metadata": dict(session.metadata),
            }

    # ------------------------------------------------------------------
    # Health & stats
    # ------------------------------------------------------------------

    def health(self) -> dict[str, Any]:
        with self._lock:
            return {
                "alive": True,
                "uptime_seconds": time.time() - self._started_at,
                "sessions": len(self._sessions),
                "goals": len(self._goals),
                "delegations": len(self._delegations),
                "planner_registered": self._planner_callback is not None,
            }

    def get_stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "total_sessions": len(self._sessions),
                "total_goals": len(self._goals),
                "total_delegations": len(self._delegations),
                "planner_registered": self._planner_callback is not None,
            }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _publish(self, event: str, data: dict[str, Any]) -> None:
        if self._event_bus:
            try:
                self._event_bus.publish(f"supervisor.{event}", data)
            except Exception:
                pass
