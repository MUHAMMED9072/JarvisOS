"""
JARVIS Evolution Engine - Approval policies.

Defines the abstract contract for any approval gate that decides whether
a generated patch may be installed into the live tree. The default
implementation is :class:`InteractiveCliApprovalPolicy`, which blocks
on a terminal prompt with a "no" default.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.evolution.installer import ApprovalRequest


@dataclass(frozen=True, slots=True)
class ApprovalDecision:
    """Outcome of an :class:`ApprovalPolicy` request.

    Attributes:
        approved: Whether the install may proceed.
        approver: Identifier of the policy that produced the decision
            (e.g. ``"cli"``). Empty when the decision was never taken.
        timestamp: ISO-8601 UTC timestamp of the decision.
        reason: Human-readable explanation; empty when approved.
    """

    approved: bool
    approver: str
    timestamp: str
    reason: str = ""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ApprovalPolicy(ABC):
    """Abstract base for any approval gate consulted by the Installer."""

    @abstractmethod
    def request(self, request: "ApprovalRequest") -> ApprovalDecision:
        """Return an :class:`ApprovalDecision` for the given request."""


class InteractiveCliApprovalPolicy(ApprovalPolicy):
    """Prompt the user on stdin. Default answer is NO.

    The policy prints a brief summary of the pending install (target,
    patch, backup, and the report summary), then asks for confirmation.
    Anything other than ``y`` or ``yes`` (case-insensitive) is treated
    as a denial, matching the "default NO" safety posture.
    """

    PROMPT = "Approve installation? (y/N): "

    def request(self, request: "ApprovalRequest") -> ApprovalDecision:
        print("=" * 50)
        print("PENDING INSTALL")
        print("=" * 50)
        print(f"  Target : {request.target_path}")
        print(f"  Patch  : {request.patch_path}")
        print(f"  Backup : {request.backup_path}")
        for key, value in request.summary.items():
            print(f"  {key:<14}: {value}")
        print("=" * 50)

        try:
            # Print the prompt explicitly so it is captured during testing,
            # even when input() is monkeypatched.
            print(self.PROMPT, end="", flush=True)
            response = input().strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return ApprovalDecision(
                approved=False,
                approver="cli",
                timestamp=_now_iso(),
                reason="interrupted before answer",
            )

        approved = response in ("y", "yes")
        return ApprovalDecision(
            approved=approved,
            approver="cli",
            timestamp=_now_iso(),
            reason="" if approved else "user denied at prompt",
        )