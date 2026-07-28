from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class GoalStatus(Enum):
    PENDING = "pending"
    INTERPRETING = "interpreting"
    PLANNING = "planning"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class GoalType(Enum):
    CREATE = "create"
    MODIFY = "modify"
    QUERY = "query"
    ANALYZE = "analyze"
    OPTIMIZE = "optimize"
    LEARN = "learn"
    MONITOR = "monitor"
    EXPLORE = "explore"
    DEBUG = "debug"
    DEPLOY = "deploy"
    UNKNOWN = "unknown"


_GOAL_KEYWORDS: dict[GoalType, list[str]] = {
    GoalType.CREATE: ["create", "build", "make", "generate", "write", "develop", "implement"],
    GoalType.MODIFY: ["modify", "update", "change", "edit", "refactor", "improve", "upgrade"],
    GoalType.QUERY: ["find", "search", "get", "show", "list", "what", "where", "who", "when"],
    GoalType.ANALYZE: ["analyze", "evaluate", "assess", "review", "inspect", "examine"],
    GoalType.OPTIMIZE: ["optimize", "speed", "performance", "reduce", "minimize"],
    GoalType.LEARN: ["learn", "study", "understand", "research", "explain"],
    GoalType.MONITOR: ["monitor", "watch", "track", "observe", "alert"],
    GoalType.EXPLORE: ["explore", "discover", "investigate", "survey"],
    GoalType.DEBUG: ["debug", "fix", "repair", "resolve", "bug", "error", "issue"],
    GoalType.DEPLOY: ["deploy", "release", "publish", "install", "distribute"],
}


@dataclass
class Goal:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    description: str = ""
    goal_type: GoalType = GoalType.UNKNOWN
    intent: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)
    constraints: dict[str, Any] = field(default_factory=dict)
    status: GoalStatus = GoalStatus.PENDING
    session_id: str = ""
    parent_goal_id: str = ""
    sub_goals: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "description": self.description,
            "goal_type": self.goal_type.value,
            "intent": self.intent,
            "parameters": dict(self.parameters),
            "constraints": dict(self.constraints),
            "status": self.status.value,
            "session_id": self.session_id,
            "parent_goal_id": self.parent_goal_id,
            "sub_goals": list(self.sub_goals),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": dict(self.metadata),
        }


class GoalInterpreter:
    """Interprets natural language or structured goal descriptions.

    Extracts intent, goal type, parameters, and constraints from a free-form
    goal description using keyword-based heuristics.

    Thread-safe.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._custom_keywords: dict[GoalType, list[str]] = {}

    def add_keywords(self, goal_type: GoalType, keywords: list[str]) -> None:
        with self._lock:
            existing = self._custom_keywords.setdefault(goal_type, [])
            for kw in keywords:
                if kw not in existing:
                    existing.append(kw)

    def interpret(self, description: str) -> Goal:
        """Parse a goal description and produce a Goal with extracted fields."""
        with self._lock:
            desc_lower = description.lower()
            goal_type = self._classify(desc_lower)
            intent = self._extract_intent(desc_lower)
            parameters = self._extract_parameters(description)
            constraints = self._extract_constraints(desc_lower)

            return Goal(
                description=description,
                goal_type=goal_type,
                intent=intent,
                parameters=parameters,
                constraints=constraints,
                status=GoalStatus.PENDING,
            )

    def _classify(self, desc_lower: str) -> GoalType:
        words = set(desc_lower.split())
        scores: dict[GoalType, int] = {}
        for gtype, keywords in _GOAL_KEYWORDS.items():
            scores[gtype] = sum(1 for kw in keywords if kw in words or f" {kw} " in f" {desc_lower} ")
        for gtype, keywords in self._custom_keywords.items():
            scores[gtype] = scores.get(gtype, 0) + sum(1 for kw in keywords if kw in words or f" {kw} " in f" {desc_lower} ")

        best = GoalType.UNKNOWN
        best_score = 0
        for gtype, score in scores.items():
            if score > best_score:
                best_score = score
                best = gtype
        return best

    def _extract_intent(self, desc_lower: str) -> str:
        action_phrases = [
            "i want to", "i need to", "please", "could you",
            "can you", "would you", "goal:",
        ]
        for phrase in action_phrases:
            if phrase in desc_lower:
                idx = desc_lower.index(phrase) + len(phrase)
                remainder = desc_lower[idx:].strip().strip(".:;,!?")
                if remainder:
                    return remainder[:200]
        return desc_lower[:200]

    def _extract_parameters(self, description: str) -> dict[str, Any]:
        params: dict[str, Any] = {}
        words = description.split()
        for i, word in enumerate(words):
            if word.startswith("--") and i + 1 < len(words):
                key = word.lstrip("-")
                params[key] = words[i + 1]
            elif word.startswith("-") and len(word) > 1 and i + 1 < len(words):
                key = word.lstrip("-")
                params[key] = words[i + 1]
        return params

    def _extract_constraints(self, desc_lower: str) -> dict[str, Any]:
        constraints: dict[str, Any] = {}
        time_indicators = {
            "urgent": "urgent",
            "asap": "urgent",
            "immediately": "urgent",
            "quick": "fast",
            "fast": "fast",
            "careful": "careful",
            "safe": "safe",
            "low risk": "low_risk",
        }
        for keyword, constraint in time_indicators.items():
            if keyword in desc_lower:
                constraints[constraint] = True
        return constraints

    def supported_types(self) -> list[str]:
        return [t.value for t in GoalType]
