from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from .structured import StructuredSchema


class PlanError(Exception):
    """Base exception for planning framework errors."""


class PlanValidationError(PlanError):
    """Raised when a plan definition is invalid."""


class PlanParseError(PlanError):
    """Raised when parsing a plan from provider output fails."""


# ---------------------------------------------------------------------------
# Action types
# ---------------------------------------------------------------------------


class PlanAction(str, Enum):
    TASK = "task"
    QUERY = "query"
    DECISION = "decision"
    PARALLEL = "parallel"
    CONDITIONAL = "conditional"
    INPUT = "input"
    OUTPUT = "output"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PlanStep:
    id: str
    title: str
    description: str = ""
    action_type: PlanAction = PlanAction.TASK
    expected_input: str = ""
    expected_output: str = ""
    depends_on: tuple[str, ...] = ()
    conditions: str = ""
    metadata: dict | None = None


@dataclass(frozen=True)
class Plan:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    title: str = ""
    objective: str = ""
    steps: tuple[PlanStep, ...] = ()
    created_at: float = field(
        default_factory=lambda: datetime.now(timezone.utc).timestamp(),
    )
    metadata: dict | None = None


@dataclass(frozen=True)
class PlanValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PlanResult:
    plan: Plan
    provider: str
    model: str
    duration_ms: float
    valid: bool
    validation_errors: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_plan(plan: Plan) -> PlanValidationResult:
    """Validate a ``Plan`` definition."""
    errors: list[str] = []
    warnings: list[str] = []

    if not plan.objective:
        errors.append("Plan objective is required")
    if not plan.title:
        errors.append("Plan title is required")
    if not plan.steps:
        errors.append("Plan has no steps")
        return PlanValidationResult(valid=False, errors=errors)

    if plan.metadata is not None and not isinstance(plan.metadata, dict):
        errors.append("Plan metadata must be a dict or None")

    seen_ids: set[str] = set()
    for step in plan.steps:
        if not step.id:
            errors.append("A step has an empty ID")
        elif step.id in seen_ids:
            errors.append(f"Duplicate step ID: {step.id!r}")
        seen_ids.add(step.id)
        if not step.title:
            errors.append(f"Step {step.id!r} has no title")
        if step.metadata is not None and not isinstance(step.metadata, dict):
            errors.append(f"Step {step.id!r} metadata must be a dict or None")

    if errors:
        return PlanValidationResult(valid=False, errors=errors)

    all_ids = {step.id for step in plan.steps}
    for step in plan.steps:
        for dep in step.depends_on:
            if dep not in all_ids:
                errors.append(
                    f"Step {step.id!r} depends on unknown step {dep!r}",
                )

    cycles = _find_circular_dependencies(plan.steps)
    for cycle in cycles:
        errors.append(f"Circular dependency: {' -> '.join(cycle)}")

    return PlanValidationResult(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
    )


def _find_circular_dependencies(
    steps: tuple[PlanStep, ...],
) -> list[list[str]]:
    dep_map: dict[str, list[str]] = {s.id: list(s.depends_on) for s in steps}
    cycles: list[list[str]] = []
    visited: set[str] = set()
    path: list[str] = []

    def dfs(node: str, path_set: set[str]) -> None:
        if node in path_set:
            idx = path.index(node)
            cycles.append(path[idx:] + [node])
            return
        if node in visited:
            return
        visited.add(node)
        path.append(node)
        path_set.add(node)
        for dep in dep_map.get(node, []):
            dfs(dep, path_set)
        path.pop()
        path_set.remove(node)

    for sid in dep_map:
        if sid not in visited:
            dfs(sid, set())

    return cycles


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def parse_plan(data: dict, provider: str = "", model: str = "") -> Plan:
    """Parse a ``Plan`` from structured output *data*.

    Raises ``PlanParseError`` when the data cannot be parsed.
    """
    try:
        steps_data: list[dict] = data.get("steps") or []
        steps: list[PlanStep] = []
        for s in steps_data:
            raw_action = s.get("action_type", "task")
            try:
                action_type = PlanAction(raw_action)
            except ValueError:
                action_type = PlanAction.TASK

            step = PlanStep(
                id=s.get("id", ""),
                title=s.get("title", ""),
                description=s.get("description", ""),
                action_type=action_type,
                expected_input=s.get("expected_input", ""),
                expected_output=s.get("expected_output", ""),
                depends_on=tuple(s.get("depends_on", []) or []),
                conditions=s.get("conditions", ""),
                metadata=s.get("metadata"),
            )
            steps.append(step)

        return Plan(
            id=data.get("id") or uuid.uuid4().hex[:12],
            title=data.get("title", ""),
            objective=data.get("objective", ""),
            steps=tuple(steps),
            metadata=data.get("metadata"),
        )
    except Exception as exc:
        raise PlanParseError(str(exc)) from exc


# ---------------------------------------------------------------------------
# Default planning schema & prompt
# ---------------------------------------------------------------------------

PLAN_SCHEMA = StructuredSchema(
    name="plan",
    schema={
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Short plan title"},
            "objective": {"type": "string", "description": "Plan objective"},
            "steps": {
                "type": "array",
                "description": "Ordered list of steps to execute",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "description": "Unique step identifier"},
                        "title": {"type": "string", "description": "Clear step title"},
                        "description": {"type": "string", "description": "What this step does"},
                        "action_type": {
                            "type": "string",
                            "enum": [
                                "task",
                                "query",
                                "decision",
                                "parallel",
                                "conditional",
                                "input",
                                "output",
                            ],
                            "description": "Type of action",
                        },
                        "expected_input": {
                            "type": "string",
                            "description": "Input the step expects",
                        },
                        "expected_output": {
                            "type": "string",
                            "description": "Output the step produces",
                        },
                        "depends_on": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Step IDs this step depends on",
                        },
                        "conditions": {
                            "type": "string",
                            "description": "Conditions for execution",
                        },
                    },
                    "required": ["id", "title", "action_type"],
                },
            },
        },
        "required": ["title", "objective", "steps"],
    },
)


DEFAULT_PLAN_PROMPT = """You are a planning assistant. Create a detailed step-by-step plan to achieve the given objective.

For each step provide:
- id: a unique identifier
- title: a clear name
- description: what the step does
- action_type: one of task, query, decision, parallel, conditional, input, or output
- expected_input: what the step needs
- expected_output: what the step produces
- depends_on: list of step IDs this step depends on (can be empty)
- conditions: any conditions for execution

Steps must be ordered logically respecting their dependencies.

Objective: {objective}"""
