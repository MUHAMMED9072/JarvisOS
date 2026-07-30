from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from app.evolution.system.scanner import ImprovementOpportunity, SystemEvolutionScanner
from app.evolution.system.generator import SystemImprovementGenerator


@dataclass
class SystemEvolutionResult:
    evolution_id: str = ""
    component: str = ""
    opportunity: str = ""
    patch_id: str = ""
    sandbox_passed: bool = False
    simulation_passed: bool = False
    governance_passed: bool = False
    approved: bool = False
    installed: bool = False
    rolled_back: bool = False
    error: str = ""
    timestamp: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "evolution_id": self.evolution_id,
            "component": self.component,
            "opportunity": self.opportunity,
            "patch_id": self.patch_id,
            "sandbox_passed": self.sandbox_passed,
            "simulation_passed": self.simulation_passed,
            "governance_passed": self.governance_passed,
            "approved": self.approved,
            "installed": self.installed,
            "rolled_back": self.rolled_back,
            "error": self.error,
            "timestamp": self.timestamp,
        }


class SystemEvolutionPipeline:
    """Orchestrates the full system evolution pipeline.

    Stages: scan → generate → sandbox → simulate → governance → approve → install
    Uses callable hooks for integration points so existing infrastructure
    (Sandbox, SimulationPipeline, PolicyEngine, Installer, etc.) is reused.
    """

    def __init__(
        self,
        scanner: SystemEvolutionScanner | None = None,
        generator: SystemImprovementGenerator | None = None,
        sandbox_hook: Callable[[str], dict[str, Any]] | None = None,
        simulation_hook: Callable[[str], dict[str, Any]] | None = None,
        governance_hook: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
        approval_hook: Callable[[dict[str, Any]], bool] | None = None,
        install_hook: Callable[[str], bool] | None = None,
        rollback_hook: Callable[[str], bool] | None = None,
        evolution_coordinator: Any = None,
    ) -> None:
        self._scanner = scanner or SystemEvolutionScanner()
        self._generator = generator or SystemImprovementGenerator()
        self._sandbox = sandbox_hook
        self._simulate = simulation_hook
        self._governance = governance_hook
        self._approve = approval_hook
        self._install = install_hook
        self._rollback = rollback_hook
        self._coordinator = evolution_coordinator
        self._lock = threading.RLock()
        self._results: list[SystemEvolutionResult] = []
        self._max_results = 1000

    def run_evolution(
        self,
        component: str,
        opportunity: ImprovementOpportunity | None = None,
    ) -> SystemEvolutionResult:
        evolution_id = uuid.uuid4().hex[:16]
        timestamp = time.time()
        result = SystemEvolutionResult(
            evolution_id=evolution_id,
            component=component,
            timestamp=timestamp,
        )

        try:
            if self._coordinator is not None:
                if not self._coordinator.window_available(component):
                    result.error = f"Evolution window not available for {component}"
                    self._record_result(result)
                    return result
                self._coordinator.open_window(component, duration=300)

            # Stage 1: Scan
            opps = self._scanner.scan_component(component)
            if not opps:
                result.error = f"No improvement opportunities found for {component}"
                self._record_result(result)
                return result

            opp = opportunity or opps[0]
            result.opportunity = opp.description
            source_root = str(self._scanner._root)

            # Stage 2: Generate patch
            patch = self._generator.generate_patch(opp, source_root)
            if not patch:
                result.error = "Failed to generate patch"
                self._record_result(result)
                return result

            patch_id = patch["patch_id"]
            result.patch_id = patch_id

            # Stage 3: Sandbox
            if self._sandbox:
                sandbox_result = self._sandbox(patch["patch_file"])
                result.sandbox_passed = sandbox_result.get("success", False)
                if not result.sandbox_passed:
                    result.error = sandbox_result.get("error", "Sandbox failed")
                    self._record_result(result)
                    return result

            # Stage 4: Simulation
            if self._simulate:
                sim_result = self._simulate(patch["patch_file"])
                result.simulation_passed = sim_result.get("passed", False)
                if not result.simulation_passed:
                    result.error = sim_result.get("summary", "Simulation failed")
                    self._record_result(result)
                    return result

            # Stage 5: Governance
            if self._governance:
                gov_decision = self._governance({
                    "component": component,
                    "patch_id": patch_id,
                    "target_file": opp.target_file,
                    "category": opp.category,
                    "severity": opp.severity,
                    "sandbox_passed": result.sandbox_passed,
                    "simulation_passed": result.simulation_passed,
                })
                result.governance_passed = gov_decision.get("allowed", False)
                if not result.governance_passed:
                    result.error = gov_decision.get("reason", "Governance rejected")
                    self._record_result(result)
                    return result

            # Stage 6: Approval
            if self._approve:
                result.approved = self._approve({
                    "component": component,
                    "patch_id": patch_id,
                    "description": opp.description,
                    "severity": opp.severity,
                    "governance_passed": result.governance_passed,
                })
                if not result.approved:
                    result.error = "Human approval denied"
                    self._record_result(result)
                    return result
            else:
                result.approved = True

            # Stage 7: Install
            if self._install:
                result.installed = self._install(patch["patch_file"])
                if not result.installed:
                    result.error = "Installation failed"
                    # Attempt rollback
                    if self._rollback:
                        result.rolled_back = self._rollback(patch["patch_file"])
                    self._record_result(result)
                    return result
            else:
                result.installed = True

            self._generator.mark_applied(patch_id)

            if self._coordinator is not None:
                try:
                    self._coordinator.commit()
                except Exception:
                    pass

        except Exception as e:
            result.error = str(e)
            result.rolled_back = bool(self._rollback and self._rollback(""))

        self._record_result(result)
        return result

    def run_batch(
        self,
        components: list[str] | None = None,
    ) -> list[SystemEvolutionResult]:
        targets = components or list(
            __import__("app.evolution.system.scanner", fromlist=["SYSTEM_COMPONENTS"])
            .SYSTEM_COMPONENTS.keys()
        )
        results: list[SystemEvolutionResult] = []
        for comp in targets:
            result = self.run_evolution(comp)
            results.append(result)
        return results

    def _record_result(self, result: SystemEvolutionResult) -> None:
        with self._lock:
            self._results.append(result)
            if len(self._results) > self._max_results:
                self._results = self._results[-self._max_results:]

    def get_results(
        self,
        component: str | None = None,
        limit: int = 50,
    ) -> list[SystemEvolutionResult]:
        with self._lock:
            if component:
                filtered = [r for r in self._results if r.component == component]
            else:
                filtered = list(self._results)
            return filtered[-limit:]

    def get_statistics(self) -> dict[str, Any]:
        with self._lock:
            total = len(self._results)
            installed = sum(1 for r in self._results if r.installed)
            failed = sum(1 for r in self._results if r.error)
            rolled_back = sum(1 for r in self._results if r.rolled_back)
        return {
            "total_attempts": total,
            "successful_installs": installed,
            "failed": failed,
            "rolled_back": rolled_back,
            "success_rate": round(installed / max(total, 1), 4),
        }

    def health(self) -> dict[str, Any]:
        stats = self.get_statistics()
        return {
            "alive": True,
            "total_attempts": stats["total_attempts"],
            "successful_installs": stats["successful_installs"],
            "success_rate": stats["success_rate"],
        }
