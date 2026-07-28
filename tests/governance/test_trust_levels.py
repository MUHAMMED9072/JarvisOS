from __future__ import annotations

import pytest

from app.governance.trust_levels import TrustLevel, trust_level_rank, is_trust_level_at_least


class TestTrustLevel:
    def test_enum_values(self):
        assert TrustLevel.CRITICAL.value == "critical"
        assert TrustLevel.HIGH.value == "high"
        assert TrustLevel.MEDIUM.value == "medium"
        assert TrustLevel.LOW.value == "low"
        assert TrustLevel.UNTRUSTED.value == "untrusted"
        assert TrustLevel.SANDBOXED.value == "sandboxed"

    def test_trust_level_rank_ordering(self):
        assert trust_level_rank(TrustLevel.CRITICAL) > trust_level_rank(TrustLevel.HIGH)
        assert trust_level_rank(TrustLevel.HIGH) > trust_level_rank(TrustLevel.MEDIUM)
        assert trust_level_rank(TrustLevel.MEDIUM) > trust_level_rank(TrustLevel.LOW)
        assert trust_level_rank(TrustLevel.LOW) > trust_level_rank(TrustLevel.UNTRUSTED)
        assert trust_level_rank(TrustLevel.UNTRUSTED) > trust_level_rank(TrustLevel.SANDBOXED)

    def test_trust_level_rank_unknown(self):
        assert trust_level_rank(None) == 0

    def test_is_trust_level_at_least_same(self):
        assert is_trust_level_at_least(TrustLevel.HIGH, TrustLevel.HIGH)

    def test_is_trust_level_at_least_higher(self):
        assert is_trust_level_at_least(TrustLevel.CRITICAL, TrustLevel.HIGH)

    def test_is_trust_level_at_least_lower(self):
        assert not is_trust_level_at_least(TrustLevel.LOW, TrustLevel.HIGH)

    def test_is_trust_level_at_least_sandboxed(self):
        assert is_trust_level_at_least(TrustLevel.SANDBOXED, TrustLevel.SANDBOXED)
        assert not is_trust_level_at_least(TrustLevel.SANDBOXED, TrustLevel.UNTRUSTED)
