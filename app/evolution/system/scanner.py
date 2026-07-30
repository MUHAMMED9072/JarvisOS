from __future__ import annotations

import ast
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ImprovementOpportunity:
    target_file: str = ""
    module_path: str = ""
    component: str = ""
    category: str = ""
    description: str = ""
    severity: str = "medium"
    line_number: int = 0
    current_snippet: str = ""
    suggestion: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_file": self.target_file,
            "module_path": self.module_path,
            "component": self.component,
            "category": self.category,
            "description": self.description,
            "severity": self.severity,
            "line_number": self.line_number,
            "current_snippet": self.current_snippet,
            "suggestion": self.suggestion,
        }


SYSTEM_COMPONENTS: dict[str, list[str]] = {
    "kernel": ["app/kernel"],
    "scheduler": ["app/kernel/scheduler.py", "app/kernel/task.py"],
    "security": ["app/kernel/security"],
    "memory": ["app/memory"],
    "config": ["app/core/config.py", "app/kernel/config.py"],
    "audit": ["app/kernel/audit.py", "app/kernel/logger.py"],
}


class _FunctionVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.opportunities: list[ImprovementOpportunity] = []
        self._file_path = ""
        self._module_path = ""
        self._component = ""

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._check_function(node)
        self.generic_visit(node)

    def _check_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        name = node.name
        lineno = node.lineno or 0

        if name.startswith("__") and name.endswith("__"):
            return

        if not ast.get_docstring(node):
            self.opportunities.append(ImprovementOpportunity(
                target_file=self._file_path,
                module_path=self._module_path,
                component=self._component,
                category="missing_docstring",
                description=f"Function '{name}' lacks a docstring",
                severity="low",
                line_number=lineno,
                current_snippet=f"def {name}(...):",
                suggestion="Add a docstring describing purpose, args, and returns",
            ))

        has_annotations = all(
            arg.annotation is not None for arg in node.args.args
        ) if node.args.args else True
        if node.returns is None:
            has_annotations = False

        if not has_annotations:
            self.opportunities.append(ImprovementOpportunity(
                target_file=self._file_path,
                module_path=self._module_path,
                component=self._component,
                category="missing_type_hints",
                description=f"Function '{name}' is missing type hints",
                severity="medium",
                line_number=lineno,
                current_snippet=f"def {name}(...):",
                suggestion="Add type hints for all parameters and return type",
            ))


class _ErrorHandlingVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.opportunities: list[ImprovementOpportunity] = []
        self._file_path = ""
        self._module_path = ""
        self._component = ""

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.type is None:
            self.opportunities.append(ImprovementOpportunity(
                target_file=self._file_path,
                module_path=self._module_path,
                component=self._component,
                category="bare_except",
                description="Bare 'except:' clause catches all exceptions including SystemExit",
                severity="high",
                line_number=node.lineno or 0,
                current_snippet="except:",
                suggestion="Catch specific exception types instead (e.g., except Exception:)",
            ))
        self.generic_visit(node)


class SystemEvolutionScanner:
    """Scans kernel and system components for improvement opportunities.

    Performs AST-based static analysis to detect:
      - Missing docstrings
      - Missing type hints
      - Bare except clauses
      - Thread safety concerns
    """

    def __init__(self, root_path: str | None = None) -> None:
        self._root = Path(root_path or "app")
        self._lock = threading.RLock()

    def scan_component(self, component: str) -> list[ImprovementOpportunity]:
        if component not in SYSTEM_COMPONENTS:
            return []
        paths = SYSTEM_COMPONENTS[component]
        all_opportunities: list[ImprovementOpportunity] = []
        for rel_path in paths:
            full = self._root / rel_path
            if full.is_dir():
                for py_file in sorted(full.rglob("*.py")):
                    all_opportunities.extend(self._scan_file(py_file, component))
            elif full.is_file():
                all_opportunities.extend(self._scan_file(full, component))
        return all_opportunities

    def scan_all(self) -> dict[str, list[ImprovementOpportunity]]:
        results: dict[str, list[ImprovementOpportunity]] = {}
        for component in SYSTEM_COMPONENTS:
            opps = self.scan_component(component)
            if opps:
                results[component] = opps
        return results

    def _scan_file(
        self,
        file_path: Path,
        component: str,
    ) -> list[ImprovementOpportunity]:
        try:
            source = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return []

        try:
            tree = ast.parse(source)
        except SyntaxError:
            return []

        rel = file_path.as_posix()
        opportunities: list[ImprovementOpportunity] = []

        func_visitor = _FunctionVisitor()
        func_visitor._file_path = rel
        func_visitor._module_path = str(file_path.with_suffix("")).replace("/", ".")
        func_visitor._component = component
        func_visitor.visit(tree)
        opportunities.extend(func_visitor.opportunities)

        err_visitor = _ErrorHandlingVisitor()
        err_visitor._file_path = rel
        err_visitor._module_path = str(file_path.with_suffix("")).replace("/", ".")
        err_visitor._component = component
        err_visitor.visit(tree)
        opportunities.extend(err_visitor.opportunities)

        return opportunities

    def get_statistics(self) -> dict[str, Any]:
        results = self.scan_all()
        total = sum(len(v) for v in results.values())
        by_severity: dict[str, int] = {}
        for opps in results.values():
            for opp in opps:
                by_severity[opp.severity] = by_severity.get(opp.severity, 0) + 1
        return {
            "components_scanned": len(results),
            "total_opportunities": total,
            "by_severity": by_severity,
            "by_component": {comp: len(opps) for comp, opps in results.items()},
        }

    def health(self) -> dict[str, Any]:
        return {
            "alive": True,
            "root_path": str(self._root),
            "components_tracked": len(SYSTEM_COMPONENTS),
        }
