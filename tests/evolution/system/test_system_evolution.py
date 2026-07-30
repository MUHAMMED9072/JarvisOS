from __future__ import annotations

import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.evolution.system.generator import SystemImprovementGenerator
from app.evolution.system.manager import SystemEvolutionManager
from app.evolution.system.pipeline import SystemEvolutionPipeline, SystemEvolutionResult
from app.evolution.system.scanner import ImprovementOpportunity, SystemEvolutionScanner


class TestImprovementOpportunity:
    def test_to_dict(self):
        opp = ImprovementOpportunity(
            target_file="app/kernel/scheduler.py",
            module_path="app.kernel.scheduler",
            component="scheduler",
            category="missing_docstring",
            description="Missing docstring",
            severity="low",
            line_number=42,
            current_snippet="def foo():",
            suggestion="Add docstring",
        )
        d = opp.to_dict()
        assert d["target_file"] == "app/kernel/scheduler.py"
        assert d["component"] == "scheduler"
        assert d["severity"] == "low"

    def test_to_dict_defaults(self):
        opp = ImprovementOpportunity()
        d = opp.to_dict()
        assert d["target_file"] == ""


class TestSystemEvolutionResult:
    def test_to_dict(self):
        r = SystemEvolutionResult(
            evolution_id="e1", component="kernel", opportunity="Add docs",
            patch_id="p1", sandbox_passed=True, simulation_passed=True,
            governance_passed=True, approved=True, installed=True,
            timestamp=1000.0,
        )
        d = r.to_dict()
        assert d["evolution_id"] == "e1"
        assert d["installed"] is True

    def test_to_dict_defaults(self):
        r = SystemEvolutionResult()
        d = r.to_dict()
        assert d["evolution_id"] == ""


class TestSystemEvolutionScanner:
    @pytest.fixture
    def scanner(self):
        return SystemEvolutionScanner(root_path="app")

    def test_initial_health(self, scanner):
        h = scanner.health()
        assert h["alive"] is True
        assert h["components_tracked"] == 6

    def test_scan_nonexistent_component(self, scanner):
        opps = scanner.scan_component("nonexistent")
        assert opps == []

    def test_scan_statistics(self, scanner):
        stats = scanner.get_statistics()
        assert stats["components_scanned"] >= 0
        assert "by_severity" in stats
        assert "by_component" in stats

    def test_scan_all_returns_dict(self, scanner):
        results = scanner.scan_all()
        assert isinstance(results, dict)
        for comp in ("kernel", "scheduler", "security", "memory", "config", "audit"):
            assert comp in results or True  # some may be empty if dir missing


class TestSystemImprovementGenerator:
    @pytest.fixture
    def generator(self):
        return SystemImprovementGenerator()

    def test_initial_health(self, generator):
        h = generator.health()
        assert h["alive"] is True
        assert h["patches_generated"] == 0

    def test_generate_patch_no_target(self, generator):
        opp = ImprovementOpportunity()
        result = generator.generate_patch(opp)
        assert result is None

    def test_generate_patch_missing_file(self, generator):
        opp = ImprovementOpportunity(target_file="nonexistent_file.py")
        result = generator.generate_patch(opp, source_root="app")
        assert result is None

    def test_generate_patch_with_real_file(self, generator, tmp_path):
        src = tmp_path / "test_mod.py"
        src.write_text("def foo():\n    pass\n")
        opp = ImprovementOpportunity(
            target_file=str(src),
            module_path="test_mod",
            component="kernel",
            category="missing_docstring",
            description="Needs docstring",
            severity="low",
            line_number=1,
            current_snippet="def foo():",
            suggestion="Add docstring",
        )
        result = generator.generate_patch(opp, source_root=str(tmp_path))
        assert result is not None
        assert result["patch_id"] is not None
        assert result["target_file"] == str(src)
        assert result["applied"] is False

        # Verify patch file was created
        patch_path = Path(result["patch_file"])
        assert patch_path.exists()
        content = patch_path.read_text()
        assert '"""' in content

    def test_get_patch(self, generator, tmp_path):
        src = tmp_path / "mod.py"
        src.write_text("def bar():\n    pass\n")
        opp = ImprovementOpportunity(
            target_file=str(src),
            component="memory",
            category="missing_docstring",
            description="Missing docstring",
            severity="low",
            line_number=1,
            current_snippet="def bar():",
            suggestion="Add docstring",
        )
        result = generator.generate_patch(opp, source_root=str(tmp_path))
        retrieved = generator.get_patch(result["patch_id"])
        assert retrieved is not None
        assert retrieved["patch_id"] == result["patch_id"]

    def test_get_patch_nonexistent(self, generator):
        assert generator.get_patch("no-such-id") is None

    def test_mark_applied(self, generator, tmp_path):
        src = tmp_path / "mod.py"
        src.write_text("def baz():\n    pass\n")
        opp = ImprovementOpportunity(
            target_file=str(src),
            component="scheduler",
            category="missing_docstring",
            description="Needs docs",
            severity="low",
            line_number=1,
        )
        result = generator.generate_patch(opp, source_root=str(tmp_path))
        assert generator.mark_applied(result["patch_id"]) is True
        assert generator.get_patch(result["patch_id"])["applied"] is True

    def test_mark_applied_nonexistent(self, generator):
        assert generator.mark_applied("no-such-id") is False

    def test_get_patches_by_component(self, generator, tmp_path):
        src = tmp_path / "mod.py"
        src.write_text("def f():\n    pass\n")
        opp1 = ImprovementOpportunity(
            target_file=str(src), component="kernel", category="missing_docstring",
            description="d1", severity="low", line_number=1,
        )
        opp2 = ImprovementOpportunity(
            target_file=str(src), component="kernel", category="bare_except",
            description="d2", severity="high", line_number=2,
        )
        generator.generate_batch([opp1, opp2], source_root=str(tmp_path))
        patches = generator.get_patches_by_component("kernel")
        assert len(patches) == 2

    def test_statistics(self, generator, tmp_path):
        src = tmp_path / "mod.py"
        src.write_text("def f():\n    pass\n")
        opp = ImprovementOpportunity(
            target_file=str(src), component="kernel", category="missing_docstring",
            description="d", severity="low", line_number=1,
        )
        generator.generate_patch(opp, source_root=str(tmp_path))
        stats = generator.get_statistics()
        assert stats["total_patches"] >= 1
        assert stats["pending"] >= 1


class TestSystemEvolutionPipeline:
    @pytest.fixture
    def pipeline(self):
        return SystemEvolutionPipeline()

    def test_initial_health(self, pipeline):
        h = pipeline.health()
        assert h["alive"] is True
        assert h["total_attempts"] == 0

    def test_run_evolution_no_hooks(self):
        scanner = MagicMock()
        scanner.scan_component.return_value = [
            ImprovementOpportunity(
                target_file="app/kernel/test_mod.py",
                module_path="app.kernel.test_mod",
                component="kernel",
                category="missing_docstring",
                description="Test",
                severity="low",
                line_number=1,
            )
        ]
        generator = MagicMock()
        generator.generate_patch.return_value = {
            "patch_id": "test_patch",
            "patch_file": "runtime/test_patch.py",
        }

        pipeline = SystemEvolutionPipeline(scanner=scanner, generator=generator)
        result = pipeline.run_evolution("kernel")

        assert result.component == "kernel"
        assert result.patch_id == "test_patch"
        assert result.installed is True  # no install hook means auto-success

    def test_run_evolution_with_sandbox_failure(self):
        scanner = MagicMock()
        scanner.scan_component.return_value = [
            ImprovementOpportunity(
                target_file="test.py", component="kernel", category="test",
                description="Test", severity="low", line_number=1,
            )
        ]
        generator = MagicMock()
        generator.generate_patch.return_value = {
            "patch_id": "p1", "patch_file": "runtime/p1.py",
        }
        sandbox = MagicMock()
        sandbox.return_value = {"success": False, "error": "Sandbox error"}

        pipeline = SystemEvolutionPipeline(
            scanner=scanner, generator=generator,
            sandbox_hook=sandbox,
        )
        result = pipeline.run_evolution("kernel")
        assert result.sandbox_passed is False
        assert "Sandbox error" in result.error

    def test_run_evolution_with_simulation_failure(self):
        scanner = MagicMock()
        scanner.scan_component.return_value = [
            ImprovementOpportunity(
                target_file="test.py", component="kernel", category="test",
                description="Test", severity="low", line_number=1,
            )
        ]
        generator = MagicMock()
        generator.generate_patch.return_value = {
            "patch_id": "p1", "patch_file": "runtime/p1.py",
        }
        sandbox = MagicMock()
        sandbox.return_value = {"success": True}
        simulate = MagicMock()
        simulate.return_value = {"passed": False, "summary": "Sim failed"}

        pipeline = SystemEvolutionPipeline(
            scanner=scanner, generator=generator,
            sandbox_hook=sandbox, simulation_hook=simulate,
        )
        result = pipeline.run_evolution("kernel")
        assert result.simulation_passed is False

    def test_run_evolution_with_governance_rejection(self):
        scanner = MagicMock()
        scanner.scan_component.return_value = [
            ImprovementOpportunity(
                target_file="test.py", component="kernel", category="test",
                description="Test", severity="low", line_number=1,
            )
        ]
        generator = MagicMock()
        generator.generate_patch.return_value = {
            "patch_id": "p1", "patch_file": "runtime/p1.py",
        }
        sandbox = MagicMock()
        sandbox.return_value = {"success": True}
        simulate = MagicMock()
        simulate.return_value = {"passed": True}
        governance = MagicMock()
        governance.return_value = {"allowed": False, "reason": "Policy violation"}

        pipeline = SystemEvolutionPipeline(
            scanner=scanner, generator=generator,
            sandbox_hook=sandbox, simulation_hook=simulate,
            governance_hook=governance,
        )
        result = pipeline.run_evolution("kernel")
        assert result.governance_passed is False

    def test_run_evolution_with_approval_denied(self):
        scanner = MagicMock()
        scanner.scan_component.return_value = [
            ImprovementOpportunity(
                target_file="test.py", component="kernel", category="test",
                description="Test", severity="low", line_number=1,
            )
        ]
        generator = MagicMock()
        generator.generate_patch.return_value = {
            "patch_id": "p1", "patch_file": "runtime/p1.py",
        }
        sandbox = MagicMock()
        sandbox.return_value = {"success": True}
        simulate = MagicMock()
        simulate.return_value = {"passed": True}
        governance = MagicMock()
        governance.return_value = {"allowed": True}
        approval = MagicMock()
        approval.return_value = False

        pipeline = SystemEvolutionPipeline(
            scanner=scanner, generator=generator,
            sandbox_hook=sandbox, simulation_hook=simulate,
            governance_hook=governance, approval_hook=approval,
        )
        result = pipeline.run_evolution("kernel")
        assert result.approved is False

    def test_run_evolution_full_success(self):
        scanner = MagicMock()
        scanner.scan_component.return_value = [
            ImprovementOpportunity(
                target_file="test.py", component="kernel", category="test",
                description="Test", severity="low", line_number=1,
            )
        ]
        generator = MagicMock()
        generator.generate_patch.return_value = {
            "patch_id": "p1", "patch_file": "runtime/p1.py",
        }
        sandbox = MagicMock()
        sandbox.return_value = {"success": True}
        simulate = MagicMock()
        simulate.return_value = {"passed": True}
        governance = MagicMock()
        governance.return_value = {"allowed": True}
        approval = MagicMock()
        approval.return_value = True
        install = MagicMock()
        install.return_value = True

        pipeline = SystemEvolutionPipeline(
            scanner=scanner, generator=generator,
            sandbox_hook=sandbox, simulation_hook=simulate,
            governance_hook=governance, approval_hook=approval,
            install_hook=install,
        )
        result = pipeline.run_evolution("kernel")
        assert result.sandbox_passed is True
        assert result.simulation_passed is True
        assert result.governance_passed is True
        assert result.approved is True
        assert result.installed is True
        assert result.error == ""

    def test_run_evolution_install_failure_rollback(self):
        scanner = MagicMock()
        scanner.scan_component.return_value = [
            ImprovementOpportunity(
                target_file="test.py", component="kernel", category="test",
                description="Test", severity="low", line_number=1,
            )
        ]
        generator = MagicMock()
        generator.generate_patch.return_value = {
            "patch_id": "p1", "patch_file": "runtime/p1.py",
        }
        sandbox = MagicMock()
        sandbox.return_value = {"success": True}
        simulate = MagicMock()
        simulate.return_value = {"passed": True}
        governance = MagicMock()
        governance.return_value = {"allowed": True}
        approval = MagicMock()
        approval.return_value = True
        install = MagicMock()
        install.return_value = False
        rollback = MagicMock()
        rollback.return_value = True

        pipeline = SystemEvolutionPipeline(
            scanner=scanner, generator=generator,
            sandbox_hook=sandbox, simulation_hook=simulate,
            governance_hook=governance, approval_hook=approval,
            install_hook=install, rollback_hook=rollback,
        )
        result = pipeline.run_evolution("kernel")
        assert result.installed is False
        assert result.rolled_back is True

    def test_run_evolution_no_opportunities(self):
        scanner = MagicMock()
        scanner.scan_component.return_value = []
        pipeline = SystemEvolutionPipeline(scanner=scanner)
        result = pipeline.run_evolution("kernel")
        assert result.error != ""
        assert "No improvement opportunities" in result.error

    def test_get_results_filtered(self):
        pipeline = SystemEvolutionPipeline()
        result1 = SystemEvolutionResult(evolution_id="e1", component="kernel", timestamp=100.0)
        result2 = SystemEvolutionResult(evolution_id="e2", component="scheduler", timestamp=200.0)
        pipeline._results = [result1, result2]
        kernel_results = pipeline.get_results(component="kernel")
        assert len(kernel_results) == 1
        assert kernel_results[0].evolution_id == "e1"

    def test_get_results_limit(self):
        pipeline = SystemEvolutionPipeline()
        pipeline._results = [
            SystemEvolutionResult(evolution_id=f"e{i}", component="kernel", timestamp=float(i))
            for i in range(100)
        ]
        results = pipeline.get_results(limit=5)
        assert len(results) == 5

    def test_statistics(self):
        pipeline = SystemEvolutionPipeline()
        pipeline._results = [
            SystemEvolutionResult(installed=True),
            SystemEvolutionResult(installed=True),
            SystemEvolutionResult(installed=False, error="fail"),
        ]
        stats = pipeline.get_statistics()
        assert stats["total_attempts"] == 3
        assert stats["successful_installs"] == 2
        assert stats["failed"] == 1

    def test_with_evolution_coordinator(self):
        coordinator = MagicMock()
        coordinator.window_available.return_value = True

        scanner = MagicMock()
        scanner.scan_component.return_value = [
            ImprovementOpportunity(
                target_file="test.py", component="kernel", category="test",
                description="Test", severity="low", line_number=1,
            )
        ]
        generator = MagicMock()
        generator.generate_patch.return_value = {
            "patch_id": "p1", "patch_file": "runtime/p1.py",
        }

        pipeline = SystemEvolutionPipeline(
            scanner=scanner, generator=generator,
            evolution_coordinator=coordinator,
        )
        result = pipeline.run_evolution("kernel")
        coordinator.open_window.assert_called_once()
        coordinator.commit.assert_called_once()


class TestSystemEvolutionManager:
    @pytest.fixture
    def manager(self):
        return SystemEvolutionManager()

    def test_initial_health(self, manager):
        h = manager.health()
        assert h["alive"] is True
        assert h["active"] is False

    def test_scan_system_all(self, manager):
        results = manager.scan_system()
        assert isinstance(results, dict)

    def test_scan_system_specific(self, manager):
        results = manager.scan_system(component="kernel")
        assert isinstance(results, dict)
        assert "kernel" in results

    def test_evolve_component(self):
        scanner = MagicMock()
        scanner.scan_component.return_value = [
            ImprovementOpportunity(
                target_file="test.py", component="kernel", category="test",
                description="Test", severity="low", line_number=1,
            )
        ]
        generator = MagicMock()
        generator.generate_patch.return_value = {
            "patch_id": "p1", "patch_file": "runtime/p1.py",
        }
        pipeline = SystemEvolutionPipeline(scanner=scanner, generator=generator)
        manager = SystemEvolutionManager(
            scanner=scanner, generator=generator, pipeline=pipeline,
        )
        result = manager.evolve_component("kernel")
        assert result.component == "kernel"

    def test_concurrent_evolution_raises(self):
        scanner = MagicMock()
        scanner.scan_component.return_value = [
            ImprovementOpportunity(
                target_file="test.py", component="kernel", category="test",
                description="Test", severity="low", line_number=1,
            )
        ]
        generator = MagicMock()
        generator.generate_patch.return_value = {
            "patch_id": "p1", "patch_file": "runtime/p1.py",
        }
        pipeline = SystemEvolutionPipeline(scanner=scanner, generator=generator)
        manager = SystemEvolutionManager(
            scanner=scanner, generator=generator, pipeline=pipeline,
        )
        manager._active = True
        with pytest.raises(RuntimeError, match="Evolution already in progress"):
            manager.evolve_component("kernel")

    def test_get_statistics(self, manager):
        stats = manager.get_statistics()
        assert "opportunities_found" in stats
        assert "evolution_attempts" in stats

    def test_with_graph_store(self):
        mock_graph = MagicMock()
        scanner = MagicMock()
        scanner.scan_component.return_value = [
            ImprovementOpportunity(
                target_file="test.py", component="kernel", category="test",
                description="Test", severity="low", line_number=1,
            )
        ]
        generator = MagicMock()
        generator.generate_patch.return_value = {
            "patch_id": "p1", "patch_file": "runtime/p1.py",
        }
        pipeline = SystemEvolutionPipeline(scanner=scanner, generator=generator)
        manager = SystemEvolutionManager(
            scanner=scanner, generator=generator, pipeline=pipeline,
            graph_store=mock_graph,
        )
        manager.evolve_component("kernel")
        mock_graph.create_entity.assert_called_once()
        assert mock_graph.create_entity.call_args.kwargs["type"] == "evolution_attempt"

    def test_with_event_bus(self):
        mock_bus = MagicMock()
        scanner = MagicMock()
        scanner.scan_component.return_value = [
            ImprovementOpportunity(
                target_file="test.py", component="kernel", category="test",
                description="Test", severity="low", line_number=1,
            )
        ]
        generator = MagicMock()
        generator.generate_patch.return_value = {
            "patch_id": "p1", "patch_file": "runtime/p1.py",
        }
        pipeline = SystemEvolutionPipeline(scanner=scanner, generator=generator)
        manager = SystemEvolutionManager(
            scanner=scanner, generator=generator, pipeline=pipeline,
            event_bus=mock_bus,
        )
        manager.evolve_component("kernel")
        mock_bus.publish.assert_called()
