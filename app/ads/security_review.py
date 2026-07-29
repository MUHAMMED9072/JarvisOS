from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Any


DANGEROUS_PATTERNS: list[dict[str, Any]] = [
    {"name": "eval_usage", "pattern": "eval(", "severity": "high", "description": "Use of eval() allows arbitrary code execution"},
    {"name": "exec_usage", "pattern": "exec(", "severity": "high", "description": "Use of exec() allows arbitrary code execution"},
    {"name": "subprocess_shell", "pattern": "shell=True", "severity": "high", "description": "shell=True allows shell injection"},
    {"name": "pickle_load", "pattern": "pickle.load", "severity": "medium", "description": "pickle.load can execute arbitrary code"},
    {"name": "requests_without_verify", "pattern": "verify=False", "severity": "medium", "description": "SSL verification disabled"},
    {"name": "hardcoded_password", "pattern": "password=", "severity": "high", "description": "Possible hardcoded credential"},
    {"name": "insecure_hash", "pattern": "hashlib.md5", "severity": "low", "description": "MD5 is cryptographically broken"},
    {"name": "temp_file", "pattern": "tempfile.mkstemp", "severity": "low", "description": "Temporary file usage"},
    {"name": "file_write", "pattern": ".write(", "severity": "low", "description": "File write operation"},
    {"name": "network_access", "pattern": "socket.", "severity": "medium", "description": "Network socket access"},
]


@dataclass
class SecurityIssue:
    pattern_name: str = ""
    severity: str = "low"
    description: str = ""
    line_number: int = 0
    code_snippet: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "pattern_name": self.pattern_name,
            "severity": self.severity,
            "description": self.description,
            "line_number": self.line_number,
            "code_snippet": self.code_snippet,
        }


@dataclass
class SecurityReport:
    """Security review results for an artifact."""

    artifact_name: str = ""
    issues: list[SecurityIssue] = field(default_factory=list)
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
    passed: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_name": self.artifact_name,
            "issues": [i.to_dict() for i in self.issues],
            "high_count": self.high_count,
            "medium_count": self.medium_count,
            "low_count": self.low_count,
            "passed": self.passed,
            "total_issues": len(self.issues),
        }


class SecurityReviewer:
    """Static analysis for dangerous patterns and permission validation."""

    def review(self, source: str, artifact_name: str = "artifact") -> SecurityReport:
        issues: list[SecurityIssue] = []

        for pattern in DANGEROUS_PATTERNS:
            for i, line in enumerate(source.splitlines(), 1):
                if pattern["pattern"] in line:
                    issues.append(SecurityIssue(
                        pattern_name=pattern["name"],
                        severity=pattern["severity"],
                        description=pattern["description"],
                        line_number=i,
                        code_snippet=line.strip(),
                    ))

        # Syntax check via AST
        try:
            ast.parse(source)
        except SyntaxError as e:
            issues.append(SecurityIssue(
                pattern_name="syntax_error",
                severity="high",
                description=f"Syntax error: {e}",
                line_number=e.lineno or 0,
                code_snippet=str(e),
            ))

        high = sum(1 for i in issues if i.severity == "high")
        medium = sum(1 for i in issues if i.severity == "medium")
        low = sum(1 for i in issues if i.severity == "low")

        return SecurityReport(
            artifact_name=artifact_name,
            issues=issues,
            high_count=high,
            medium_count=medium,
            low_count=low,
            passed=high == 0,
        )

    def health(self) -> dict[str, Any]:
        return {"alive": True, "dangerous_patterns": len(DANGEROUS_PATTERNS)}
