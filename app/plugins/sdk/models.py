from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class PluginDependency:
    name: str
    version: str = "*"


@dataclass
class PluginManifest:
    name: str
    version: str
    description: str = ""
    author: str = ""
    min_core_version: str = "0.4.0"
    dependencies: list[PluginDependency] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)
    config_schema: dict[str, Any] | None = None


_SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-([a-zA-Z0-9.-]+))?"
    r"(?:\+([a-zA-Z0-9.-]+))?$"
)


def _parse_semver(version: str) -> tuple[int, int, int, str, str]:
    m = _SEMVER_RE.match(version)
    if not m:
        raise ValueError(f"Invalid semver: {version!r}")
    return (
        int(m.group(1)), int(m.group(2)), int(m.group(3)),
        m.group(4) or "", m.group(5) or "",
    )


def check_version_compatibility(
    plugin_version: str, core_version: str,
) -> bool:
    try:
        p_major, p_minor, p_patch, *_ = _parse_semver(plugin_version)
        c_major, c_minor, c_patch, *_ = _parse_semver(core_version)
    except ValueError:
        return False
    if p_major != c_major:
        return False
    if p_minor > c_minor:
        return False
    if p_minor == c_minor and p_patch > c_patch:
        return False
    return True


def validate_manifest(manifest: PluginManifest) -> list[str]:
    errors: list[str] = []
    if not manifest.name or not isinstance(manifest.name, str):
        errors.append("manifest.name must be a non-empty string")
    if not manifest.version or not isinstance(manifest.version, str):
        errors.append("manifest.version must be a non-empty string")
    else:
        try:
            _parse_semver(manifest.version)
        except ValueError:
            errors.append(
                f"manifest.version {manifest.version!r} is not valid semver"
            )
    if manifest.min_core_version:
        try:
            _parse_semver(manifest.min_core_version)
        except ValueError:
            errors.append(
                f"manifest.min_core_version {manifest.min_core_version!r} "
                f"is not valid semver"
            )
    if not manifest.dependencies:
        return errors
    for i, dep in enumerate(manifest.dependencies):
        if not dep.name or not isinstance(dep.name, str):
            errors.append(f"manifest.dependencies[{i}].name must be a non-empty string")
    return errors
