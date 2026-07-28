from __future__ import annotations

import pytest

from app.simulation.compatibility_checker import (
    CompatibilityChecker,
    VersionRange,
    CompatibilityResult,
)


class TestVersionRange:
    def test_defaults(self):
        v = VersionRange()
        assert v.version_string == ""
        assert v.min_version == ""
        assert v.includes_min

    def test_to_dict(self):
        v = VersionRange(version_string=">=1.0", min_version="1.0")
        d = v.to_dict()
        assert d["version_string"] == ">=1.0"
        assert d["min_version"] == "1.0"


class TestCompatibilityChecker:
    def test_exact_match(self):
        c = CompatibilityChecker()
        assert c.is_compatible("1.2.3", "1.2.3") == CompatibilityResult.COMPATIBLE

    def test_exact_mismatch(self):
        c = CompatibilityChecker()
        assert c.is_compatible("1.2.4", "1.2.3") == CompatibilityResult.INCOMPATIBLE

    def test_greater_equal_compatible(self):
        c = CompatibilityChecker()
        assert c.is_compatible("2.0", ">=1.5") == CompatibilityResult.COMPATIBLE

    def test_greater_equal_exact(self):
        c = CompatibilityChecker()
        assert c.is_compatible("1.5", ">=1.5") == CompatibilityResult.COMPATIBLE

    def test_greater_equal_incompatible(self):
        c = CompatibilityChecker()
        assert c.is_compatible("1.0", ">=1.5") == CompatibilityResult.INCOMPATIBLE

    def test_less_equal_compatible(self):
        c = CompatibilityChecker()
        assert c.is_compatible("1.0", "<=1.5") == CompatibilityResult.COMPATIBLE

    def test_less_equal_incompatible(self):
        c = CompatibilityChecker()
        assert c.is_compatible("2.0", "<=1.5") == CompatibilityResult.INCOMPATIBLE

    def test_greater_compatible(self):
        c = CompatibilityChecker()
        assert c.is_compatible("2.0", ">1.5") == CompatibilityResult.COMPATIBLE

    def test_greater_not_equal(self):
        c = CompatibilityChecker()
        assert c.is_compatible("1.5", ">1.5") == CompatibilityResult.INCOMPATIBLE

    def test_less_compatible(self):
        c = CompatibilityChecker()
        assert c.is_compatible("1.0", "<1.5") == CompatibilityResult.COMPATIBLE

    def test_less_not_equal(self):
        c = CompatibilityChecker()
        assert c.is_compatible("1.5", "<1.5") == CompatibilityResult.INCOMPATIBLE

    def test_not_equal_compatible(self):
        c = CompatibilityChecker()
        # != means "not equal to" - everything except that specific version
        assert c.is_compatible("1.0", "!=1.5") == CompatibilityResult.COMPATIBLE

    def test_not_equal_incompatible(self):
        c = CompatibilityChecker()
        assert c.is_compatible("1.5", "!=1.5") == CompatibilityResult.INCOMPATIBLE

    def test_caret_range_minor(self):
        c = CompatibilityChecker()
        # ^1.2.3 means >=1.2.3, <2.0.0
        assert c.is_compatible("1.9.9", "^1.2.3") == CompatibilityResult.COMPATIBLE
        assert c.is_compatible("2.0.0", "^1.2.3") == CompatibilityResult.INCOMPATIBLE
        assert c.is_compatible("1.2.3", "^1.2.3") == CompatibilityResult.COMPATIBLE

    def test_tilde_range(self):
        c = CompatibilityChecker()
        # ~1.2.3 means >=1.2.3, <1.3.0
        assert c.is_compatible("1.2.9", "~1.2.3") == CompatibilityResult.COMPATIBLE
        assert c.is_compatible("1.3.0", "~1.2.3") == CompatibilityResult.INCOMPATIBLE
        assert c.is_compatible("1.2.3", "~1.2.3") == CompatibilityResult.COMPATIBLE

    def test_invalid_version_unknown(self):
        c = CompatibilityChecker()
        assert c.is_compatible("not-a-version", ">=1.0") == CompatibilityResult.UNKNOWN

    def test_empty_range_unknown(self):
        c = CompatibilityChecker()
        assert c.is_compatible("1.0", "") == CompatibilityResult.UNKNOWN

    def test_two_part_version(self):
        c = CompatibilityChecker()
        assert c.is_compatible("1.5", ">=1.0") == CompatibilityResult.COMPATIBLE
        assert c.is_compatible("0.9", ">=1.0") == CompatibilityResult.INCOMPATIBLE

    def test_one_part_version(self):
        c = CompatibilityChecker()
        assert c.is_compatible("2", ">=1") == CompatibilityResult.COMPATIBLE
        assert c.is_compatible("1", ">=2") == CompatibilityResult.INCOMPATIBLE

    def test_health(self):
        c = CompatibilityChecker()
        h = c.health()
        assert h["alive"]

    def test_thread_safe(self):
        import threading
        c = CompatibilityChecker()
        errors = []

        def check():
            try:
                for _ in range(50):
                    c.is_compatible("1.2.3", ">=1.0")
                    c.is_compatible("2.0", "^1.5")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=check) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
