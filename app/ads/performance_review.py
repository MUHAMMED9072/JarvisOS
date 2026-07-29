from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PerformanceIssue:
    category: str = ""
    severity: str = "info"
    description: str = ""
    recommendation: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "severity": self.severity,
            "description": self.description,
            "recommendation": self.recommendation,
        }


@dataclass
class PerformanceReport:
    """Performance review results for an artifact."""

    artifact_name: str = ""
    issues: list[PerformanceIssue] = field(default_factory=list)
    hotspots: list[str] = field(default_factory=list)
    resource_score: float = 1.0  # 0-1 scale
    passed: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_name": self.artifact_name,
            "issues": [i.to_dict() for i in self.issues],
            "hotspots": list(self.hotspots),
            "resource_score": self.resource_score,
            "passed": self.passed,
        }


class PerformanceReviewer:
    """Analyze source code for performance bottlenecks."""

    # Patterns that may indicate performance issues
    PERFORMANCE_PATTERNS: list[dict[str, Any]] = [
        {
            "category": "loop",
            "pattern": "for ",
            "severity": "info",
            "description": "Loop detected — ensure it's not O(n^2)",
            "recommendation": "Consider using list comprehensions or vectorized operations",
        },
        {
            "category": "recursion",
            "pattern": "def .*self",
            "severity": "info",
            "description": "Method definition — check for deep recursion",
            "recommendation": "Consider iterative approach if recursion depth > 1000",
        },
        {
            "category": "io",
            "pattern": ".open(",
            "severity": "info",
            "description": "File I/O operation",
            "recommendation": "Use context managers and buffered I/O",
        },
        {
            "category": "memory",
            "pattern": "list(",
            "severity": "info",
            "description": "List construction — monitor for large allocations",
            "recommendation": "Consider generator expressions for large datasets",
        },
        {
            "category": "network",
            "pattern": "requests.",
            "severity": "info",
            "description": "Network request — may add latency",
            "recommendation": "Use connection pooling and async where possible",
        },
        {
            "category": "import",
            "pattern": "import ",
            "severity": "info",
            "description": "Import statement",
            "recommendation": "Use lazy imports for heavy modules",
        },
    ]

    def review(self, source: str, artifact_name: str = "artifact") -> PerformanceReport:
        issues: list[PerformanceIssue] = []
        hotspots: list[str] = []

        for pattern in self.PERFORMANCE_PATTERNS:
            count = source.count(pattern["pattern"])
            if count > 3:
                issues.append(PerformanceIssue(
                    category=pattern["category"],
                    severity="warning" if count > 10 else pattern["severity"],
                    description=f"{pattern['description']} ({count} occurrences)",
                    recommendation=pattern["recommendation"],
                ))
                if count > 3:
                    hotspots.append(f"{pattern['category']}: {count} occurrences")

        # Estimate resource score based on number of issues
        resource_score = max(0.0, 1.0 - (len(issues) * 0.1))

        return PerformanceReport(
            artifact_name=artifact_name,
            issues=issues,
            hotspots=hotspots,
            resource_score=round(resource_score, 2),
            passed=resource_score >= 0.5,
        )

    def health(self) -> dict[str, Any]:
        return {"alive": True, "patterns": len(self.PERFORMANCE_PATTERNS)}
