from __future__ import annotations

from unittest.mock import patch

import pytest


def test_cli_import():
    from app.cli import main, run_build, run_interactive, run_status, STAGE_ICONS
    assert callable(main)
    assert callable(run_build)
    assert callable(run_status)
    assert len(STAGE_ICONS) > 0


def test_cli_build_command():
    from app.cli import run_build
    from app.autonomy.build_orchestrator import BuildOrchestrator

    orch = BuildOrchestrator()
    with patch("app.cli.console.print"):
        run_build(orch, "Build a test")
    stats = orch.get_statistics()
    assert stats["total_builds"] == 1


def test_stage_icons():
    from app.cli import STAGE_ICONS
    from app.autonomy.build_orchestrator import Stage

    for stage in Stage:
        assert stage in STAGE_ICONS, f"Missing icon for {stage}"
