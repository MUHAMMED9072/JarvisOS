from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class UpgradeResult:
    upgrade_id: str = ""
    target_module: str = ""
    patch_id: str = ""
    agents_upgraded: int = 0
    agents_failed: int = 0
    total_agents: int = 0
    completed: bool = False
    error: str = ""
    timestamp: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "upgrade_id": self.upgrade_id,
            "target_module": self.target_module,
            "patch_id": self.patch_id,
            "agents_upgraded": self.agents_upgraded,
            "agents_failed": self.agents_failed,
            "total_agents": self.total_agents,
            "completed": self.completed,
            "error": self.error,
            "timestamp": self.timestamp,
        }


class RollingUpgradeManager:
    """Manages gradual rolling upgrades of agents to new framework versions.

    Upgrades agents one-by-one or in small batches, monitoring
    for failures and rolling back if issues are detected.
    """

    def __init__(
        self,
        agent_upgrade_hook: Callable[[str, str], bool] | None = None,
        agent_health_hook: Callable[[str], bool] | None = None,
        batch_size: int = 1,
    ) -> None:
        self._upgrade_hook = agent_upgrade_hook
        self._health_hook = agent_health_hook
        self._batch_size = batch_size
        self._lock = threading.RLock()
        self._upgrades: dict[str, UpgradeResult] = {}

    def rolling_upgrade(
        self,
        agent_ids: list[str],
        target_module: str,
        patch_id: str,
    ) -> UpgradeResult:
        upgrade_id = uuid.uuid4().hex[:16]
        result = UpgradeResult(
            upgrade_id=upgrade_id,
            target_module=target_module,
            patch_id=patch_id,
            total_agents=len(agent_ids),
            timestamp=time.time(),
        )

        if not self._upgrade_hook:
            result.completed = True
            result.agents_upgraded = len(agent_ids)
            with self._lock:
                self._upgrades[upgrade_id] = result
            return result

        for i in range(0, len(agent_ids), self._batch_size):
            batch = agent_ids[i:i + self._batch_size]
            for agent_id in batch:
                try:
                    success = self._upgrade_hook(agent_id, patch_id)
                    if success:
                        result.agents_upgraded += 1
                        if self._health_hook:
                            healthy = self._health_hook(agent_id)
                            if not healthy:
                                result.agents_failed += 1
                                result.error = (
                                    f"Agent {agent_id} unhealthy after upgrade"
                                )
                                self._rollback_batch(batch, patch_id)
                                with self._lock:
                                    self._upgrades[upgrade_id] = result
                                return result
                    else:
                        result.agents_failed += 1
                except Exception as e:
                    result.agents_failed += 1
                    result.error = str(e)

        result.completed = result.agents_failed == 0
        with self._lock:
            self._upgrades[upgrade_id] = result
        return result

    def _rollback_batch(
        self,
        agent_ids: list[str],
        patch_id: str,
    ) -> None:
        if not self._upgrade_hook:
            return
        for agent_id in agent_ids:
            try:
                self._upgrade_hook(agent_id, f"rollback:{patch_id}")
            except Exception:
                pass

    def get_upgrade(self, upgrade_id: str) -> UpgradeResult | None:
        with self._lock:
            return self._upgrades.get(upgrade_id)

    def get_statistics(self) -> dict[str, Any]:
        with self._lock:
            total = len(self._upgrades)
            completed = sum(1 for u in self._upgrades.values() if u.completed)
            total_agents = sum(u.total_agents for u in self._upgrades.values())
            upgraded = sum(u.agents_upgraded for u in self._upgrades.values())
        return {
            "total_upgrades": total,
            "completed": completed,
            "total_agents": total_agents,
            "agents_upgraded": upgraded,
        }

    def health(self) -> dict[str, Any]:
        stats = self.get_statistics()
        return {
            "alive": True,
            "total_upgrades": stats["total_upgrades"],
            "agents_upgraded": stats["agents_upgraded"],
        }
