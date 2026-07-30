from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.evolution.framework.compatibility import CompatibilityChecker, CompatibilityResult
from app.evolution.framework.generator import FrameworkImprovementGenerator
from app.evolution.framework.manager import FrameworkEvolutionManager
from app.evolution.framework.scanner import FrameworkEvolutionScanner, FrameworkImprovement
from app.evolution.framework.upgrade import RollingUpgradeManager, UpgradeResult


class TestFrameworkImprovement:
    def test_to_dict(self):
        imp = FrameworkImprovement(
            target_module="app/agents/base.py", target_class="Agent",
            target_method="execute", category="missing_docstring",
            description="No docs", severity="low", line_number=10,
        )
        d = imp.to_dict()
        assert d["target_module"] == "app/agents/base.py"
        assert d["category"] == "missing_docstring"

    def test_to_dict_defaults(self):
        imp = FrameworkImprovement()
        d = imp.to_dict()
        assert d["target_module"] == ""


class TestUpgradeResult:
    def test_to_dict(self):
        r = UpgradeResult(
            upgrade_id="u1", target_module="base.py", patch_id="p1",
            agents_upgraded=5, total_agents=5, completed=True,
        )
        d = r.to_dict()
        assert d["upgrade_id"] == "u1"
        assert d["completed"] is True

    def test_to_dict_defaults(self):
        r = UpgradeResult()
        d = r.to_dict()
        assert d["completed"] is False


class TestFrameworkEvolutionScanner:
    @pytest.fixture
    def scanner(self):
        return FrameworkEvolutionScanner(root_path="app")

    def test_health(self, scanner):
        h = scanner.health()
        assert h["alive"] is True
        assert h["modules_tracked"] == 14

    def test_scan_framework(self, scanner):
        results = scanner.scan_framework()
        assert isinstance(results, list)

    def test_scan_module(self, scanner):
        results = scanner.scan_module("base.py")
        assert isinstance(results, list)

    def test_scan_statistics(self, scanner):
        stats = scanner.get_statistics()
        assert "total_improvements" in stats
        assert "by_severity" in stats


class TestFrameworkImprovementGenerator:
    @pytest.fixture
    def generator(self):
        return FrameworkImprovementGenerator()

    def test_health(self, generator):
        h = generator.health()
        assert h["alive"] is True

    def test_generate_patch_nonexistent(self, generator):
        imp = FrameworkImprovement(target_module="nonexistent.py")
        result = generator.generate_patch(imp)
        assert result is None

    def test_generate_patch(self, generator, tmp_path):
        src = tmp_path / "test_agent.py"
        src.write_text("class Agent:\n    def execute(self):\n        pass\n")
        imp = FrameworkImprovement(
            target_module=str(src), target_class="Agent",
            target_method="execute", category="missing_docstring",
            description="Needs docstring", severity="low", line_number=2,
        )
        result = generator.generate_patch(imp, source_root=str(tmp_path))
        assert result is not None
        assert result["patch_id"] is not None
        assert Path(result["patch_file"]).exists()

    def test_generate_batch(self, generator, tmp_path):
        src = tmp_path / "mod.py"
        src.write_text("class A:\n    def f(self): pass\n    def g(self): pass\n")
        imps = [
            FrameworkImprovement(
                target_module=str(src), target_class="A",
                target_method="f", category="missing_docstring",
                description="d1", severity="low", line_number=2,
            ),
            FrameworkImprovement(
                target_module=str(src), target_class="A",
                target_method="g", category="missing_docstring",
                description="d2", severity="low", line_number=3,
            ),
        ]
        patches = generator.generate_batch(imps, source_root=str(tmp_path))
        assert len(patches) == 2

    def test_get_patch(self, generator, tmp_path):
        src = tmp_path / "m.py"
        src.write_text("def foo():\n    pass\n")
        imp = FrameworkImprovement(
            target_module=str(src), category="missing_docstring",
            description="d", severity="low", line_number=1,
        )
        result = generator.generate_patch(imp, source_root=str(tmp_path))
        retrieved = generator.get_patch(result["patch_id"])
        assert retrieved is not None

    def test_get_patch_nonexistent(self, generator):
        assert generator.get_patch("no-id") is None

    def test_mark_applied(self, generator, tmp_path):
        src = tmp_path / "m.py"
        src.write_text("def f():\n    pass\n")
        imp = FrameworkImprovement(
            target_module=str(src), category="missing_docstring",
            description="d", severity="low", line_number=1,
        )
        result = generator.generate_patch(imp, source_root=str(tmp_path))
        assert generator.mark_applied(result["patch_id"]) is True
        assert generator.get_patch(result["patch_id"])["applied"] is True

    def test_statistics(self, generator, tmp_path):
        src = tmp_path / "m.py"
        src.write_text("def f():\n    pass\n")
        imp = FrameworkImprovement(
            target_module=str(src), category="missing_docstring",
            description="d", severity="low", line_number=1,
        )
        generator.generate_patch(imp, source_root=str(tmp_path))
        stats = generator.get_statistics()
        assert stats["total_patches"] >= 1


class TestCompatibilityChecker:
    @pytest.fixture
    def checker(self):
        return CompatibilityChecker()

    def test_health(self, checker):
        assert checker.health()["alive"] is True

    def test_compatible_patch(self, checker):
        content = "def foo(x: int) -> str:\n    return str(x)\n"
        result = checker.check_patch_compatibility(content, "test.py")
        assert result.compatible is True

    def test_interface_compatibility_removed_method(self, checker):
        old = {"Agent": ["execute", "cleanup"]}
        new = {"Agent": ["execute"]}
        result = checker.check_interface_compatibility(old, new)
        assert result.compatible is False
        assert any("cleanup" in c for c in result.breaking_changes)

    def test_interface_compatibility_stable(self, checker):
        old = {"Agent": ["execute", "cleanup"]}
        new = {"Agent": ["execute", "cleanup", "new_method"]}
        result = checker.check_interface_compatibility(old, new)
        assert result.compatible is True


class TestRollingUpgradeManager:
    @pytest.fixture
    def manager(self):
        return RollingUpgradeManager()

    def test_health(self, manager):
        h = manager.health()
        assert h["alive"] is True

    def test_rolling_upgrade_no_hook(self, manager):
        result = manager.rolling_upgrade(
            ["agent1", "agent2"], "base.py", "patch1",
        )
        assert result.completed is True
        assert result.agents_upgraded == 2

    def test_rolling_upgrade_with_hook(self):
        mock_upgrade = MagicMock()
        mock_upgrade.return_value = True
        manager = RollingUpgradeManager(agent_upgrade_hook=mock_upgrade)
        result = manager.rolling_upgrade(
            ["agent1", "agent2"], "base.py", "patch1",
        )
        assert result.completed is True
        assert result.agents_upgraded == 2
        assert mock_upgrade.call_count == 2

    def test_rolling_upgrade_partial_failure(self):
        calls = 0

        def upgrade(agent_id, patch):
            nonlocal calls
            calls += 1
            return calls <= 1

        manager = RollingUpgradeManager(agent_upgrade_hook=upgrade)
        result = manager.rolling_upgrade(
            ["agent1", "agent2", "agent3"], "base.py", "patch1",
        )
        assert result.agents_upgraded == 1
        assert result.agents_failed >= 1

    def test_rolling_upgrade_with_health_check(self):
        mock_upgrade = MagicMock()
        mock_upgrade.return_value = True
        mock_health = MagicMock()
        mock_health.return_value = False
        manager = RollingUpgradeManager(
            agent_upgrade_hook=mock_upgrade,
            agent_health_hook=mock_health,
        )
        result = manager.rolling_upgrade(
            ["agent1"], "base.py", "patch1",
        )
        assert result.agents_upgraded == 1  # upgraded but unhealthy
        assert result.agents_failed == 1

    def test_get_upgrade(self, manager):
        result = manager.rolling_upgrade(["a1"], "base.py", "p1")
        retrieved = manager.get_upgrade(result.upgrade_id)
        assert retrieved is not None
        assert retrieved.upgrade_id == result.upgrade_id

    def test_get_upgrade_nonexistent(self, manager):
        assert manager.get_upgrade("no-id") is None

    def test_statistics(self, manager):
        manager.rolling_upgrade(["a1", "a2"], "base.py", "p1")
        stats = manager.get_statistics()
        assert stats["total_upgrades"] == 1
        assert stats["total_agents"] == 2


class TestFrameworkEvolutionManager:
    @pytest.fixture
    def manager(self):
        return FrameworkEvolutionManager()

    def test_health(self, manager):
        h = manager.health()
        assert h["alive"] is True

    def test_scan(self, manager):
        results = manager.scan()
        assert isinstance(results, list)

    def test_generate_patches(self, manager):
        patches = manager.generate_patches([])
        assert patches == []

    def test_check_compatibility_nonexistent(self, manager):
        result = manager.check_compatibility("test.py", "no-such-patch")
        assert result is None

    def test_rolling_upgrade(self, manager):
        result = manager.rolling_upgrade(["agent1"], "base.py", "patch1")
        assert result is not None

    def test_statistics(self, manager):
        stats = manager.get_statistics()
        assert "improvements_found" in stats

    def test_with_graph_store(self):
        mock_graph = MagicMock()
        manager = FrameworkEvolutionManager(graph_store=mock_graph)
        manager.rolling_upgrade(["a1"], "base.py", "p1")
        mock_graph.create_entity.assert_called_once()

    def test_with_event_bus(self):
        mock_bus = MagicMock()
        manager = FrameworkEvolutionManager(event_bus=mock_bus)
        manager.rolling_upgrade(["a1"], "base.py", "p1")
        mock_bus.publish.assert_called_once()
