from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CompatibilityResult:
    compatible: bool = True
    breaking_changes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    api_changes: list[str] = field(default_factory=list)
    required_migration: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "compatible": self.compatible,
            "breaking_changes": list(self.breaking_changes),
            "warnings": list(self.warnings),
            "api_changes": list(self.api_changes),
            "required_migration": self.required_migration,
        }


class CompatibilityChecker:
    """Checks backward compatibility of framework changes.

    Validates that evolved agent framework components
    remain compatible with existing agent implementations.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()

    def check_patch_compatibility(
        self,
        patch_content: str,
        module_name: str,
        original_content: str | None = None,
    ) -> CompatibilityResult:
        result = CompatibilityResult()
        new_lines = patch_content.splitlines()

        removed_defs = self._find_removed_definitions(new_lines)
        if removed_defs:
            result.compatible = False
            for d in removed_defs:
                result.breaking_changes.append(f"Removed definition: {d}")

        if original_content is not None:
            added_required_params = self._find_added_required_params(
                original_content.splitlines(), new_lines,
            )
            if added_required_params:
                result.compatible = False
                for p in added_required_params:
                    result.breaking_changes.append(f"Added required parameter: {p}")
            old_lines = original_content.splitlines()
            changed = self._compare_signatures(old_lines, new_lines)
            if changed:
                result.compatible = False
                result.breaking_changes.extend(changed)

        if not result.compatible:
            result.required_migration = (
                f"Patch to {module_name} introduces breaking changes. "
                "Existing agents may need updates to remain compatible."
            )

        return result

    def check_interface_compatibility(
        self,
        old_interface: dict[str, list[str]],
        new_interface: dict[str, list[str]],
    ) -> CompatibilityResult:
        result = CompatibilityResult()

        for class_name, methods in old_interface.items():
            new_methods = new_interface.get(class_name, [])
            removed = [m for m in methods if m not in new_methods]
            if removed:
                result.compatible = False
                result.breaking_changes.append(
                    f"Class '{class_name}' lost methods: {', '.join(removed)}"
                )

        for class_name, methods in new_interface.items():
            if class_name not in old_interface:
                continue
            old_methods = old_interface.get(class_name, [])

            def _is_required_param_sig(m: str) -> bool:
                if "(" not in m:
                    return False
                params = m.split("(")[1].split(")")[0]
                required = [
                    p.strip().split(":")[0].strip()
                    for p in params.split(",")
                    if p.strip() and "=" not in p
                    and p.strip() != "self"
                ]
                return bool(required)

            for m in methods:
                stripped = m.split("(")[0].strip()
                matching_old = [
                    o for o in old_methods
                    if o.split("(")[0].strip() == stripped
                ]
                if not matching_old:
                    continue
                new_has_required = _is_required_param_sig(m)
                old_has_required = _is_required_param_sig(matching_old[0])
                if new_has_required and not old_has_required:
                    result.breaking_changes.append(
                        f"Method '{stripped}' in '{class_name}' added required params"
                    )

        return result

    def _find_removed_definitions(self, lines: list[str]) -> list[str]:
        removed: list[str] = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith('"'):
                continue
            if "def " in stripped and stripped.startswith("-"):
                name = stripped.split("def ")[1].split("(")[0].strip()
                removed.append(name)
        return removed

    def _compare_signatures(
        self,
        old_lines: list[str],
        new_lines: list[str],
    ) -> list[str]:
        old_sigs = self._extract_signatures(old_lines)
        new_sigs = self._extract_signatures(new_lines)
        breaking: list[str] = []
        for name, sig in old_sigs.items():
            if name not in new_sigs:
                breaking.append(f"Removed function/class: {name}")
        return breaking

    def _extract_signatures(self, lines: list[str]) -> dict[str, str]:
        sigs: dict[str, str] = {}
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("class ") and ":" in stripped:
                name = stripped.split("class ")[1].split("(")[0].split(":")[0].strip()
                if name and not name.startswith("_"):
                    sigs[name] = stripped
            elif stripped.startswith("def ") and stripped.endswith(":"):
                name = stripped.split("def ")[1].split("(")[0].strip()
                if name and not name.startswith("_"):
                    sigs[name] = stripped
        return sigs

    def _find_added_required_params(
        self,
        old_lines: list[str],
        new_lines: list[str],
    ) -> list[str]:
        old_sigs = self._extract_required_params(old_lines)
        new_sigs = self._extract_required_params(new_lines)
        added: list[str] = []
        for func_name, params in new_sigs.items():
            if func_name in old_sigs:
                old_params = set(old_sigs[func_name])
                for p in params:
                    if p not in old_params:
                        added.append(f"{func_name}: {p}")
        return added

    def _extract_required_params(self, lines: list[str]) -> dict[str, list[str]]:
        result: dict[str, list[str]] = {}
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("def ") and "(" in stripped and ")" in stripped:
                name = stripped.split("def ")[1].split("(")[0].strip()
                params_str = stripped.split("(")[1].split(")")[0]
                params = []
                for p in params_str.split(","):
                    p = p.strip()
                    if p and p != "self" and "=" not in p and ":" in p:
                        params.append(p.split(":")[0].strip())
                if params:
                    result[name] = params
        return result

    def health(self) -> dict[str, Any]:
        return {"alive": True}
