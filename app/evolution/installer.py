"""
JARVIS Evolution Engine - Installer.

Asks an :class:`~app.evolution.approval.ApprovalPolicy` for explicit
human approval before replacing a target file with a generated patch.
On denial the target is left untouched. On installation failure after
approval, the target is restored from the backup that
:class:`RollbackManager` created, and a record of the decision is
written to the audit directory.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.config import Config
from app.core.logger import JarvisLogger
from app.evolution.approval import (
    ApprovalDecision,
    ApprovalPolicy,
    InteractiveCliApprovalPolicy,
)
from app.evolution.rollback import RollbackManager


@dataclass(frozen=True, slots=True)
class ApprovalRequest:
    """Information required by the Installer to make an approval decision.

    Attributes:
        patch_path: Filesystem path to the generated replacement file.
        target_path: Filesystem path of the file that will be replaced
            on approval.
        backup_path: Filesystem path to the backup directory created by
            :class:`RollbackManager` before the install attempt; used
            for one-step restore on failure.
        summary: Free-form per-stage verdict map (validation, sandbox,
            tests, ...). Kept as a dict so additional stages can be
            surfaced without a schema change.
    """

    patch_path: str
    target_path: str
    backup_path: str
    summary: dict[str, Any]


@dataclass(frozen=True, slots=True)
class InstallResult:
    """Outcome of :meth:`Installer.install`.

    Attributes:
        success: ``True`` only when the patch was applied to the target.
        message: Human-readable description of the outcome.
        approved_by: Identifier of the policy that produced the
            decision, or ``"policy"`` when no approval was ever asked.
        approval_timestamp: ISO-8601 timestamp of the decision; empty
            when the install did not require approval.
        target_path: The target file the install attempted to write.
        backup_path: The backup directory associated with the attempt.
    """

    success: bool
    message: str
    approved_by: str
    approval_timestamp: str
    target_path: str
    backup_path: str


class Installer:
    """Apply an approved patch to a target file under human-in-the-loop gating.

    The Installer does not decide whether to approve an install — that
    is the policy's job. It asks the configured
    :class:`ApprovalPolicy` for a verdict, then either applies the
    patch atomically or restores the target from the backup. Every
    decision is recorded as a JSON file in the audit directory.
    """

    def __init__(
        self,
        policy: ApprovalPolicy | None = None,
        rollback: RollbackManager | None = None,
        audit_dir: str | None = None,
    ) -> None:
        self.policy = policy if policy is not None else InteractiveCliApprovalPolicy()
        self.rollback = rollback if rollback is not None else RollbackManager()
        self.audit_dir = (
            Path(audit_dir) if audit_dir is not None
            else Config.DATA_DIR / "evolution" / "decisions"
        )

    def install(self, request: ApprovalRequest) -> InstallResult:
        """Ask the policy, then either install the patch or restore from backup."""
        JarvisLogger.info(
            "Installer: requesting approval for %s", request.target_path,
        )

        decision: ApprovalDecision = self.policy.request(request)

        if not decision.approved:
            self._write_audit(request, decision, error=None)
            JarvisLogger.warning(
                "Installer: install denied (%s) for %s",
                decision.approver,
                request.target_path,
            )
            return InstallResult(
                success=False,
                message=f"install denied: {decision.reason or 'no reason given'}",
                approved_by=decision.approver,
                approval_timestamp=decision.timestamp,
                target_path=request.target_path,
                backup_path=request.backup_path,
            )

        try:
            self._atomic_replace(request.target_path, request.patch_path)
        except (OSError, shutil.Error) as exc:
            self._write_audit(request, decision, error=str(exc))
            JarvisLogger.error(
                "Installer: install failed for %s: %s; restoring backup",
                request.target_path,
                exc,
            )
            restore_result = self.rollback.restore(
                request.backup_path, request.target_path,
            )
            detail = (
                "restored from backup"
                if restore_result.success
                else f"backup restore FAILED: {restore_result.message}"
            )
            return InstallResult(
                success=False,
                message=f"install failed ({exc}); {detail}",
                approved_by=decision.approver,
                approval_timestamp=decision.timestamp,
                target_path=request.target_path,
                backup_path=request.backup_path,
            )

        self._write_audit(request, decision, error=None)
        JarvisLogger.info(
            "Installer: installed %s (approved by %s)",
            request.target_path,
            decision.approver,
        )
        return InstallResult(
            success=True,
            message="installed successfully",
            approved_by=decision.approver,
            approval_timestamp=decision.timestamp,
            target_path=request.target_path,
            backup_path=request.backup_path,
        )

    def _atomic_replace(self, target: str, patch: str) -> None:
        """Replace the target with the patch via a write-then-rename."""
        target_path = Path(target)
        patch_path = Path(patch)
        if not patch_path.exists():
            raise FileNotFoundError(f"patch file not found: {patch_path}")
        target_path.parent.mkdir(parents=True, exist_ok=True)
        pending = target_path.with_suffix(target_path.suffix + ".pending")
        shutil.copy2(patch_path, pending)
        Path.replace(pending, target_path)

    def _write_audit(
        self,
        request: ApprovalRequest,
        decision: ApprovalDecision,
        error: str | None,
    ) -> None:
        try:
            self.audit_dir.mkdir(parents=True, exist_ok=True)
            stamp = (
                decision.timestamp[:19]
                .replace("-", "")
                .replace(":", "")
                .replace("T", "-")
            )
            verdict = "approved" if decision.approved else "denied"
            audit_file = self.audit_dir / f"{stamp}-{verdict}.json"
            payload = {
                "request": {
                    "patch_path": request.patch_path,
                    "target_path": request.target_path,
                    "backup_path": request.backup_path,
                    "summary": request.summary,
                },
                "decision": {
                    "approved": decision.approved,
                    "approver": decision.approver,
                    "timestamp": decision.timestamp,
                    "reason": decision.reason,
                },
                "error": error,
            }
            audit_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except OSError as exc:
            JarvisLogger.warning("Installer: could not write audit record: %s", exc)
