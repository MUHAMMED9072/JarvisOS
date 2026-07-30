from __future__ import annotations

import threading
import time
from typing import Any

from app.evolution.system.scanner import SystemEvolutionScanner, ImprovementOpportunity
from app.evolution.system.generator import SystemImprovementGenerator
from app.evolution.system.pipeline import SystemEvolutionPipeline, SystemEvolutionResult


class SystemEvolutionManager:
    """Entry point for system-level self-evolution.

    Coordinates scanning, patch generation, pipeline execution,
    and result tracking for all kernel/system components.
    """

    def __init__(
        self,
        scanner: SystemEvolutionScanner | None = None,
        generator: SystemImprovementGenerator | None = None,
        pipeline: SystemEvolutionPipeline | None = None,
        graph_store: Any = None,
        event_bus: Any = None,
    ) -> None:
        self._scanner = scanner or SystemEvolutionScanner()
        self._generator = generator or SystemImprovementGenerator()
        self._pipeline = pipeline or SystemEvolutionPipeline(
            scanner=self._scanner,
            generator=self._generator,
        )
        self._graph = graph_store
        self._bus = event_bus
        self._lock = threading.RLock()
        self._active = False

    def scan_system(self, component: str | None = None) -> dict[str, list[ImprovementOpportunity]]:
        if component:
            return {component: self._scanner.scan_component(component)}
        return self._scanner.scan_all()

    def evolve_component(self, component: str) -> SystemEvolutionResult:
        with self._lock:
            if self._active:
                raise RuntimeError("Evolution already in progress")
            self._active = True

        try:
            result = self._pipeline.run_evolution(component)

            if self._graph:
                try:
                    self._graph.create_entity(
                        type="evolution_attempt",
                        name=f"evolution_{result.evolution_id}",
                        properties=result.to_dict(),
                    )
                except Exception:
                    pass

            if self._bus:
                try:
                    self._bus.publish("system.evolution.completed", result.to_dict())
                except Exception:
                    pass

            return result
        finally:
            with self._lock:
                self._active = False

    def evolve_all(self) -> list[SystemEvolutionResult]:
        results: list[SystemEvolutionResult] = []
        for component in [
            "kernel", "scheduler", "security", "memory", "config", "audit",
        ]:
            try:
                result = self.evolve_component(component)
                results.append(result)
            except Exception as e:
                results.append(SystemEvolutionResult(
                    component=component,
                    error=str(e),
                    timestamp=time.time(),
                ))
        return results

    def get_history(self, component: str | None = None) -> list[SystemEvolutionResult]:
        return self._pipeline.get_results(component=component)

    def get_statistics(self) -> dict[str, Any]:
        scan_stats = self._scanner.get_statistics()
        pipe_stats = self._pipeline.get_statistics()
        gen_stats = self._generator.get_statistics()
        return {
            "opportunities_found": scan_stats["total_opportunities"],
            "patches_generated": gen_stats["total_patches"],
            "patches_applied": gen_stats["applied"],
            "evolution_attempts": pipe_stats["total_attempts"],
            "successful_installs": pipe_stats["successful_installs"],
            "failed": pipe_stats["failed"],
            "rolled_back": pipe_stats["rolled_back"],
            "success_rate": pipe_stats["success_rate"],
        }

    def health(self) -> dict[str, Any]:
        with self._lock:
            return {
                "alive": True,
                "active": self._active,
                "scanner": self._scanner.health(),
                "generator": self._generator.health(),
                "pipeline": self._pipeline.health(),
            }
