from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.ads.benchmark import BenchmarkReport
from app.ads.performance_review import PerformanceReport
from app.ads.security_review import SecurityReport
from app.governance.trust_levels import TrustLevel, is_trust_level_at_least


@dataclass
class GovernanceResult:
    """Result of governance evaluation for an artifact."""

    artifact_name: str = ""
    trust_level: str = "low"
    risk_score: float = 0.0
    security_passed: bool = True
    performance_passed: bool = True
    benchmark_passed: bool = True
    policy_violations: list[str] = field(default_factory=list)
    passed: bool = False
    approval_mode: str = "manual"

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_name": self.artifact_name,
            "trust_level": self.trust_level,
            "risk_score": self.risk_score,
            "security_passed": self.security_passed,
            "performance_passed": self.performance_passed,
            "benchmark_passed": self.benchmark_passed,
            "policy_violations": list(self.policy_violations),
            "passed": self.passed,
            "approval_mode": self.approval_mode,
        }


class GovernanceChecker:
    """Evaluate all relevant policies against an artifact and its reports."""

    def check(
        self,
        artifact_name: str,
        trust_level: str = "low",
        security_report: SecurityReport | None = None,
        performance_report: PerformanceReport | None = None,
        benchmark_report: BenchmarkReport | None = None,
    ) -> GovernanceResult:
        violations: list[str] = []
        risk_score = 0.0

        # Trust level assessment
        level = TrustLevel(trust_level) if trust_level in [t.value for t in TrustLevel] else TrustLevel.LOW

        # Security evaluation
        security_passed = True
        if security_report:
            security_passed = security_report.passed
            if not security_passed:
                violations.append(f"Security: {security_report.high_count} high severity issues")
                risk_score += security_report.high_count * 30
                risk_score += security_report.medium_count * 10

        # Performance evaluation
        performance_passed = True
        if performance_report:
            performance_passed = performance_report.passed
            if not performance_passed:
                violations.append(f"Performance: resource score {performance_report.resource_score}")
                risk_score += 10

        # Benchmark evaluation
        benchmark_passed = True
        if benchmark_report:
            benchmark_passed = benchmark_report.passed
            if not benchmark_passed:
                violations.append("Benchmark: below baseline")
                risk_score += 15

        # Policy checks
        if not is_trust_level_at_least(level, TrustLevel.LOW):
            violations.append(f"Trust level '{trust_level}' too low")
            risk_score += 50

        # Final assessment
        if risk_score > 70:
            approval_mode = "rejected"
            passed = False
        elif risk_score > 30:
            approval_mode = "manual"
            passed = True  # manual approval required
        else:
            approval_mode = "auto-approve"
            passed = True

        return GovernanceResult(
            artifact_name=artifact_name,
            trust_level=trust_level,
            risk_score=risk_score,
            security_passed=security_passed,
            performance_passed=performance_passed,
            benchmark_passed=benchmark_passed,
            policy_violations=violations,
            passed=passed,
            approval_mode=approval_mode,
        )

    def health(self) -> dict[str, Any]:
        return {"alive": True}
