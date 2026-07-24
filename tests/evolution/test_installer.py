"""Tests for the Evolution Engine Installer.

The Installer asks an :class:`ApprovalPolicy` for a verdict, then either
applies the patch atomically or restores the target from backup. Every
decision is written to the audit directory.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.evolution.approval import ApprovalDecision, ApprovalPolicy
from app.evolution.installer import (
    ApprovalRequest,
    Installer,
    InstallResult,
)
from app.evolution.rollback import RollbackManager


class _ScriptedPolicy(ApprovalPolicy):
    """A test policy that returns a pre-set decision every time."""

    def __init__(self, decision: ApprovalDecision) -> None:
        self.decision = decision
        self.calls: list[ApprovalRequest] = []

    def request(self, request: ApprovalRequest) -> ApprovalDecision:
        self.calls.append(request)
        return self.decision


def _make_target_and_patch(
    tmp_path: Path,
    target_content: str = "ORIGINAL",
    patch_content: str = "PATCHED",
) -> tuple[Path, Path]:
    target = tmp_path / "loader.py"
    target.write_text(target_content, encoding="utf-8")
    patch = tmp_path / "generated_patch.py"
    patch.write_text(patch_content, encoding="utf-8")
    return target, patch


def _make_backup(tmp_path: Path, target: Path) -> Path:
    backup_dir = tmp_path / "backup"
    RollbackManager().create_backup(str(target), str(backup_dir))
    return backup_dir


def _request(target: Path, patch: Path, backup_dir: Path) -> ApprovalRequest:
    return ApprovalRequest(
        patch_path=str(patch),
        target_path=str(target),
        backup_path=str(backup_dir),
        summary={"validation_ok": True, "test_success": True},
    )


def _audit_files(audit_dir: Path) -> list[Path]:
    return sorted(audit_dir.glob("*.json"))


class TestInstallerApproved:
    def test_approved_replaces_target_with_patch(
        self, tmp_path: Path,
    ) -> None:
        target, patch = _make_target_and_patch(tmp_path)
        backup_dir = _make_backup(tmp_path, target)
        policy = _ScriptedPolicy(
            ApprovalDecision(
                approved=True,
                approver="test",
                timestamp="2024-01-15T12:34:56+00:00",
                reason="",
            )
        )
        installer = Installer(
            policy=policy,  # type: ignore[arg-type]
            audit_dir=str(tmp_path / "decisions"),
        )

        result = installer.install(_request(target, patch, backup_dir))

        assert result.success is True
        assert result.message == "installed successfully"
        assert result.approved_by == "test"
        assert result.approval_timestamp == "2024-01-15T12:34:56+00:00"
        assert result.target_path == str(target)
        assert result.backup_path == str(backup_dir)
        assert target.read_text(encoding="utf-8") == "PATCHED"
        # No .pending leftover
        assert not target.with_suffix(target.suffix + ".pending").exists()
        # Policy was consulted exactly once
        assert len(policy.calls) == 1

    def test_approved_writes_audit_record(
        self, tmp_path: Path,
    ) -> None:
        target, patch = _make_target_and_patch(tmp_path)
        backup_dir = _make_backup(tmp_path, target)
        audit_dir = tmp_path / "decisions"
        policy = _ScriptedPolicy(
            ApprovalDecision(
                approved=True,
                approver="cli",
                timestamp="2024-01-15T12:34:56+00:00",
                reason="",
            )
        )
        installer = Installer(
            policy=policy,  # type: ignore[arg-type]
            audit_dir=str(audit_dir),
        )

        installer.install(_request(target, patch, backup_dir))

        files = _audit_files(audit_dir)
        assert len(files) == 1
        record = json.loads(files[0].read_text(encoding="utf-8"))
        assert "approved" in files[0].name
        assert record["decision"]["approved"] is True
        assert record["decision"]["approver"] == "cli"
        assert record["error"] is None
        assert record["request"]["target_path"] == str(target)
        assert record["request"]["backup_path"] == str(backup_dir)


class TestInstallerDenied:
    def test_denied_leaves_target_untouched(
        self, tmp_path: Path,
    ) -> None:
        target, patch = _make_target_and_patch(tmp_path)
        backup_dir = _make_backup(tmp_path, target)
        policy = _ScriptedPolicy(
            ApprovalDecision(
                approved=False,
                approver="cli",
                timestamp="2024-01-15T12:34:56+00:00",
                reason="user denied at prompt",
            )
        )
        installer = Installer(
            policy=policy,  # type: ignore[arg-type]
            audit_dir=str(tmp_path / "decisions"),
        )

        result = installer.install(_request(target, patch, backup_dir))

        assert result.success is False
        assert "denied" in result.message.lower()
        assert result.approved_by == "cli"
        # Target must be byte-identical to its pre-install contents
        assert target.read_text(encoding="utf-8") == "ORIGINAL"

    def test_denied_writes_audit_record(
        self, tmp_path: Path,
    ) -> None:
        target, patch = _make_target_and_patch(tmp_path)
        backup_dir = _make_backup(tmp_path, target)
        audit_dir = tmp_path / "decisions"
        policy = _ScriptedPolicy(
            ApprovalDecision(
                approved=False,
                approver="cli",
                timestamp="2024-01-15T12:34:56+00:00",
                reason="user denied at prompt",
            )
        )
        installer = Installer(
            policy=policy,  # type: ignore[arg-type]
            audit_dir=str(audit_dir),
        )

        installer.install(_request(target, patch, backup_dir))

        files = _audit_files(audit_dir)
        assert len(files) == 1
        assert "denied" in files[0].name
        record = json.loads(files[0].read_text(encoding="utf-8"))
        assert record["decision"]["approved"] is False
        assert record["decision"]["reason"] == "user denied at prompt"


class TestInstallerRollback:
    def test_install_failure_restores_from_backup(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        target, patch = _make_target_and_patch(tmp_path)
        backup_dir = _make_backup(tmp_path, target)
        policy = _ScriptedPolicy(
            ApprovalDecision(
                approved=True,
                approver="test",
                timestamp="2024-01-15T12:34:56+00:00",
                reason="",
            )
        )
        installer = Installer(
            policy=policy,  # type: ignore[arg-type]
            audit_dir=str(tmp_path / "decisions"),
        )

        # Force Path.replace to fail; the installer must catch, restore, and
        # return success=False with a message that mentions the restore.
        real_replace = Path.replace
        def _exploding_replace(self: Path, target: Path) -> Any:  # type: ignore[override]
            if self.name.endswith(".pending"):
                raise OSError("simulated rename failure")
            return real_replace(self, target)

        monkeypatch.setattr(Path, "replace", _exploding_replace)

        result = installer.install(_request(target, patch, backup_dir))

        assert result.success is False
        assert "install failed" in result.message.lower()
        assert "restored" in result.message.lower()
        # Target must be restored to ORIGINAL because rollback ran
        assert target.read_text(encoding="utf-8") == "ORIGINAL"

    def test_install_failure_records_error_in_audit(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        target, patch = _make_target_and_patch(tmp_path)
        backup_dir = _make_backup(tmp_path, target)
        audit_dir = tmp_path / "decisions"
        policy = _ScriptedPolicy(
            ApprovalDecision(
                approved=True,
                approver="test",
                timestamp="2024-01-15T12:34:56+00:00",
                reason="",
            )
        )
        installer = Installer(
            policy=policy,  # type: ignore[arg-type]
            audit_dir=str(audit_dir),
        )

        real_replace = Path.replace
        def _exploding_replace(self: Path, target: Path) -> Any:  # type: ignore[override]
            if self.name.endswith(".pending"):
                raise OSError("disk full")
            return real_replace(self, target)

        monkeypatch.setattr(Path, "replace", _exploding_replace)

        installer.install(_request(target, patch, backup_dir))

        files = _audit_files(audit_dir)
        assert len(files) == 1
        record = json.loads(files[0].read_text(encoding="utf-8"))
        assert record["decision"]["approved"] is True
        assert "disk full" in (record["error"] or "")

    def test_missing_patch_file_does_not_overwrite_target(
        self, tmp_path: Path,
    ) -> None:
        target, _ = _make_target_and_patch(tmp_path)
        patch = tmp_path / "missing_patch.py"  # never written
        backup_dir = _make_backup(tmp_path, target)
        policy = _ScriptedPolicy(
            ApprovalDecision(
                approved=True,
                approver="test",
                timestamp="2024-01-15T12:34:56+00:00",
                reason="",
            )
        )
        installer = Installer(
            policy=policy,  # type: ignore[arg-type]
            audit_dir=str(tmp_path / "decisions"),
        )

        result = installer.install(_request(target, patch, backup_dir))

        assert result.success is False
        assert "restored" in result.message.lower()
        assert target.read_text(encoding="utf-8") == "ORIGINAL"


class TestInstallerInjection:
    def test_uses_injected_policy_and_rollback(self, tmp_path: Path) -> None:
        target, patch = _make_target_and_patch(tmp_path)
        backup_dir = _make_backup(tmp_path, target)
        policy = _ScriptedPolicy(
            ApprovalDecision(
                approved=True,
                approver="injected",
                timestamp="2024-01-15T12:34:56+00:00",
                reason="",
            )
        )
        rollback = MagicMock(spec=RollbackManager)

        installer = Installer(
            policy=policy,  # type: ignore[arg-type]
            rollback=rollback,
            audit_dir=str(tmp_path / "decisions"),
        )
        result = installer.install(_request(target, patch, backup_dir))

        assert result.success is True
        assert result.approved_by == "injected"
        # Rollback was not needed on the success path
        rollback.restore.assert_not_called()


class TestInstallResultDataclass:
    def test_fields_are_immutable(self) -> None:
        result = InstallResult(
            success=True,
            message="ok",
            approved_by="cli",
            approval_timestamp="2024-01-15T12:34:56+00:00",
            target_path="app/skills/loader.py",
            backup_path="data/evolution/backups/loader.py-20240101",
        )
        with pytest.raises((AttributeError, Exception)):
            result.success = False  # type: ignore[misc]
