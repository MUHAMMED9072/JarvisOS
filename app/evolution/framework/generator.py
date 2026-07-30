from __future__ import annotations

import threading
import time
import uuid
from pathlib import Path
from typing import Any

from app.evolution.framework.scanner import FrameworkImprovement


class FrameworkImprovementGenerator:
    """Generates patches for Agent Framework improvements.

    Converts identified framework improvements into patches
    that preserve backward compatibility.
    """

    PATCH_DIR = Path("runtime") / "evolution" / "framework_patches"

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._patches: dict[str, dict[str, Any]] = {}
        self.PATCH_DIR.mkdir(parents=True, exist_ok=True)

    def generate_patch(
        self,
        improvement: FrameworkImprovement,
        source_root: str = "app",
    ) -> dict[str, Any] | None:
        target = Path(source_root) / improvement.target_module
        if not target.is_file():
            return None

        try:
            source = target.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None

        patch_content = self._build_patch(source, improvement)
        if not patch_content:
            return None

        patch_id = uuid.uuid4().hex[:16]
        patch_path = self.PATCH_DIR / f"{patch_id}.py"

        try:
            patch_path.write_text(patch_content, encoding="utf-8")
        except OSError:
            return None

        manifest: dict[str, Any] = {
            "patch_id": patch_id,
            "target_module": improvement.target_module,
            "target_class": improvement.target_class,
            "target_method": improvement.target_method,
            "category": improvement.category,
            "description": improvement.description,
            "severity": improvement.severity,
            "patch_file": str(patch_path),
            "timestamp": time.time(),
            "applied": False,
        }

        with self._lock:
            self._patches[patch_id] = manifest

        return manifest

    def generate_batch(
        self,
        improvements: list[FrameworkImprovement],
        source_root: str = "app",
    ) -> list[dict[str, Any]]:
        return [
            p for imp in improvements
            if (p := self.generate_patch(imp, source_root)) is not None
        ]

    def get_patch(self, patch_id: str) -> dict[str, Any] | None:
        with self._lock:
            return self._patches.get(patch_id)

    def mark_applied(self, patch_id: str) -> bool:
        with self._lock:
            patch = self._patches.get(patch_id)
            if patch is None:
                return False
            patch["applied"] = True
            return True

    def _build_patch(
        self,
        source: str,
        improvement: FrameworkImprovement,
    ) -> str | None:
        lines = source.splitlines(keepends=True)
        lineno = improvement.line_number
        if lineno < 1 or lineno > len(lines):
            return None

        cat = improvement.category

        if cat == "missing_docstring":
            line = lines[lineno - 1]
            indent = " " * (len(line) - len(line.lstrip()))
            docstring = f'{indent}"""\n{indent}{improvement.description}\n{indent}"""\n'
            new_lines = list(lines)
            new_lines.insert(lineno, docstring)
            return "".join(new_lines)

        if cat == "missing_type_hints":
            new_lines = list(lines)
            line = new_lines[lineno - 1]
            if "def " in line and "->" not in line:
                new_lines[lineno - 1] = line.rstrip("\n") + " -> Any:\n"
            return "".join(new_lines)

        return None

    def get_statistics(self) -> dict[str, Any]:
        with self._lock:
            total = len(self._patches)
            applied = sum(1 for p in self._patches.values() if p["applied"])
            by_category: dict[str, int] = {}
            for p in self._patches.values():
                by_category[p["category"]] = by_category.get(p["category"], 0) + 1
        return {
            "total_patches": total,
            "applied": applied,
            "pending": total - applied,
            "by_category": by_category,
        }

    def health(self) -> dict[str, Any]:
        stats = self.get_statistics()
        return {
            "alive": True,
            "patches_generated": stats["total_patches"],
            "patches_applied": stats["applied"],
        }
