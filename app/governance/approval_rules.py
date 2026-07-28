from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ApprovalOutcome(Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    PENDING = "pending"
    ESCALATED = "escalated"


@dataclass
class ApprovalRule:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    name: str = ""
    description: str = ""
    min_approvers: int = 1
    required_approvers: list[str] = field(default_factory=list)
    min_trust_level: str = "medium"
    timeout_seconds: float = 3600.0
    auto_approve: bool = False
    escalation_contact: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "min_approvers": self.min_approvers,
            "required_approvers": list(self.required_approvers),
            "min_trust_level": self.min_trust_level,
            "timeout_seconds": self.timeout_seconds,
            "auto_approve": self.auto_approve,
            "escalation_contact": self.escalation_contact,
        }


@dataclass
class ApprovalRequest:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    rule_id: str = ""
    artifact_id: str = ""
    requester: str = ""
    reason: str = ""
    outcome: ApprovalOutcome = ApprovalOutcome.PENDING
    approvers: list[str] = field(default_factory=list)
    decisions: dict[str, bool] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    decided_at: float | None = None
    escalation_reason: str = ""

    @property
    def approved_count(self) -> int:
        return sum(1 for v in self.decisions.values() if v)

    @property
    def rejected_count(self) -> int:
        return sum(1 for v in self.decisions.values() if not v)

    @property
    def is_expired(self) -> bool:
        return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "rule_id": self.rule_id,
            "artifact_id": self.artifact_id,
            "requester": self.requester,
            "reason": self.reason,
            "outcome": self.outcome.value,
            "approvers": list(self.approvers),
            "decisions": dict(self.decisions),
            "approved_count": self.approved_count,
            "rejected_count": self.rejected_count,
            "created_at": self.created_at,
            "decided_at": self.decided_at,
            "escalation_reason": self.escalation_reason,
        }


class ApprovalManager:
    """Manages approval rules and approval requests.

    Thread-safe.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._rules: dict[str, ApprovalRule] = {}
        self._requests: dict[str, ApprovalRequest] = {}

    def register_rule(self, rule: ApprovalRule) -> str:
        with self._lock:
            self._rules[rule.id] = rule
            return rule.id

    def get_rule(self, rule_id: str) -> ApprovalRule | None:
        with self._lock:
            return self._rules.get(rule_id)

    def delete_rule(self, rule_id: str) -> bool:
        with self._lock:
            if rule_id in self._rules:
                del self._rules[rule_id]
                return True
            return False

    def list_rules(self) -> list[ApprovalRule]:
        with self._lock:
            return list(self._rules.values())

    def create_request(
        self,
        rule_id: str,
        artifact_id: str,
        requester: str,
        reason: str = "",
    ) -> ApprovalRequest:
        with self._lock:
            rule = self._rules.get(rule_id)
            if rule is None:
                raise ValueError(f"Approval rule '{rule_id}' not found")
            req = ApprovalRequest(
                rule_id=rule_id,
                artifact_id=artifact_id,
                requester=requester,
                reason=reason,
                approvers=list(rule.required_approvers),
            )
            self._requests[req.id] = req
            return req

    def approve(self, request_id: str, approver: str) -> ApprovalOutcome | None:
        with self._lock:
            req = self._requests.get(request_id)
            if req is None:
                return None
            if req.outcome != ApprovalOutcome.PENDING:
                return req.outcome
            req.decisions[approver] = True
            if approver not in req.approvers:
                req.approvers.append(approver)
            return self._check_outcome(req)

    def reject(self, request_id: str, approver: str) -> ApprovalOutcome | None:
        with self._lock:
            req = self._requests.get(request_id)
            if req is None:
                return None
            if req.outcome != ApprovalOutcome.PENDING:
                return req.outcome
            req.decisions[approver] = False
            if approver not in req.approvers:
                req.approvers.append(approver)
            req.outcome = ApprovalOutcome.REJECTED
            req.decided_at = time.time()
            return req.outcome

    def get_request(self, request_id: str) -> ApprovalRequest | None:
        with self._lock:
            return self._requests.get(request_id)

    def list_requests(
        self,
        outcome: ApprovalOutcome | None = None,
        requester: str | None = None,
    ) -> list[ApprovalRequest]:
        with self._lock:
            result = list(self._requests.values())
            if outcome:
                result = [r for r in result if r.outcome == outcome]
            if requester:
                result = [r for r in result if r.requester == requester]
            return sorted(result, key=lambda r: r.created_at, reverse=True)

    def _check_outcome(self, req: ApprovalRequest) -> ApprovalOutcome:
        rule = self._rules.get(req.rule_id)
        if rule is None:
            req.outcome = ApprovalOutcome.REJECTED
            req.decided_at = time.time()
            return req.outcome
        if req.approved_count >= rule.min_approvers:
            req.outcome = ApprovalOutcome.APPROVED
            req.decided_at = time.time()
        return req.outcome
