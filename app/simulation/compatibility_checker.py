from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class CompatibilityResult(Enum):
    COMPATIBLE = "compatible"
    INCOMPATIBLE = "incompatible"
    UNKNOWN = "unknown"


_VERSION_PATTERN = re.compile(r"^(\d+)(?:\.(\d+))?(?:\.(\d+))?(?:-([0-9A-Za-z.-]+))?(?:\+([0-9A-Za-z.-]+))?$")
_RANGE_PATTERN = re.compile(
    r"^(?:(>=|<=|>|<|==|!=)\s*)?(\d+(?:\.\d+)?(?:\.\d+)?(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?)$"
)
_CARET_TILDE = re.compile(r"^([~^])(\d+(?:\.\d+)?(?:\.\d+)?)$")


@dataclass
class VersionRange:
    version_string: str = ""
    min_version: str = ""
    max_version: str = ""
    includes_min: bool = True
    includes_max: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "version_string": self.version_string,
            "min_version": self.min_version,
            "max_version": self.max_version,
            "includes_min": self.includes_min,
            "includes_max": self.includes_max,
        }


class CompatibilityChecker:
    """Checks version compatibility between artifacts.

    Supports semver comparison, range expressions (>=1.0, <2.0, ==1.2.3),
    caret (^1.2.3) and tilde (~1.2.3) ranges, and exact version matching.

    Thread-safe.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()

    def is_compatible(self, actual_version: str, required_range: str) -> CompatibilityResult:
        """Check if `actual_version` satisfies `required_range`.

        Args:
            actual_version: Version string of the installed/found artifact.
            required_range: Version requirement (e.g. ">=1.0", "^2.3", "1.2.3").

        Returns:
            ``CompatibilityResult.COMPATIBLE``, ``INCOMPATIBLE``, or ``UNKNOWN``.
        """
        with self._lock:
            actual = self._parse_version(actual_version)
            if actual is None:
                return CompatibilityResult.UNKNOWN

            version_range = self._parse_range(required_range)
            if version_range is None:
                return CompatibilityResult.UNKNOWN

            # Handle != (not-equal) specially
            if required_range.strip().startswith("!="):
                excluded_ver = self._parse_version(required_range.strip()[2:].strip())
                if excluded_ver is not None and self._compare_versions(actual, excluded_ver) == 0:
                    return CompatibilityResult.INCOMPATIBLE
                return CompatibilityResult.COMPATIBLE

            min_ver = self._parse_version(version_range.min_version)
            max_ver = self._parse_version(version_range.max_version)

            if min_ver is not None:
                cmp_min = self._compare_versions(actual, min_ver)
                if version_range.includes_min:
                    if cmp_min < 0:
                        return CompatibilityResult.INCOMPATIBLE
                else:
                    if cmp_min <= 0:
                        return CompatibilityResult.INCOMPATIBLE

            if max_ver is not None:
                cmp_max = self._compare_versions(actual, max_ver)
                if version_range.includes_max:
                    if cmp_max > 0:
                        return CompatibilityResult.INCOMPATIBLE
                else:
                    if cmp_max >= 0:
                        return CompatibilityResult.INCOMPATIBLE

            return CompatibilityResult.COMPATIBLE

    def _parse_version(self, version: str) -> tuple[int, ...] | None:
        m = _VERSION_PATTERN.match(version.strip())
        if m is None:
            return None
        major = int(m.group(1))
        minor = int(m.group(2)) if m.group(2) else 0
        patch = int(m.group(3)) if m.group(3) else 0
        return (major, minor, patch)

    def _parse_range(self, range_str: str) -> VersionRange | None:
        range_str = range_str.strip()
        if not range_str:
            return None

        # Caret ^1.2.3
        m = _CARET_TILDE.match(range_str)
        if m:
            prefix = m.group(1)
            ver = m.group(2)
            parts = ver.split(".")
            if prefix == "^":
                major = int(parts[0])
                if len(parts) == 1:
                    return VersionRange(
                        version_string=range_str,
                        min_version=ver, max_version=f"{major + 1}.0.0",
                        includes_min=True, includes_max=False,
                    )
                return VersionRange(
                    version_string=range_str,
                    min_version=ver, max_version=f"{major + 1}.0.0",
                    includes_min=True, includes_max=False,
                )
            if prefix == "~":
                major = int(parts[0])
                if len(parts) >= 2:
                    minor = int(parts[1])
                    return VersionRange(
                        version_string=range_str,
                        min_version=ver, max_version=f"{major}.{minor + 1}.0",
                        includes_min=True, includes_max=False,
                    )
                return VersionRange(
                    version_string=range_str,
                    min_version=ver, max_version=f"{major + 1}.0.0",
                    includes_min=True, includes_max=False,
                )

        # Operator + version: >=1.0, <=2.3, >1.5, <3.0, ==1.2.3, !=1.0
        m = _RANGE_PATTERN.match(range_str)
        if m:
            op = m.group(1) or "=="
            ver = m.group(2)
            if op == ">=":
                return VersionRange(
                    version_string=range_str,
                    min_version=ver, max_version="",
                    includes_min=True, includes_max=False,
                )
            if op == "<=":
                return VersionRange(
                    version_string=range_str,
                    min_version="", max_version=ver,
                    includes_min=False, includes_max=True,
                )
            if op == ">":
                return VersionRange(
                    version_string=range_str,
                    min_version=ver, max_version="",
                    includes_min=False, includes_max=False,
                )
            if op == "<":
                return VersionRange(
                    version_string=range_str,
                    min_version="", max_version=ver,
                    includes_min=False, includes_max=False,
                )
            if op == "==":
                return VersionRange(
                    version_string=range_str,
                    min_version=ver, max_version=ver,
                    includes_min=True, includes_max=True,
                )
            if op == "!=":
                return VersionRange(
                    version_string=range_str,
                    min_version="", max_version="",
                    includes_min=False, includes_max=False,
                )

        # Bare version -> exact match
        if _VERSION_PATTERN.match(range_str):
            return VersionRange(
                version_string=range_str,
                min_version=range_str, max_version=range_str,
                includes_min=True, includes_max=True,
            )

        return None

    def _compare_versions(self, a: tuple[int, ...], b: tuple[int, ...]) -> int:
        for i in range(max(len(a), len(b))):
            av = a[i] if i < len(a) else 0
            bv = b[i] if i < len(b) else 0
            if av < bv:
                return -1
            if av > bv:
                return 1
        return 0

    def health(self) -> dict[str, Any]:
        return {"alive": True}
