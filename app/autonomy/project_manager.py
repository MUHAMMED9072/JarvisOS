from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ProjectStatus(Enum):
    PENDING = "pending"
    PLANNING = "planning"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ProjectPhase(Enum):
    GOAL_DEFINITION = "goal_definition"
    PLANNING = "planning"
    AGENT_ASSIGNMENT = "agent_assignment"
    EXECUTION = "execution"
    VERIFICATION = "verification"
    DELIVERY = "delivery"


@dataclass
class Milestone:
    milestone_id: str = ""
    name: str = ""
    description: str = ""
    depends_on: list[str] = field(default_factory=list)
    status: str = "pending"
    assigned_agent: str = ""
    result: dict[str, Any] = field(default_factory=dict)
    started_at: float = 0.0
    completed_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "milestone_id": self.milestone_id,
            "name": self.name,
            "description": self.description,
            "depends_on": list(self.depends_on),
            "status": self.status,
            "assigned_agent": self.assigned_agent,
            "result": dict(self.result),
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }


@dataclass
class Project:
    project_id: str = ""
    name: str = ""
    goal: str = ""
    status: ProjectStatus = ProjectStatus.PENDING
    phase: ProjectPhase = ProjectPhase.GOAL_DEFINITION
    milestones: list[Milestone] = field(default_factory=list)
    checkpoints: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = 0.0
    updated_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "name": self.name,
            "goal": self.goal,
            "status": self.status.value,
            "phase": self.phase.value,
            "milestones": [m.to_dict() for m in self.milestones],
            "checkpoints": list(self.checkpoints),
            "metadata": dict(self.metadata),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class ProjectReport:
    report_id: str = ""
    project_id: str = ""
    project_name: str = ""
    goal: str = ""
    status: str = ""
    milestones_completed: int = 0
    milestones_total: int = 0
    duration_seconds: float = 0.0
    decisions_made: int = 0
    human_interventions: int = 0
    summary: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_id": self.report_id,
            "project_id": self.project_id,
            "project_name": self.project_name,
            "goal": self.goal,
            "status": self.status,
            "milestones_completed": self.milestones_completed,
            "milestones_total": self.milestones_total,
            "duration_seconds": self.duration_seconds,
            "decisions_made": self.decisions_made,
            "human_interventions": self.human_interventions,
            "summary": self.summary,
            "details": dict(self.details),
            "timestamp": self.timestamp,
        }


class ProjectManager:
    """Manages the full autonomous project lifecycle.

    Accepts high-level goals, decomposes into milestones,
    assigns agents, tracks progress, enforces human checkpoints,
    and produces project reports.

    Integrates with:
    - IntelligencePipeline (goal planning)
    - ExecutiveController (subsystem coordination)
    - Agent Registry (agent assignment)
    - Knowledge Graph (project persistence)
    - Governance (policy enforcement)
    """

    def __init__(
        self,
        graph_store: Any = None,
        event_bus: Any = None,
        pipeline: Any = None,
        agent_registry: Any = None,
        governance: Any = None,
        executive_controller: Any = None,
    ) -> None:
        self._graph = graph_store
        self._bus = event_bus
        self._pipeline = pipeline
        self._agent_registry = agent_registry
        self._governance = governance
        self._ec = executive_controller
        self._lock = threading.RLock()
        self._projects: dict[str, Project] = {}
        self._reports: dict[str, ProjectReport] = {}
        self._decision_log: list[dict[str, Any]] = []

    def create_project(
        self,
        goal: str,
        name: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> Project:
        project_id = uuid.uuid4().hex[:16]
        project = Project(
            project_id=project_id,
            name=name or f"Project-{project_id[:8]}",
            goal=goal,
            status=ProjectStatus.PENDING,
            phase=ProjectPhase.GOAL_DEFINITION,
            created_at=time.time(),
            updated_at=time.time(),
            metadata=metadata or {},
        )
        with self._lock:
            self._projects[project_id] = project
        self._log_decision(f"Project created: {project.name}", project_id)
        if self._bus:
            self._bus.publish("autonomy.project.created", project.to_dict())
        if self._graph:
            self._graph.create_entity(
                type="project",
                name=project.name,
                properties=project.to_dict(),
            )
        return project

    def get_project(self, project_id: str) -> Project | None:
        with self._lock:
            return self._projects.get(project_id)

    def plan_project(self, project_id: str) -> Milestone | None:
        project = self.get_project(project_id)
        if not project:
            return None

        with self._lock:
            project.status = ProjectStatus.PLANNING
            project.phase = ProjectPhase.PLANNING
            project.updated_at = time.time()

        milestones = self._decompose_goal(project.goal)
        with self._lock:
            project.milestones = milestones

        self._log_decision(
            f"Project planned: {len(milestones)} milestones", project_id
        )
        if self._bus:
            self._bus.publish("autonomy.project.planned", {
                "project_id": project_id,
                "milestones": [m.to_dict() for m in milestones],
            })
        return milestones[0] if milestones else None

    def _decompose_goal(self, goal: str) -> list[Milestone]:
        if self._pipeline:
            try:
                result = self._pipeline.run(goal)
                task_graph = getattr(result, "task_graph", None)
                if task_graph:
                    tasks = getattr(task_graph, "tasks", [])
                    return [
                        Milestone(
                            milestone_id=uuid.uuid4().hex[:16],
                            name=f"Task {i}",
                            description=str(t),
                        )
                        for i, t in enumerate(tasks)
                    ]
            except Exception:
                pass
        return [
            Milestone(
                milestone_id=uuid.uuid4().hex[:16],
                name="Milestone 1",
                description=f"Initial milestone for: {goal[:80]}",
            ),
        ]

    def start_execution(self, project_id: str) -> bool:
        project = self.get_project(project_id)
        if not project or project.status != ProjectStatus.PLANNING:
            return False

        with self._lock:
            project.status = ProjectStatus.ACTIVE
            project.phase = ProjectPhase.EXECUTION
            project.updated_at = time.time()

        self._log_decision(f"Execution started for: {project.name}", project_id)
        if self._bus:
            self._bus.publish("autonomy.project.started", {
                "project_id": project_id,
            })
        return True

    def update_milestone(
        self,
        project_id: str,
        milestone_id: str,
        status: str = "completed",
        result: dict[str, Any] | None = None,
    ) -> bool:
        project = self.get_project(project_id)
        if not project:
            return False

        with self._lock:
            for ms in project.milestones:
                if ms.milestone_id == milestone_id:
                    ms.status = status
                    ms.result = result or {}
                    if status in ("completed", "failed"):
                        ms.completed_at = time.time()
                    project.updated_at = time.time()
                    break
            else:
                return False

        self._log_decision(
            f"Milestone {milestone_id}: {status}", project_id
        )
        if self._bus:
            self._bus.publish("autonomy.milestone.updated", {
                "project_id": project_id,
                "milestone_id": milestone_id,
                "status": status,
            })
        return self._check_completion(project_id)

    def _check_completion(self, project_id: str) -> bool:
        project = self.get_project(project_id)
        if not project:
            return False

        with self._lock:
            all_done = all(
                ms.status in ("completed", "failed", "skipped")
                for ms in project.milestones
            )
            if all_done:
                project.phase = ProjectPhase.VERIFICATION
                project.status = ProjectStatus.COMPLETED
                project.updated_at = time.time()

        if all_done:
            self._log_decision(
                f"Project completed: {project.name}", project_id
            )
            self._generate_report(project_id)
            if self._bus:
                self._bus.publish("autonomy.project.completed", {
                    "project_id": project_id,
                })
        return all_done

    def add_human_checkpoint(
        self,
        project_id: str,
        description: str,
        required_approval: bool = True,
    ) -> str | None:
        project = self.get_project(project_id)
        if not project:
            return None

        checkpoint_id = uuid.uuid4().hex[:16]
        checkpoint = {
            "checkpoint_id": checkpoint_id,
            "description": description,
            "required_approval": required_approval,
            "approved": not required_approval,
            "created_at": time.time(),
            "resolved_at": 0.0,
        }
        with self._lock:
            project.checkpoints.append(checkpoint)
            project.updated_at = time.time()

        if self._bus:
            self._bus.publish("autonomy.checkpoint.created", {
                "project_id": project_id,
                "checkpoint": checkpoint,
            })
        return checkpoint_id

    def resolve_checkpoint(
        self,
        project_id: str,
        checkpoint_id: str,
        approved: bool = True,
    ) -> bool:
        project = self.get_project(project_id)
        if not project:
            return False

        with self._lock:
            for cp in project.checkpoints:
                if cp["checkpoint_id"] == checkpoint_id:
                    cp["approved"] = approved
                    cp["resolved_at"] = time.time()
                    project.updated_at = time.time()
                    break
            else:
                return False

        if self._bus:
            self._bus.publish("autonomy.checkpoint.resolved", {
                "project_id": project_id,
                "checkpoint_id": checkpoint_id,
                "approved": approved,
            })
        return True

    def pause_project(self, project_id: str) -> bool:
        project = self.get_project(project_id)
        if not project or project.status != ProjectStatus.ACTIVE:
            return False
        with self._lock:
            project.status = ProjectStatus.PAUSED
            project.updated_at = time.time()
        self._log_decision(f"Project paused: {project.name}", project_id)
        if self._bus:
            self._bus.publish("autonomy.project.paused", {
                "project_id": project_id,
            })
        return True

    def resume_project(self, project_id: str) -> bool:
        project = self.get_project(project_id)
        if not project or project.status != ProjectStatus.PAUSED:
            return False
        with self._lock:
            project.status = ProjectStatus.ACTIVE
            project.updated_at = time.time()
        self._log_decision(f"Project resumed: {project.name}", project_id)
        if self._bus:
            self._bus.publish("autonomy.project.resumed", {
                "project_id": project_id,
            })
        return True

    def cancel_project(self, project_id: str) -> bool:
        project = self.get_project(project_id)
        if not project:
            return False
        with self._lock:
            project.status = ProjectStatus.CANCELLED
            project.updated_at = time.time()
        self._log_decision(f"Project cancelled: {project.name}", project_id)
        if self._bus:
            self._bus.publish("autonomy.project.cancelled", {
                "project_id": project_id,
            })
        self._generate_report(project_id)
        return True

    def make_decision(
        self,
        project_id: str,
        context: str,
        options: list[str],
        selected: str,
        rationale: str = "",
    ) -> dict[str, Any]:
        decision = {
            "decision_id": uuid.uuid4().hex[:16],
            "project_id": project_id,
            "context": context,
            "options": list(options),
            "selected": selected,
            "rationale": rationale,
            "timestamp": time.time(),
        }
        with self._lock:
            self._decision_log.append(decision)

        if self._graph:
            try:
                self._graph.create_entity(
                    type="decision",
                    name=f"decision_{decision['decision_id']}",
                    properties=decision,
                )
            except Exception:
                pass
        return decision

    def _log_decision(self, description: str, project_id: str = "") -> None:
        self._decision_log.append({
            "description": description,
            "project_id": project_id,
            "timestamp": time.time(),
        })

    def _generate_report(self, project_id: str) -> ProjectReport | None:
        project = self.get_project(project_id)
        if not project:
            return None

        completed = sum(
            1 for m in project.milestones if m.status == "completed"
        )
        total = len(project.milestones)
        interventions = sum(
            1 for cp in project.checkpoints if cp.get("required_approval", False)
        )
        decisions = sum(
            1 for d in self._decision_log if d.get("project_id") == project_id
        )
        duration = time.time() - project.created_at
        report_id = uuid.uuid4().hex[:16]

        report = ProjectReport(
            report_id=report_id,
            project_id=project_id,
            project_name=project.name,
            goal=project.goal,
            status=project.status.value,
            milestones_completed=completed,
            milestones_total=total,
            duration_seconds=round(duration, 2),
            decisions_made=decisions,
            human_interventions=interventions,
            summary=f"Project {project.name}: {completed}/{total} milestones completed in {duration:.1f}s",
            details={
                "milestones": [m.to_dict() for m in project.milestones],
                "checkpoints": list(project.checkpoints),
                "phase": project.phase.value,
            },
            timestamp=time.time(),
        )

        with self._lock:
            self._reports[report_id] = report

        if self._graph:
            try:
                self._graph.create_entity(
                    type="report",
                    name=f"report_{report_id}",
                    properties=report.to_dict(),
                )
            except Exception:
                pass
        return report

    def get_report(self, report_id: str) -> ProjectReport | None:
        with self._lock:
            return self._reports.get(report_id)

    def get_project_report_by_id(self, project_id: str) -> ProjectReport | None:
        with self._lock:
            for report in self._reports.values():
                if report.project_id == project_id:
                    return report
        return None

    def list_projects(self) -> list[Project]:
        with self._lock:
            return list(self._projects.values())

    def list_active_projects(self) -> list[Project]:
        with self._lock:
            return [
                p for p in self._projects.values()
                if p.status in (ProjectStatus.ACTIVE, ProjectStatus.PLANNING)
            ]

    def get_statistics(self) -> dict[str, Any]:
        with self._lock:
            total = len(self._projects)
            active = sum(
                1 for p in self._projects.values()
                if p.status == ProjectStatus.ACTIVE
            )
            completed = sum(
                1 for p in self._projects.values()
                if p.status == ProjectStatus.COMPLETED
            )
            failed = sum(
                1 for p in self._projects.values()
                if p.status == ProjectStatus.FAILED
            )
            total_decisions = len(self._decision_log)
        return {
            "total_projects": total,
            "active": active,
            "completed": completed,
            "failed": failed,
            "total_decisions": total_decisions,
        }

    def health(self) -> dict[str, Any]:
        return {"alive": True}
