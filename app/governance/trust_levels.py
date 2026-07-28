from __future__ import annotations

from enum import Enum


class TrustLevel(Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNTRUSTED = "untrusted"
    SANDBOXED = "sandboxed"


TRUST_LEVEL_RANK: dict[TrustLevel, int] = {
    TrustLevel.CRITICAL: 6,
    TrustLevel.HIGH: 5,
    TrustLevel.MEDIUM: 4,
    TrustLevel.LOW: 3,
    TrustLevel.UNTRUSTED: 2,
    TrustLevel.SANDBOXED: 1,
}


def trust_level_rank(level: TrustLevel) -> int:
    return TRUST_LEVEL_RANK.get(level, 0)


def is_trust_level_at_least(actual: TrustLevel, minimum: TrustLevel) -> bool:
    return trust_level_rank(actual) >= trust_level_rank(minimum)
