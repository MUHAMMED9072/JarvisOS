from __future__ import annotations

import threading
import time
from typing import Any

from app.evolution.ads.scanner import ADSEvolutionScanner, ADSBottleneck
from app.evolution.ads.improver import ADSStageImprover, StageImprovementResult
from app.evolution.ads.optimizer import ADSPipelineOptimizer, OptimizationPlan
from app.evolution.ads.self_improve import SelfImprovementEngine, SelfImprovementResult


class ADSEvolutionManager:
    """Entry point for ADS self-evolution.

    Coordinates scanning, stage improvement, pipeline optimization,
    and self-improvement of ADS's own capabilities.
    """

    def __init__(
        self,
        scanner: ADSEvolutionScanner | None = None,
        improver: ADSStageImprover | None = None,
        optimizer: ADSPipelineOptimizer | None = None,
        self_improve: SelfImprovementEngine | None = None,
        graph_store: Any = None,
        event_bus: Any = None,
    ) -> None:
        self._scanner = scanner or ADSEvolutionScanner()
        self._improver = improver or ADSStageImprover()
        self._optimizer = optimizer or ADSPipelineOptimizer()
        self._self_improve = self_improve or SelfImprovementEngine()
        self._graph = graph_store
        self._bus = event_bus
        self._lock = threading.RLock()

    def scan(self) -> list[ADSBottleneck]:
        return self._scanner.scan_bottlenecks()

    def record_execution(self, stage: str, duration_ms: float, success: bool) -> None:
        self._scanner.record_execution(stage, duration_ms, success)

    def improve_stage(self, stage_name: str) -> StageImprovementResult:
        bottlenecks = self._scanner.scan_bottlenecks()
        desc = f"Improve stage '{stage_name}'"
        for b in bottlenecks:
            if b.stage_name == stage_name:
                desc = b.description
                break
        result = self._improver.improve_stage(stage_name, desc)

        if self._graph:
            try:
                self._graph.create_entity(
                    type="evolution_attempt",
                    name=f"ads_improve_{result.improvement_id}",
                    properties=result.to_dict(),
                )
            except Exception:
                pass
        if self._bus:
            try:
                self._bus.publish("ads.evolution.stage_improved", result.to_dict())
            except Exception:
                pass
        return result

    def optimize_pipeline(self) -> OptimizationPlan:
        plan = self._optimizer.create_optimization_plan()
        self._optimizer.apply_plan(plan.plan_id)

        if self._graph:
            try:
                self._graph.create_entity(
                    type="evolution_attempt",
                    name=f"ads_optimize_{plan.plan_id}",
                    properties=plan.to_dict(),
                )
            except Exception:
                pass
        if self._bus:
            try:
                self._bus.publish("ads.evolution.pipeline_optimized", plan.to_dict())
            except Exception:
                pass
        return plan

    def self_improve(self, target: str = "content_generator") -> SelfImprovementResult:
        if target == "test_generator":
            result = self._self_improve.improve_test_generation()
        elif target == "architecture_designer":
            result = self._self_improve.improve_architecture_design()
        else:
            result = self._self_improve.improve_code_generation()

        if self._graph:
            try:
                self._graph.create_entity(
                    type="evolution_attempt",
                    name=f"ads_self_improve_{result.improvement_id}",
                    properties=result.to_dict(),
                )
            except Exception:
                pass
        if self._bus:
            try:
                self._bus.publish("ads.evolution.self_improved", result.to_dict())
            except Exception:
                pass
        return result

    def get_statistics(self) -> dict[str, Any]:
        scan_stats = self._scanner.get_statistics()
        imp_stats = self._improver.get_statistics()
        opt_stats = self._optimizer.get_statistics()
        si_stats = self._self_improve.get_statistics()
        return {
            "bottlenecks_found": scan_stats["bottlenecks_found"],
            "stages_improved": imp_stats["stages_improved"],
            "optimization_plans": opt_stats["total_plans"],
            "plans_applied": opt_stats["applied"],
            "self_improvements": si_stats["total_improvements"],
        }

    def health(self) -> dict[str, Any]:
        return {
            "alive": True,
            "scanner": self._scanner.health(),
            "improver": self._improver.health(),
            "optimizer": self._optimizer.health(),
            "self_improve": self._self_improve.health(),
        }
