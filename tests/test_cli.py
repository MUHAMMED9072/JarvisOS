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
    from unittest.mock import MagicMock
    from pathlib import Path

    for d in ["runtime/build_checkpoints", "runtime/build_history"]:
        p = Path(d)
        if p.exists():
            for f in p.iterdir():
                f.unlink(missing_ok=True)

    mock_ai = MagicMock()
    mock_ai.ask.return_value = "Python tool"
    mock_ads = MagicMock()
    mock_ads.run.return_value = MagicMock(to_dict=lambda: {"artifact": "test"})
    mock_sim = MagicMock()
    mock_sim.run.return_value = MagicMock(to_dict=lambda: {"passed": True})
    mock_sandbox = MagicMock()
    mock_sandbox.run_code.return_value = MagicMock(to_dict=lambda: {"passed": True})
    mock_sandbox.run_tests.return_value = MagicMock(to_dict=lambda: {"passed": True})
    orch = BuildOrchestrator(
        ai_manager=mock_ai, ads_pipeline=mock_ads,
        simulation_pipeline=mock_sim, sandbox=mock_sandbox,
    )
    with patch("app.cli.console.print"):
        run_build(orch, "Build a test")
    stats = orch.get_statistics()
    assert stats["total_builds"] == 1


def test_stage_icons():
    from app.cli import STAGE_ICONS
    from app.autonomy.build_orchestrator import Stage

    for stage in Stage:
        assert stage in STAGE_ICONS, f"Missing icon for {stage}"
