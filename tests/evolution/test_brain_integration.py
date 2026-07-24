"""Integration tests for the EvolutionBrain install-gate wiring.

These tests verify the contract the user spelled out for P3-24:
``EvolutionBrain.evolve()`` must call ``Installer.install()`` with an
``ApprovalRequest``, and if the returned ``InstallResult.success`` is
``False``, the post-install stages (``GitManager``, ``VersionManager``,
``Benchmark``) must NOT run.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.evolution import sandbox as _sandbox_mod
from app.evolution.approval import ApprovalDecision
from app.evolution.brain import EvolutionBrain
from app.evolution.installer import InstallResult
from app.evolution.rollback import RollbackResult

# Use module-aliased imports so pytest's name-based class collector does
# not pick up ``TestResult`` / ``SandboxResult`` (both dataclasses) as
# test classes when scanning this test module.
SandboxResult = _sandbox_mod.SandboxResult


def _approved_result(target_path: str, backup_path: str) -> InstallResult:
    return InstallResult(
        success=True,
        message="installed successfully",
        approved_by="cli",
        approval_timestamp="2024-01-15T12:34:56+00:00",
        target_path=target_path,
        backup_path=backup_path,
    )


def _denied_result(target_path: str, backup_path: str) -> InstallResult:
    return InstallResult(
        success=False,
        message="install denied: user denied at prompt",
        approved_by="cli",
        approval_timestamp="2024-01-15T12:34:56+00:00",
        target_path=target_path,
        backup_path=backup_path,
    )


def _patch_stage_classes(
    monkeypatch: pytest.MonkeyPatch,
    *,
    installer_result: InstallResult,
    patch_path: Path,
) -> dict[str, MagicMock]:
    """Replace every stage in app.evolution.brain with a MagicMock stub.

    Returns the mocks for the post-install stages so the test can assert
    on them.
    """
    monkeypatch.setattr("app.evolution.brain.Analyzer", MagicMock())
    monkeypatch.setattr("app.evolution.brain.ProjectScanner", MagicMock())
    monkeypatch.setattr("app.evolution.brain.EvolutionPlanner", MagicMock())

    monkeypatch.setattr(
        "app.evolution.brain.RollbackManager",
        MagicMock(
            return_value=MagicMock(
                create_backup=MagicMock(
                    return_value=RollbackResult(True, "backup created"),
                ),
            ),
        ),
    )

    monkeypatch.setattr(
        "app.evolution.brain.CodeGenerator",
        MagicMock(
            return_value=MagicMock(
                generate_task=MagicMock(return_value=str(patch_path)),
            ),
        ),
    )

    monkeypatch.setattr("app.evolution.brain.PatchReviewer", MagicMock())
    monkeypatch.setattr("app.evolution.brain.AutoFixer", MagicMock())

    monkeypatch.setattr(
        "app.evolution.brain.PatchValidator",
        MagicMock(
            return_value=MagicMock(validate=MagicMock(return_value=(True, []))),
        ),
    )

    monkeypatch.setattr(
        "app.evolution.brain.Sandbox",
        MagicMock(
            return_value=MagicMock(
                run=MagicMock(
                    return_value=SandboxResult(
                        success=True,
                        returncode=0,
                        stdout="",
                        stderr="",
                    ),
                ),
            ),
        ),
    )

    monkeypatch.setattr(
        "app.evolution.brain.TestRunner",
        MagicMock(
            return_value=MagicMock(
                run=MagicMock(
                    return_value=MagicMock(success=True),
                ),
            ),
        ),
    )

    mock_installer = MagicMock()
    mock_installer.return_value.install.return_value = installer_result
    monkeypatch.setattr("app.evolution.brain.Installer", mock_installer)

    mock_git = MagicMock()
    mock_git.return_value.status = MagicMock()
    monkeypatch.setattr("app.evolution.brain.GitManager", mock_git)

    mock_version = MagicMock()
    mock_version.return_value.bump_patch = MagicMock()
    monkeypatch.setattr("app.evolution.brain.VersionManager", mock_version)

    mock_benchmark = MagicMock()
    mock_benchmark.return_value.run = MagicMock()
    monkeypatch.setattr("app.evolution.brain.Benchmark", mock_benchmark)

    return {
        "installer": mock_installer,
        "git": mock_git,
        "version": mock_version,
        "benchmark": mock_benchmark,
    }


def _task_one_request() -> str:
    """Default input() answer that picks TASK 1 (loader.py)."""
    return "1"


class TestEvolutionBrainInstallGate:
    def test_evolve_returns_false_and_stops_on_install_denial(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        patch_path = tmp_path / "generated_patch.py"
        patch_path.write_text("# fake patch", encoding="utf-8")
        target_path = EvolutionBrain.TASKS["1"][1]
        backup_path = str(
            tmp_path / "data" / "evolution" / "backups" / "loader.py-20240101",
        )

        mocks = _patch_stage_classes(
            monkeypatch,
            installer_result=_denied_result(target_path, backup_path),
            patch_path=patch_path,
        )
        monkeypatch.setattr("builtins.input", lambda *_a, **_k: _task_one_request())

        result = EvolutionBrain().evolve()

        assert result is False
        # The install was actually attempted
        mocks["installer"].return_value.install.assert_called_once()
        # The post-install stages must NOT have run
        mocks["git"].return_value.status.assert_not_called()
        mocks["version"].return_value.bump_patch.assert_not_called()
        mocks["benchmark"].return_value.run.assert_not_called()

    def test_evolve_returns_true_and_runs_post_install_on_approval(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        patch_path = tmp_path / "generated_patch.py"
        patch_path.write_text("# fake patch", encoding="utf-8")
        target_path = EvolutionBrain.TASKS["1"][1]
        backup_path = str(
            tmp_path / "data" / "evolution" / "backups" / "loader.py-20240101",
        )

        mocks = _patch_stage_classes(
            monkeypatch,
            installer_result=_approved_result(target_path, backup_path),
            patch_path=patch_path,
        )
        monkeypatch.setattr("builtins.input", lambda *_a, **_k: _task_one_request())

        result = EvolutionBrain().evolve()

        assert result is True
        mocks["installer"].return_value.install.assert_called_once()
        mocks["git"].return_value.status.assert_called_once()
        mocks["version"].return_value.bump_patch.assert_called_once()
        # Benchmark is called with (task, TestRunner().run) — assert it ran
        assert mocks["benchmark"].return_value.run.call_count >= 1

    def test_evolve_passes_approval_request_with_required_fields(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        patch_path = tmp_path / "generated_patch.py"
        patch_path.write_text("# fake patch", encoding="utf-8")
        target_path = EvolutionBrain.TASKS["1"][1]
        backup_path = "data/evolution/backups/loader.py-test"

        mocks = _patch_stage_classes(
            monkeypatch,
            installer_result=_approved_result(target_path, backup_path),
            patch_path=patch_path,
        )
        monkeypatch.setattr("builtins.input", lambda *_a, **_k: _task_one_request())

        EvolutionBrain().evolve()

        # Inspect the ApprovalRequest that was actually handed to the installer
        call = mocks["installer"].return_value.install.call_args
        request = call.args[0]
        assert request.patch_path == str(patch_path)
        assert request.target_path == target_path
        # backup_path is derived from Config.DATA_DIR, not the literal we
        # passed to _patch_stage_classes; we only assert that it is a string
        # and points under data/evolution/backups/.
        assert "data" in request.backup_path
        assert "evolution" in request.backup_path
        assert "backups" in request.backup_path
        # summary carries the per-stage verdicts
        assert request.summary["validation_ok"] is True
        assert request.summary["sandbox_success"] is True
        assert request.summary["test_success"] is True

    def test_evolve_returns_false_and_stops_when_backup_fails(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        # When the backup step itself fails, the installer must never be
        # called and the post-install stages must never run.
        patch_path = tmp_path / "generated_patch.py"
        patch_path.write_text("# fake patch", encoding="utf-8")

        monkeypatch.setattr("app.evolution.brain.Analyzer", MagicMock())
        monkeypatch.setattr("app.evolution.brain.ProjectScanner", MagicMock())
        monkeypatch.setattr("app.evolution.brain.EvolutionPlanner", MagicMock())
        monkeypatch.setattr(
            "app.evolution.brain.RollbackManager",
            MagicMock(
                return_value=MagicMock(
                    create_backup=MagicMock(
                        return_value=RollbackResult(False, "no source"),
                    ),
                ),
            ),
        )
        monkeypatch.setattr(
            "app.evolution.brain.CodeGenerator",
            MagicMock(
                return_value=MagicMock(
                    generate_task=MagicMock(return_value=str(patch_path)),
                ),
            ),
        )

        mock_installer = MagicMock()
        monkeypatch.setattr("app.evolution.brain.Installer", mock_installer)
        mock_git = MagicMock()
        mock_git.return_value.status = MagicMock()
        monkeypatch.setattr("app.evolution.brain.GitManager", mock_git)
        mock_version = MagicMock()
        mock_version.return_value.bump_patch = MagicMock()
        monkeypatch.setattr("app.evolution.brain.VersionManager", mock_version)
        mock_benchmark = MagicMock()
        mock_benchmark.return_value.run = MagicMock()
        monkeypatch.setattr("app.evolution.brain.Benchmark", mock_benchmark)

        monkeypatch.setattr("builtins.input", lambda *_a, **_k: "1")

        result = EvolutionBrain().evolve()

        assert result is False
        mock_installer.return_value.install.assert_not_called()
        mock_git.return_value.status.assert_not_called()
        mock_version.return_value.bump_patch.assert_not_called()
        mock_benchmark.return_value.run.assert_not_called()


def test_approval_decision_dataclass_round_trip() -> None:
    """Smoke check the dataclass the brain passes back to the installer."""
    decision = ApprovalDecision(
        approved=True,
        approver="cli",
        timestamp="2024-01-15T12:34:56+00:00",
        reason="",
    )
    assert decision.approved is True
    assert decision.reason == ""
