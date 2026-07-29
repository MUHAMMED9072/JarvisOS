from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any

from app.tools.base import Tool
from app.tools.registry import ToolRegistry


@dataclass
class DependencyValidationResult:
    valid: bool = True
    missing_dependencies: list[str] = field(default_factory=list)
    version_mismatches: list[dict[str, Any]] = field(default_factory=list)
    circular_dependencies: list[list[str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "missing_dependencies": list(self.missing_dependencies),
            "version_mismatches": list(self.version_mismatches),
            "circular_dependencies": [[str(s) for s in c] for c in self.circular_dependencies],
            "warnings": list(self.warnings),
        }


class ToolDependencyValidator:
    """Validates tool dependencies, detects cycles, and checks versions.

    Works with tools that declare dependencies via their metadata.tags
    or via explicit dependency declarations in tool metadata.
    """

    def __init__(self, registry: ToolRegistry | None = None) -> None:
        self._registry = registry
        self._lock = threading.RLock()

    def validate_tool(self, tool: Tool) -> DependencyValidationResult:
        deps = self._extract_dependencies(tool)
        if not deps:
            return DependencyValidationResult(valid=True)

        result = DependencyValidationResult()

        if self._registry:
            for dep_name, dep_version in deps:
                meta = self._registry.get(dep_name)
                if meta is None:
                    result.missing_dependencies.append(dep_name)
                elif dep_version and meta.version != dep_version:
                    result.version_mismatches.append({
                        "tool": dep_name,
                        "required": dep_version,
                        "found": meta.version,
                    })

        dep_names = [d[0] for d in deps]
        cycles = self._detect_cycles(tool.name, dep_names)
        result.circular_dependencies = cycles

        if result.missing_dependencies or result.version_mismatches or cycles:
            result.valid = False

        return result

    def _extract_dependencies(self, tool: Tool) -> list[tuple[str, str]]:
        deps: list[tuple[str, str]] = []
        for tag in tool.metadata.tags:
            if tag.startswith("dep:"):
                parts = tag[4:].split("==")
                if len(parts) == 2:
                    deps.append((parts[0], parts[1]))
                else:
                    deps.append((parts[0], ""))
        return deps

    def _detect_cycles(
        self,
        tool_name: str,
        dep_names: list[str],
        visited: set[str] | None = None,
        path: list[str] | None = None,
    ) -> list[list[str]]:
        if visited is None:
            visited = set()
        if path is None:
            path = []

        cycles: list[list[str]] = []
        current_visited = set(visited)
        current_path = list(path)

        current_visited.add(tool_name)
        current_path.append(tool_name)

        for dep_name in dep_names:
            if dep_name == tool_name:
                cycles.append([tool_name, tool_name])
                continue
            if dep_name in current_visited:
                cycle_start = current_path.index(dep_name)
                cycles.append(current_path[cycle_start:] + [dep_name])
                continue
            if self._registry:
                sub_meta = self._registry.get(dep_name)
                if sub_meta:
                    sub_deps = [
                        t for t in sub_meta.tags if t.startswith("dep:")
                    ]
                    sub_dep_names = [t[4:].split("==")[0] for t in sub_deps]
                    sub_cycles = self._detect_cycles(
                        dep_name, sub_dep_names,
                        current_visited, current_path,
                    )
                    cycles.extend(sub_cycles)

        return cycles

    def health(self) -> dict[str, Any]:
        return {"alive": True}
