from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AgentRole(Enum):
    LEAD = "lead"
    WORKER = "worker"
    REVIEWER = "reviewer"
    COORDINATOR = "coordinator"
    OBSERVER = "observer"


class WorkflowStatus(Enum):
    PENDING = "pending"
    ASSIGNING = "assigning"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"


class ConflictSeverity(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class AgentTeam:
    team_id: str = ""
    name: str = ""
    members: list[dict[str, Any]] = field(default_factory=list)
    created_at: float = 0.0
    objective: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "team_id": self.team_id,
            "name": self.name,
            "members": list(self.members),
            "created_at": self.created_at,
            "objective": self.objective,
        }


@dataclass
class WorkflowStep:
    step_id: str = ""
    name: str = ""
    assigned_agent: str = ""
    role: str = "worker"
    depends_on: list[str] = field(default_factory=list)
    status: str = "pending"
    result: dict[str, Any] = field(default_factory=dict)
    started_at: float = 0.0
    completed_at: float = 0.0
    retry_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "name": self.name,
            "assigned_agent": self.assigned_agent,
            "role": self.role,
            "depends_on": list(self.depends_on),
            "status": self.status,
            "result": dict(self.result),
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "retry_count": self.retry_count,
        }


@dataclass
class Workflow:
    workflow_id: str = ""
    name: str = ""
    description: str = ""
    status: WorkflowStatus = WorkflowStatus.PENDING
    team: AgentTeam | None = None
    steps: list[WorkflowStep] = field(default_factory=list)
    created_at: float = 0.0
    updated_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "name": self.name,
            "description": self.description,
            "status": self.status.value,
            "team": self.team.to_dict() if self.team else None,
            "steps": [s.to_dict() for s in self.steps],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class ConflictRecord:
    conflict_id: str = ""
    workflow_id: str = ""
    between_agents: list[str] = field(default_factory=list)
    description: str = ""
    severity: ConflictSeverity = ConflictSeverity.LOW
    resolution: str = ""
    resolved: bool = False
    timestamp: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "conflict_id": self.conflict_id,
            "workflow_id": self.workflow_id,
            "between_agents": list(self.between_agents),
            "description": self.description,
            "severity": self.severity.value,
            "resolution": self.resolution,
            "resolved": self.resolved,
            "timestamp": self.timestamp,
        }


class WorkflowOrchestrator:
    """Orchestrates multi-agent workflows.

    Forms agent teams, assigns roles, tracks progress,
    mediates conflicts, and handles failure recovery.
    """

    def __init__(
        self,
        graph_store: Any = None,
        event_bus: Any = None,
        agent_registry: Any = None,
        governance: Any = None,
    ) -> None:
        self._graph = graph_store
        self._bus = event_bus
        self._agent_registry = agent_registry
        self._governance = governance
        self._lock = threading.RLock()
        self._workflows: dict[str, Workflow] = {}
        self._conflicts: dict[str, ConflictRecord] = {}
        self._teams: dict[str, AgentTeam] = {}
        self._available_agents: list[str] = []

    def register_agent_available(self, agent_id: str) -> None:
        with self._lock:
            if agent_id not in self._available_agents:
                self._available_agents.append(agent_id)

    def unregister_agent(self, agent_id: str) -> None:
        with self._lock:
            if agent_id in self._available_agents:
                self._available_agents.remove(agent_id)

    def create_workflow(
        self,
        name: str,
        description: str = "",
        steps: list[dict[str, Any]] | None = None,
    ) -> Workflow:
        workflow_id = uuid.uuid4().hex[:16]
        workflow = Workflow(
            workflow_id=workflow_id,
            name=name,
            description=description,
            status=WorkflowStatus.PENDING,
            created_at=time.time(),
            updated_at=time.time(),
        )
        if steps:
            workflow.steps = [
                WorkflowStep(
                    step_id=uuid.uuid4().hex[:16],
                    name=s.get("name", f"Step {i}"),
                    assigned_agent=s.get("assigned_agent", ""),
                    role=s.get("role", "worker"),
                    depends_on=s.get("depends_on", []),
                )
                for i, s in enumerate(steps)
            ]
        with self._lock:
            self._workflows[workflow_id] = workflow
        if self._bus:
            self._bus.publish("autonomy.workflow.created", workflow.to_dict())
        if self._graph:
            try:
                self._graph.create_entity(
                    type="workflow",
                    name=name,
                    properties=workflow.to_dict(),
                )
            except Exception:
                pass
        return workflow

    def get_workflow(self, workflow_id: str) -> Workflow | None:
        with self._lock:
            return self._workflows.get(workflow_id)

    def form_team(
        self,
        workflow_id: str,
        required_capabilities: list[str] | None = None,
        team_name: str = "",
    ) -> AgentTeam | None:
        workflow = self.get_workflow(workflow_id)
        if not workflow:
            return None

        team_id = uuid.uuid4().hex[:16]
        members: list[dict[str, Any]] = []

        with self._lock:
            available = list(self._available_agents)

        for i, agent_id in enumerate(available):
            role = AgentRole.WORKER
            if i == 0:
                role = AgentRole.LEAD
            elif i == len(available) - 1:
                role = AgentRole.REVIEWER

            members.append({
                "agent_id": agent_id,
                "role": role.value,
                "joined_at": time.time(),
            })

        if not members:
            members.append({
                "agent_id": "coordinator",
                "role": AgentRole.COORDINATOR.value,
                "joined_at": time.time(),
            })

        team = AgentTeam(
            team_id=team_id,
            name=team_name or f"Team-{workflow_id[:8]}",
            members=members,
            created_at=time.time(),
            objective=workflow.description,
        )

        with self._lock:
            workflow.team = team
            self._teams[team_id] = team
            workflow.status = WorkflowStatus.ASSIGNING
            workflow.updated_at = time.time()

        if self._bus:
            self._bus.publish("autonomy.team.formed", team.to_dict())
        return team

    def get_team(self, team_id: str) -> AgentTeam | None:
        with self._lock:
            return self._teams.get(team_id)

    def assign_step(
        self,
        workflow_id: str,
        step_id: str,
        agent_id: str,
    ) -> bool:
        workflow = self.get_workflow(workflow_id)
        if not workflow:
            return False
        with self._lock:
            for step in workflow.steps:
                if step.step_id == step_id:
                    step.assigned_agent = agent_id
                    workflow.updated_at = time.time()
                    break
            else:
                return False
        return True

    def start_workflow(self, workflow_id: str) -> bool:
        workflow = self.get_workflow(workflow_id)
        if not workflow:
            return False
        with self._lock:
            if workflow.status != WorkflowStatus.ASSIGNING:
                # Auto-transition from PENDING to ASSIGNING then RUNNING
                if workflow.status == WorkflowStatus.PENDING:
                    workflow.status = WorkflowStatus.ASSIGNING
            workflow.status = WorkflowStatus.RUNNING
            for step in workflow.steps:
                step.started_at = time.time()
            workflow.updated_at = time.time()
        if self._bus:
            self._bus.publish("autonomy.workflow.started", {
                "workflow_id": workflow_id,
            })
        return True

    def complete_step(
        self,
        workflow_id: str,
        step_id: str,
        result: dict[str, Any] | None = None,
    ) -> bool:
        workflow = self.get_workflow(workflow_id)
        if not workflow:
            return False
        with self._lock:
            for step in workflow.steps:
                if step.step_id == step_id:
                    step.status = "completed"
                    step.result = result or {}
                    step.completed_at = time.time()
                    workflow.updated_at = time.time()
                    break
            else:
                return False
        self._check_workflow_completion(workflow_id)
        if self._bus:
            self._bus.publish("autonomy.workflow.step_completed", {
                "workflow_id": workflow_id,
                "step_id": step_id,
            })
        return True

    def fail_step(
        self,
        workflow_id: str,
        step_id: str,
        error: str,
        reassign: bool = True,
    ) -> bool:
        workflow = self.get_workflow(workflow_id)
        if not workflow:
            return False
        with self._lock:
            for step in workflow.steps:
                if step.step_id == step_id:
                    step.status = "failed"
                    step.result = {"error": error}
                    step.completed_at = time.time()
                    step.retry_count += 1
                    workflow.updated_at = time.time()
                    if reassign and step.retry_count < 3:
                        # Find another agent
                        with self._lock:
                            available = list(self._available_agents)
                        if step.assigned_agent in available:
                            available.remove(step.assigned_agent)
                        if available:
                            step.assigned_agent = available[0]
                            step.status = "pending"
                            step.started_at = 0.0
                            step.completed_at = 0.0
                    break
            else:
                return False
        if self._bus:
            self._bus.publish("autonomy.workflow.step_failed", {
                "workflow_id": workflow_id,
                "step_id": step_id,
                "error": error,
            })
        return True

    def _check_workflow_completion(self, workflow_id: str) -> bool:
        workflow = self.get_workflow(workflow_id)
        if not workflow:
            return False
        with self._lock:
            all_done = all(
                s.status in ("completed", "failed", "skipped")
                for s in workflow.steps
            )
            if all_done:
                has_failures = any(s.status == "failed" for s in workflow.steps)
                workflow.status = WorkflowStatus.FAILED if has_failures else WorkflowStatus.COMPLETED
                workflow.updated_at = time.time()
        if all_done and self._bus:
            self._bus.publish("autonomy.workflow.completed", {
                "workflow_id": workflow_id,
                "status": workflow.status.value,
            })
        return all_done

    def report_conflict(
        self,
        workflow_id: str,
        between_agents: list[str],
        description: str,
        severity: ConflictSeverity = ConflictSeverity.MEDIUM,
    ) -> ConflictRecord:
        conflict = ConflictRecord(
            conflict_id=uuid.uuid4().hex[:16],
            workflow_id=workflow_id,
            between_agents=list(between_agents),
            description=description,
            severity=severity,
            timestamp=time.time(),
        )
        with self._lock:
            self._conflicts[conflict.conflict_id] = conflict
        if self._bus:
            self._bus.publish("autonomy.conflict.reported", conflict.to_dict())
        return conflict

    def resolve_conflict(
        self,
        conflict_id: str,
        resolution: str,
    ) -> bool:
        with self._lock:
            conflict = self._conflicts.get(conflict_id)
            if not conflict:
                return False
            conflict.resolution = resolution
            conflict.resolved = True
        if self._bus:
            self._bus.publish("autonomy.conflict.resolved", {
                "conflict_id": conflict_id,
                "resolution": resolution,
            })
        return True

    def pause_workflow(self, workflow_id: str) -> bool:
        workflow = self.get_workflow(workflow_id)
        if not workflow or workflow.status != WorkflowStatus.RUNNING:
            return False
        with self._lock:
            workflow.status = WorkflowStatus.PAUSED
            workflow.updated_at = time.time()
        if self._bus:
            self._bus.publish("autonomy.workflow.paused", {
                "workflow_id": workflow_id,
            })
        return True

    def resume_workflow(self, workflow_id: str) -> bool:
        workflow = self.get_workflow(workflow_id)
        if not workflow or workflow.status != WorkflowStatus.PAUSED:
            return False
        with self._lock:
            workflow.status = WorkflowStatus.RUNNING
            workflow.updated_at = time.time()
        if self._bus:
            self._bus.publish("autonomy.workflow.resumed", {
                "workflow_id": workflow_id,
            })
        return True

    def get_next_ready_steps(self, workflow_id: str) -> list[WorkflowStep]:
        workflow = self.get_workflow(workflow_id)
        if not workflow:
            return []
        ready: list[WorkflowStep] = []
        with self._lock:
            for step in workflow.steps:
                if step.status != "pending":
                    continue
                deps_met = all(
                    any(
                        s.step_id == dep and s.status == "completed"
                        for s in workflow.steps
                    )
                    for dep in step.depends_on
                )
                if deps_met:
                    ready.append(step)
        return ready

    def get_workflow_progress(self, workflow_id: str) -> dict[str, Any]:
        workflow = self.get_workflow(workflow_id)
        if not workflow:
            return {}
        with self._lock:
            total = len(workflow.steps)
            completed = sum(1 for s in workflow.steps if s.status == "completed")
            failed = sum(1 for s in workflow.steps if s.status == "failed")
            running = sum(1 for s in workflow.steps if s.status == "running")
            pending = sum(1 for s in workflow.steps if s.status == "pending")
        return {
            "workflow_id": workflow_id,
            "name": workflow.name,
            "status": workflow.status.value,
            "total_steps": total,
            "completed": completed,
            "failed": failed,
            "running": running,
            "pending": pending,
            "progress_pct": round((completed / total * 100) if total else 0, 1),
        }

    def get_statistics(self) -> dict[str, Any]:
        with self._lock:
            total_wf = len(self._workflows)
            running = sum(
                1 for w in self._workflows.values()
                if w.status == WorkflowStatus.RUNNING
            )
            completed = sum(
                1 for w in self._workflows.values()
                if w.status == WorkflowStatus.COMPLETED
            )
            failed = sum(
                1 for w in self._workflows.values()
                if w.status == WorkflowStatus.FAILED
            )
            total_conflicts = len(self._conflicts)
            resolved = sum(1 for c in self._conflicts.values() if c.resolved)
        return {
            "total_workflows": total_wf,
            "running": running,
            "completed": completed,
            "failed": failed,
            "total_conflicts": total_conflicts,
            "resolved_conflicts": resolved,
        }

    def health(self) -> dict[str, Any]:
        return {"alive": True}
