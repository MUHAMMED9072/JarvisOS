from __future__ import annotations

import enum
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from app.ads.governance import GovernanceResult


class ApprovalDecision(enum.Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    PENDING = "pending"
    TIMEOUT = "timeout"


@dataclass
class ApprovalRequest:
    """An approval request for an artifact."""

    artifact_name: str = ""
    governance_result: GovernanceResult | None = None
    submitted_at: float = field(default_factory=time.time)
    decision: ApprovalDecision = ApprovalDecision.PENDING
    decided_at: float = 0.0
    reviewer: str = ""
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_name": self.artifact_name,
            "governance_result": self.governance_result.to_dict() if self.governance_result else {},
            "submitted_at": self.submitted_at,
            "decision": self.decision.value,
            "decided_at": self.decided_at,
            "reviewer": self.reviewer,
            "notes": self.notes,
        }


class ApprovalGate:
    """Present governance results and manage the approval decision.

    Supports auto-approve (low risk, high trust), manual (medium risk),
    and reject (high risk) modes with configurable timeout.
    """

    def __init__(
        self,
        timeout_seconds: float = 3600.0,
        on_timeout: str = "reject",
        auto_approve_callback: Callable[[str], None] | None = None,
    ) -> None:
        self._timeout = timeout_seconds
        self._on_timeout = on_timeout
        self._auto_approve_callback = auto_approve_callback
        self._requests: dict[str, ApprovalRequest] = {}

    def submit(self, artifact_name: str, result: GovernanceResult) -> ApprovalRequest:
        request = ApprovalRequest(
            artifact_name=artifact_name,
            governance_result=result,
        )

        # Auto-approve or reject based on risk
        if result.approval_mode == "auto-approve":
            request.decision = ApprovalDecision.APPROVED
            request.decided_at = time.time()
            request.notes = "Auto-approved (low risk)"
            if self._auto_approve_callback:
                self._auto_approve_callback(artifact_name)
        elif result.approval_mode == "rejected":
            request.decision = ApprovalDecision.REJECTED
            request.decided_at = time.time()
            request.notes = "Auto-rejected (high risk)"
        # Manual: leave as PENDING

        self._requests[artifact_name] = request
        return request

    def approve(self, artifact_name: str, reviewer: str = "", notes: str = "") -> ApprovalRequest | None:
        request = self._requests.get(artifact_name)
        if request is None:
            return None
        request.decision = ApprovalDecision.APPROVED
        request.decided_at = time.time()
        request.reviewer = reviewer
        request.notes = notes
        return request

    def reject(self, artifact_name: str, reviewer: str = "", notes: str = "") -> ApprovalRequest | None:
        request = self._requests.get(artifact_name)
        if request is None:
            return None
        request.decision = ApprovalDecision.REJECTED
        request.decided_at = time.time()
        request.reviewer = reviewer
        request.notes = notes
        return request

    def check_timeout(self, artifact_name: str) -> ApprovalRequest | None:
        """Check if a pending request has timed out."""
        request = self._requests.get(artifact_name)
        if request is None:
            return None
        if request.decision != ApprovalDecision.PENDING:
            return request
        elapsed = time.time() - request.submitted_at
        if elapsed > self._timeout:
            if self._on_timeout == "approve":
                request.decision = ApprovalDecision.APPROVED
            else:
                request.decision = ApprovalDecision.TIMEOUT
            request.decided_at = time.time()
            request.notes = f"Timed out after {self._timeout}s, default: {self._on_timeout}"
        return request

    def get_status(self, artifact_name: str) -> ApprovalRequest | None:
        return self._requests.get(artifact_name)

    def list_pending(self) -> list[ApprovalRequest]:
        return [
            r for r in self._requests.values()
            if r.decision == ApprovalDecision.PENDING
        ]

    def health(self) -> dict[str, Any]:
        return {
            "alive": True,
            "pending_requests": len(self.list_pending()),
            "total_requests": len(self._requests),
        }
