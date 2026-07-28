from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any


_FAILURE_PATTERNS: list[dict[str, Any]] = [
    {"pattern": "timeout", "cause": "execution_timeout", "severity": "high"},
    {"pattern": "out of memory", "cause": "insufficient_memory", "severity": "high"},
    {"pattern": "permission denied", "cause": "permission_error", "severity": "medium"},
    {"pattern": "not found", "cause": "resource_not_found", "severity": "medium"},
    {"pattern": "connection refused", "cause": "network_error", "severity": "high"},
    {"pattern": "invalid input", "cause": "invalid_input", "severity": "low"},
    {"pattern": "dependency failed", "cause": "dependency_failure", "severity": "high"},
    {"pattern": "rate limit", "cause": "rate_limited", "severity": "low"},
    {"pattern": "unexpected error", "cause": "unexpected_error", "severity": "medium"},
]


@dataclass
class TaskOutcome:
    task_id: str = ""
    task_name: str = ""
    success: bool = True
    error_message: str = ""
    duration_seconds: float = 0.0
    resource_used: dict[str, float] = field(default_factory=dict)
    root_cause: str = ""
    failure_pattern: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task_name": self.task_name,
            "success": self.success,
            "error_message": self.error_message,
            "duration_seconds": self.duration_seconds,
            "resource_used": dict(self.resource_used),
            "root_cause": self.root_cause,
            "failure_pattern": self.failure_pattern,
        }


@dataclass
class PatternRecord:
    pattern: str = ""
    cause: str = ""
    count: int = 1
    severity: str = "medium"
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pattern": self.pattern,
            "cause": self.cause,
            "count": self.count,
            "severity": self.severity,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
        }


class OutcomeAnalyzer:
    """Analyzes task execution outcomes to classify success/failure,
    identify root causes, and detect recurring failure patterns.

    Thread-safe.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._outcomes: list[TaskOutcome] = []
        self._patterns: dict[str, PatternRecord] = {}

    def analyze(self, outcome: TaskOutcome) -> TaskOutcome:
        """Analyze a task outcome, classifying root cause and pattern."""
        with self._lock:
            if not outcome.success and outcome.error_message:
                outcome.root_cause = self._identify_root_cause(outcome.error_message)
                outcome.failure_pattern = self._classify_pattern(outcome.error_message)
                self._update_patterns(outcome.failure_pattern, outcome.root_cause, outcome.error_message)

            self._outcomes.append(outcome)
            return outcome

    def _identify_root_cause(self, error_message: str) -> str:
        msg_lower = error_message.lower()
        for fp in _FAILURE_PATTERNS:
            if fp["pattern"] in msg_lower:
                return fp["cause"]
        if len(error_message) > 100:
            return "complex_error"
        return "unknown"

    def _classify_pattern(self, error_message: str) -> str:
        msg_lower = error_message.lower()
        for fp in _FAILURE_PATTERNS:
            if fp["pattern"] in msg_lower:
                return fp["pattern"]
        return "unknown"

    def _update_patterns(self, pattern: str, cause: str, error_message: str) -> None:
        if pattern == "unknown":
            return
        now = time.time()
        if pattern in self._patterns:
            rec = self._patterns[pattern]
            rec.count += 1
            rec.last_seen = now
        else:
            severity = "medium"
            for fp in _FAILURE_PATTERNS:
                if fp["pattern"] == pattern:
                    severity = fp["severity"]
                    break
            self._patterns[pattern] = PatternRecord(
                pattern=pattern, cause=cause,
                count=1, severity=severity,
                first_seen=now, last_seen=now,
            )

    def list_outcomes(
        self,
        success: bool | None = None,
        limit: int = 100,
    ) -> list[TaskOutcome]:
        with self._lock:
            result = list(self._outcomes)
            if success is not None:
                result = [o for o in result if o.success == success]
            return result[-limit:]

    def get_outcome_count(self) -> int:
        with self._lock:
            return len(self._outcomes)

    def get_failure_rate(self) -> float:
        with self._lock:
            total = len(self._outcomes)
            if total == 0:
                return 0.0
            failures = sum(1 for o in self._outcomes if not o.success)
            return failures / total

    def get_patterns(self) -> list[PatternRecord]:
        with self._lock:
            return sorted(
                self._patterns.values(),
                key=lambda p: p.count,
                reverse=True,
            )

    def get_common_failures(self, min_count: int = 2) -> list[PatternRecord]:
        return [p for p in self.get_patterns() if p.count >= min_count]

    def health(self) -> dict[str, Any]:
        return {
            "alive": True,
            "outcomes_analyzed": self.get_outcome_count(),
            "failure_rate": self.get_failure_rate(),
            "patterns_detected": len(self._patterns),
        }
