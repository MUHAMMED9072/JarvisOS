from __future__ import annotations

import threading
import time
from typing import Any

from app.evolution.framework.scanner import FrameworkEvolutionScanner, FrameworkImprovement
from app.evolution.framework.generator import FrameworkImprovementGenerator
from app.evolution.framework.compatibility import CompatibilityChecker
from app.evolution.framework.upgrade import RollingUpgradeManager


class FrameworkEvolutionManager:
    """Entry point for Agent Framework self-evolution.

    Coordinates scanning, patch generation, compatibility checking,
    and rolling upgrades for agent framework components.
    """

    def __init__(
        self,
        scanner: FrameworkEvolutionScanner | None = None,
        generator: FrameworkImprovementGenerator | None = None,
        compatibility: CompatibilityChecker | None = None,
        upgrade_manager: RollingUpgradeManager | None = None,
        graph_store: Any = None,
        event_bus: Any = None,
    ) -> None:
        self._scanner = scanner or FrameworkEvolutionScanner()
        self._generator = generator or FrameworkImprovementGenerator()
        self._compat = compatibility or CompatibilityChecker()
        self._upgrader = upgrade_manager or RollingUpgradeManager()
        self._graph = graph_store
        self._bus = event_bus
        self._lock = threading.RLock()

    def scan(self) -> list[FrameworkImprovement]:
        return self._scanner.scan_framework()

    def generate_patches(
        self,
        improvements: list[FrameworkImprovement] | None = None,
    ) -> list[dict[str, Any]]:
        if improvements is None:
            improvements = self.scan()
        return self._generator.generate_batch(improvements)

    def check_compatibility(self, module_name: str, patch_id: str) -> Any:
        patch = self._generator.get_patch(patch_id)
        if not patch:
            return None
        try:
            patch_path = patch.get("patch_file", "")
            with open(patch_path, encoding="utf-8") as f:
                content = f.read()
        except (OSError, TypeError):
            return None
        return self._compat.check_patch_compatibility(content, module_name)

    def rolling_upgrade(
        self,
        agent_ids: list[str],
        module_name: str,
        patch_id: str,
    ) -> Any:
        result = self._upgrader.rolling_upgrade(agent_ids, module_name, patch_id)

        if self._graph:
            try:
                self._graph.create_entity(
                    type="evolution_attempt",
                    name=f"framework_upgrade_{result.upgrade_id}",
                    properties=result.to_dict(),
                )
            except Exception:
                pass

        if self._bus:
            try:
                self._bus.publish("framework.evolution.upgrade", result.to_dict())
            except Exception:
                pass

        return result

    def get_statistics(self) -> dict[str, Any]:
        scan_stats = self._scanner.get_statistics()
        gen_stats = self._generator.get_statistics()
        upgrade_stats = self._upgrader.get_statistics()
        return {
            "improvements_found": scan_stats["total_improvements"],
            "patches_generated": gen_stats["total_patches"],
            "patches_applied": gen_stats["applied"],
            "upgrades_performed": upgrade_stats["total_upgrades"],
            "agents_upgraded": upgrade_stats["agents_upgraded"],
        }

    def health(self) -> dict[str, Any]:
        return {
            "alive": True,
            "scanner": self._scanner.health(),
            "generator": self._generator.health(),
            "compatibility": self._compat.health(),
            "upgrade_manager": self._upgrader.health(),
        }
