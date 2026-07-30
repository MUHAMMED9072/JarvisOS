from __future__ import annotations

import ast
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class FrameworkImprovement:
    target_module: str = ""
    target_class: str = ""
    target_method: str = ""
    category: str = ""
    description: str = ""
    severity: str = "medium"
    line_number: int = 0
    current_snippet: str = ""
    suggestion: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_module": self.target_module,
            "target_class": self.target_class,
            "target_method": self.target_method,
            "category": self.category,
            "description": self.description,
            "severity": self.severity,
            "line_number": self.line_number,
            "current_snippet": self.current_snippet,
            "suggestion": self.suggestion,
        }


FRAMEWORK_MODULES: list[str] = [
    "app/agents/base.py",
    "app/agents/types.py",
    "app/agents/factory.py",
    "app/agents/lifecycle.py",
    "app/agents/state_machine.py",
    "app/agents/registry.py",
    "app/agents/memory.py",
    "app/agents/communication/bus.py",
    "app/agents/communication/message.py",
    "app/agents/communication/router.py",
    "app/agents/communication/patterns.py",
    "app/agents/metrics.py",
    "app/agents/health.py",
    "app/agents/versioning.py",
]


class _ClassMethodVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.improvements: list[FrameworkImprovement] = []
        self._current_class = ""
        self._module_path = ""

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        old_class = self._current_class
        self._current_class = node.name
        self.generic_visit(node)
        self._current_class = old_class

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._check_method(node)
        self.generic_visit(node)

    def _check_method(self, node: ast.FunctionDef) -> None:
        name = node.name
        lineno = node.lineno or 0

        if not ast.get_docstring(node):
            self.improvements.append(FrameworkImprovement(
                target_module=self._module_path,
                target_class=self._current_class,
                target_method=name,
                category="missing_docstring",
                description=f"Method '{name}' in '{self._current_class}' lacks docstring",
                severity="low",
                line_number=lineno,
                current_snippet=f"def {name}(...):",
                suggestion="Add docstring describing purpose and args",
            ))

        has_return_hint = node.returns is not None
        has_arg_hints = all(
            arg.annotation is not None for arg in node.args.args
        ) if node.args.args else True

        if not has_return_hint or not has_arg_hints:
            self.improvements.append(FrameworkImprovement(
                target_module=self._module_path,
                target_class=self._current_class,
                target_method=name,
                category="missing_type_hints",
                description=f"Method '{name}' in '{self._current_class}' missing type hints",
                severity="medium",
                line_number=lineno,
                current_snippet=f"def {name}(...):",
                suggestion="Add type hints for all parameters and return",
            ))


class FrameworkEvolutionScanner:
    """Scans the Agent Framework for improvement opportunities.

    Analyzes agent base classes, lifecycle, registry, memory,
    communication, metrics, health, and versioning modules.
    """

    def __init__(self, root_path: str | None = None) -> None:
        self._root = Path(root_path or "app")
        self._lock = threading.RLock()

    def scan_framework(self) -> list[FrameworkImprovement]:
        all_improvements: list[FrameworkImprovement] = []
        for rel_path in FRAMEWORK_MODULES:
            full = self._root / rel_path
            if full.is_file():
                all_improvements.extend(self._scan_file(full))
        return all_improvements

    def scan_module(self, module_name: str) -> list[FrameworkImprovement]:
        candidates = [
            p for p in FRAMEWORK_MODULES
            if module_name in p.replace("/", ".")
        ]
        results: list[FrameworkImprovement] = []
        for rel_path in candidates:
            full = self._root / rel_path
            if full.is_file():
                results.extend(self._scan_file(full))
        return results

    def _scan_file(self, file_path: Path) -> list[FrameworkImprovement]:
        try:
            source = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return []
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return []

        rel = file_path.as_posix()
        visitor = _ClassMethodVisitor()
        visitor._module_path = str(file_path.with_suffix("")).replace("/", ".")
        visitor.visit(tree)
        for imp in visitor.improvements:
            imp.target_module = rel
        return visitor.improvements

    def get_statistics(self) -> dict[str, Any]:
        improvements = self.scan_framework()
        total = len(improvements)
        by_severity: dict[str, int] = {}
        by_category: dict[str, int] = {}
        for imp in improvements:
            by_severity[imp.severity] = by_severity.get(imp.severity, 0) + 1
            by_category[imp.category] = by_category.get(imp.category, 0) + 1
        modules_affected = len(set(imp.target_module for imp in improvements))
        return {
            "total_improvements": total,
            "by_severity": by_severity,
            "by_category": by_category,
            "modules_affected": modules_affected,
        }

    def health(self) -> dict[str, Any]:
        return {
            "alive": True,
            "modules_tracked": len(FRAMEWORK_MODULES),
            "root_path": str(self._root),
        }
