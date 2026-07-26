from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from .structured import StructuredSchema


class ReasoningError(Exception):
    """Base exception for reasoning framework errors."""


class ReasoningValidationError(ReasoningError):
    """Raised when a reasoning chain definition is invalid."""


class ReasoningParseError(ReasoningError):
    """Raised when parsing a reasoning chain from provider output fails."""


# ---------------------------------------------------------------------------
# Step types
# ---------------------------------------------------------------------------


class ReasoningStepType(str, Enum):
    DEDUCTION = "deduction"
    INDUCTION = "induction"
    ABDUCTION = "abduction"
    ANALOGY = "analogy"
    ANALYSIS = "analysis"
    EVALUATION = "evaluation"
    COMPARISON = "comparison"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReasoningStep:
    id: str
    title: str
    description: str = ""
    step_type: ReasoningStepType = ReasoningStepType.ANALYSIS
    evidence: str = ""
    depends_on: tuple[str, ...] = ()
    confidence: float = 1.0
    metadata: dict | None = None


@dataclass(frozen=True)
class ReasoningChain:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    objective: str = ""
    assumptions: tuple[str, ...] = ()
    steps: tuple[ReasoningStep, ...] = ()
    conclusion: str = ""
    confidence: float = 1.0
    created_at: float = field(
        default_factory=lambda: datetime.now(timezone.utc).timestamp(),
    )
    metadata: dict | None = None


@dataclass(frozen=True)
class ReasoningValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ReasoningResult:
    chain: ReasoningChain
    provider: str
    model: str
    duration_ms: float
    valid: bool
    validation_errors: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_reasoning(chain: ReasoningChain) -> ReasoningValidationResult:
    """Validate a ``ReasoningChain`` definition."""
    errors: list[str] = []
    warnings: list[str] = []

    if not chain.objective:
        errors.append("Reasoning objective is required")
    if not chain.steps:
        errors.append("Reasoning chain has no steps")
        return ReasoningValidationResult(valid=False, errors=errors)

    if chain.metadata is not None and not isinstance(chain.metadata, dict):
        errors.append("Chain metadata must be a dict or None")

    if not (0.0 <= chain.confidence <= 1.0):
        errors.append(
            f"Chain confidence must be between 0.0 and 1.0, got {chain.confidence}",
        )

    seen_ids: set[str] = set()
    for step in chain.steps:
        if not step.id:
            errors.append("A step has an empty ID")
        elif step.id in seen_ids:
            errors.append(f"Duplicate step ID: {step.id!r}")
        seen_ids.add(step.id)

        if not step.title:
            errors.append(f"Step {step.id!r} has no title")

        if not (0.0 <= step.confidence <= 1.0):
            errors.append(
                f"Step {step.id!r} confidence must be between "
                f"0.0 and 1.0, got {step.confidence}",
            )

        if step.metadata is not None and not isinstance(step.metadata, dict):
            errors.append(f"Step {step.id!r} metadata must be a dict or None")

    if errors:
        return ReasoningValidationResult(valid=False, errors=errors)

    all_ids = {step.id for step in chain.steps}
    for step in chain.steps:
        for dep in step.depends_on:
            if dep not in all_ids:
                errors.append(
                    f"Step {step.id!r} depends on unknown step {dep!r}",
                )

    cycles = _find_circular_dependencies(chain.steps)
    for cycle in cycles:
        errors.append(f"Circular dependency: {' -> '.join(cycle)}")

    return ReasoningValidationResult(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
    )


def _find_circular_dependencies(
    steps: tuple[ReasoningStep, ...],
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


def parse_reasoning(
    data: dict,
    provider: str = "",
    model: str = "",
) -> ReasoningChain:
    """Parse a ``ReasoningChain`` from structured output *data*.

    Raises ``ReasoningParseError`` when the data cannot be parsed.
    """
    try:
        steps_data: list[dict] = data.get("steps") or []
        steps: list[ReasoningStep] = []
        for s in steps_data:
            raw_type = s.get("step_type", "analysis")
            try:
                step_type = ReasoningStepType(raw_type)
            except ValueError:
                step_type = ReasoningStepType.ANALYSIS

            raw_confidence = s.get("confidence", 1.0)
            step = ReasoningStep(
                id=s.get("id", ""),
                title=s.get("title", ""),
                description=s.get("description", ""),
                step_type=step_type,
                evidence=s.get("evidence", ""),
                depends_on=tuple(s.get("depends_on", []) or []),
                confidence=float(raw_confidence),
                metadata=s.get("metadata"),
            )
            steps.append(step)

        raw_chain_conf = data.get("confidence", 1.0)
        raw_assumptions = data.get("assumptions") or []

        return ReasoningChain(
            id=data.get("id") or uuid.uuid4().hex[:12],
            objective=data.get("objective", ""),
            assumptions=tuple(
                a if isinstance(a, str) else str(a) for a in raw_assumptions
            ),
            steps=tuple(steps),
            conclusion=data.get("conclusion", ""),
            confidence=float(raw_chain_conf),
            metadata=data.get("metadata"),
        )
    except Exception as exc:
        raise ReasoningParseError(str(exc)) from exc


# ---------------------------------------------------------------------------
# Default reasoning schema & prompt
# ---------------------------------------------------------------------------

REASONING_SCHEMA = StructuredSchema(
    name="reasoning",
    schema={
        "type": "object",
        "properties": {
            "objective": {
                "type": "string",
                "description": "The question or problem being reasoned about",
            },
            "assumptions": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Assumptions underlying the reasoning",
            },
            "conclusion": {
                "type": "string",
                "description": "Final conclusion drawn from the reasoning",
            },
            "confidence": {
                "type": "number",
                "description": "Overall confidence in the conclusion (0.0–1.0)",
            },
            "steps": {
                "type": "array",
                "description": "Ordered reasoning steps",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "description": "Unique step identifier"},
                        "title": {"type": "string", "description": "Step title"},
                        "description": {
                            "type": "string",
                            "description": "Detailed reasoning for this step",
                        },
                        "step_type": {
                            "type": "string",
                            "enum": [
                                "deduction",
                                "induction",
                                "abduction",
                                "analogy",
                                "analysis",
                                "evaluation",
                                "comparison",
                            ],
                            "description": "Type of reasoning",
                        },
                        "evidence": {
                            "type": "string",
                            "description": "Evidence or data supporting this step",
                        },
                        "depends_on": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Step IDs this step depends on",
                        },
                        "confidence": {
                            "type": "number",
                            "description": "Confidence in this step (0.0–1.0)",
                        },
                    },
                    "required": ["id", "title", "step_type"],
                },
            },
        },
        "required": ["objective", "conclusion", "steps"],
    },
)


DEFAULT_REASONING_PROMPT = """You are a reasoning assistant. Structure your analytical thinking about the given question or problem.

For each step provide:
- id: a unique identifier
- title: a clear name for this reasoning step
- description: detailed reasoning
- step_type: one of deduction, induction, abduction, analogy, analysis, evaluation, or comparison
- evidence: supporting evidence or data
- depends_on: list of step IDs this step depends on (can be empty)
- confidence: how confident you are in this step (0.0 to 1.0)

Then provide your conclusion along with your overall confidence level and any assumptions you made.

Question: {objective}"""
