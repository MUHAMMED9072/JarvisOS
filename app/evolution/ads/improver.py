from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


@dataclass
class StageImprovementResult:
    improvement_id: str = ""
    stage_name: str = ""
    patch_content: str = ""
    applied: bool = False
    verified: bool = False
    error: str = ""
    timestamp: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "improvement_id": self.improvement_id,
            "stage_name": self.stage_name,
            "applied": self.applied,
            "verified": self.verified,
            "error": self.error,
            "timestamp": self.timestamp,
        }


class ADSStageImprover:
    """Improves individual ADS pipeline stages.

    Generates patches for specific stages based on
    identified bottlenecks and optimization targets.
    """

    IMPROVEMENT_DIR = Path("runtime") / "evolution" / "ads_improvements"

    def __init__(
        self,
        verify_hook: Callable[[str], bool] | None = None,
    ) -> None:
        self._verify = verify_hook
        self._lock = threading.RLock()
        self._results: dict[str, StageImprovementResult] = {}
        self.IMPROVEMENT_DIR.mkdir(parents=True, exist_ok=True)

    def improve_stage(
        self,
        stage_name: str,
        description: str,
    ) -> StageImprovementResult:
        improvement_id = uuid.uuid4().hex[:16]
        result = StageImprovementResult(
            improvement_id=improvement_id,
            stage_name=stage_name,
            timestamp=time.time(),
        )

        patch = self._generate_stage_patch(stage_name, description)
        if not patch:
            result.error = f"Could not generate improvement for stage '{stage_name}'"
            with self._lock:
                self._results[improvement_id] = result
            return result

        result.patch_content = patch

        patch_path = self.IMPROVEMENT_DIR / f"{improvement_id}.py"
        try:
            patch_path.write_text(patch, encoding="utf-8")
        except OSError as e:
            result.error = str(e)
            with self._lock:
                self._results[improvement_id] = result
            return result

        result.applied = True

        if self._verify:
            result.verified = self._verify(improvement_id)

        with self._lock:
            self._results[improvement_id] = result
        return result

    def _generate_stage_patch(
        self,
        stage_name: str,
        description: str,
    ) -> str | None:
        patches = {
            "governance_check": self._patch_governance,
            "sandbox_execution": self._patch_sandbox,
            "test_generation": self._patch_test_gen,
        }
        builder = patches.get(stage_name)
        if builder:
            return builder(description)
        return self._patch_generic(stage_name, description)

    def _patch_governance(self, description: str) -> str:
        return (
            f"# Improvement for governance_check\n"
            f"# {description}\n"
            f"ADDITIONAL_POLICIES = {{\n"
            f'    "evolution_safety": {{\n'
            f'        "condition": "category == evolution",\n'
            f'        "action": "REQUIRE_APPROVAL",\n'
            f'        "priority": 100,\n'
            f"    }}\n"
            f"}}\n"
        )

    def _patch_sandbox(self, description: str) -> str:
        return (
            f"# Improvement for sandbox_execution\n"
            f"# {description}\n"
            f"ADDITIONAL_BLOCKED_MODULES = [\n"
            f'    "ctypes",\n'
            f'    "socket",\n'
            f'    "multiprocessing",\n'
            f"]\n"
            f"TIMEOUT_SECONDS = 60\n"
        )

    def _patch_test_gen(self, description: str) -> str:
        return (
            f"# Improvement for test_generation\n"
            f"# {description}\n"
            f"COVERAGE_THRESHOLD = 0.85\n"
            f"INCLUDE_EDGE_CASES = True\n"
            f"MAX_TEST_METHODS = 20\n"
        )

    def _patch_generic(self, stage_name: str, description: str) -> str:
        return (
            f"# Improvement for {stage_name}\n"
            f"# {description}\n"
            f"STAGE_CONFIG = {{\n"
            f'    "name": "{stage_name}",\n'
            f'    "optimization": description,\n'
            f'    "enabled": True,\n'
            f"}}\n"
        )

    def get_result(self, improvement_id: str) -> StageImprovementResult | None:
        with self._lock:
            return self._results.get(improvement_id)

    def get_statistics(self) -> dict[str, Any]:
        with self._lock:
            total = len(self._results)
            applied = sum(1 for r in self._results.values() if r.applied)
            verified = sum(1 for r in self._results.values() if r.verified)
        return {
            "total_improvements": total,
            "applied": applied,
            "verified": verified,
            "stages_improved": len(set(r.stage_name for r in self._results.values())),
        }

    def health(self) -> dict[str, Any]:
        return {"alive": True}
