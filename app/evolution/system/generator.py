from __future__ import annotations

import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from app.evolution.system.scanner import ImprovementOpportunity


class SystemImprovementGenerator:
    """Produces patches for system-level improvement opportunities.

    Converts identified improvement opportunities into actionable patches
    that can be reviewed, sandboxed, and installed.
    """

    PATCH_DIR = Path("runtime") / "evolution" / "patches"

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._generated_patches: dict[str, dict[str, Any]] = {}
        self.PATCH_DIR.mkdir(parents=True, exist_ok=True)

    def generate_patch(
        self,
        opportunity: ImprovementOpportunity,
        source_root: str = "app",
    ) -> dict[str, Any] | None:
        if not opportunity.target_file:
            return None

        patch_id = uuid.uuid4().hex[:16]
        timestamp = time.time()

        patch_content = self._build_patch(opportunity, source_root)
        if not patch_content:
            return None

        patch_path = self.PATCH_DIR / f"{patch_id}.py"
        try:
            patch_path.write_text(patch_content, encoding="utf-8")
        except OSError:
            return None

        manifest: dict[str, Any] = {
            "patch_id": patch_id,
            "target_file": opportunity.target_file,
            "component": opportunity.component,
            "category": opportunity.category,
            "description": opportunity.description,
            "severity": opportunity.severity,
            "line_number": opportunity.line_number,
            "patch_file": str(patch_path),
            "timestamp": timestamp,
            "applied": False,
        }

        with self._lock:
            self._generated_patches[patch_id] = manifest

        return manifest

    def generate_batch(
        self,
        opportunities: list[ImprovementOpportunity],
        source_root: str = "app",
    ) -> list[dict[str, Any]]:
        patches: list[dict[str, Any]] = []
        for opp in opportunities:
            patch = self.generate_patch(opp, source_root)
            if patch:
                patches.append(patch)
        return patches

    def get_patch(self, patch_id: str) -> dict[str, Any] | None:
        with self._lock:
            return self._generated_patches.get(patch_id)

    def get_patches_by_component(self, component: str) -> list[dict[str, Any]]:
        with self._lock:
            return [
                p for p in self._generated_patches.values()
                if p["component"] == component
            ]

    def mark_applied(self, patch_id: str) -> bool:
        with self._lock:
            patch = self._generated_patches.get(patch_id)
            if patch is None:
                return False
            patch["applied"] = True
            return True

    def _build_patch(
        self,
        opportunity: ImprovementOpportunity,
        source_root: str,
    ) -> str | None:
        target = Path(source_root) / opportunity.target_file
        if not target.is_file():
            return None

        try:
            source = target.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None

        lines = source.splitlines(keepends=True)
        lineno = opportunity.line_number
        if lineno < 1 or lineno > len(lines):
            return None

        category = opportunity.category
        if category == "missing_docstring":
            return self._build_docstring_patch(lines, lineno, opportunity)
        elif category == "missing_type_hints":
            return self._build_type_hint_patch(lines, lineno, opportunity)
        elif category == "bare_except":
            return self._build_bare_except_patch(lines, lineno, opportunity)
        return None

    def _build_docstring_patch(
        self,
        lines: list[str],
        lineno: int,
        opportunity: ImprovementOpportunity,
    ) -> str:
        line = lines[lineno - 1] if lineno <= len(lines) else ""
        indent = " " * (len(line) - len(line.lstrip()))
        docstring = f'{indent}"""\n{indent}{opportunity.description}\n{indent}"""\n'
        new_lines = list(lines)
        new_lines.insert(lineno, docstring)
        return "".join(new_lines)

    def _build_type_hint_patch(
        self,
        lines: list[str],
        lineno: int,
        opportunity: ImprovementOpportunity,
    ) -> str:
        line = lines[lineno - 1] if lineno <= len(lines) else ""
        hinted = line.replace("def ", "def ") if "def " in line else line
        if hinted == line and ":" not in line.split("def ")[-1][:2] if "def " in line else True:
            hinted = hinted.rstrip("\n") + " -> Any:\n"
        new_lines = list(lines)
        new_lines[lineno - 1] = hinted
        return "".join(new_lines)

    def _build_bare_except_patch(
        self,
        lines: list[str],
        lineno: int,
        opportunity: ImprovementOpportunity,
    ) -> str:
        new_lines = list(lines)
        if lineno <= len(new_lines):
            new_lines[lineno - 1] = new_lines[lineno - 1].replace(
                "except:", "except Exception:"
            )
        return "".join(new_lines)

    def get_statistics(self) -> dict[str, Any]:
        with self._lock:
            total = len(self._generated_patches)
            applied = sum(1 for p in self._generated_patches.values() if p["applied"])
            by_component: dict[str, int] = {}
            for p in self._generated_patches.values():
                comp = p["component"]
                by_component[comp] = by_component.get(comp, 0) + 1
        return {
            "total_patches": total,
            "applied": applied,
            "pending": total - applied,
            "by_component": by_component,
        }

    def health(self) -> dict[str, Any]:
        stats = self.get_statistics()
        return {
            "alive": True,
            "patches_generated": stats["total_patches"],
            "patches_applied": stats["applied"],
            "patch_dir": str(self.PATCH_DIR),
        }
