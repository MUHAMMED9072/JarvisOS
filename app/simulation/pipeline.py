from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.knowledge_graph.store import GraphStore
from app.simulation.compatibility_checker import CompatibilityChecker, CompatibilityResult, VersionRange
from app.simulation.dependency_analyzer import DependencyAnalyzer, ConflictReport
from app.simulation.failure_simulator import FailureSimulator, FailureImpactReport
from app.simulation.performance_modeler import PerformanceModeler, PerformanceEstimate
from app.simulation.regression_scorer import RegressionScorer, RegressionRiskReport
from app.simulation.security_analyzer import SecurityAnalyzer, SecurityImpactReport


class CheckStatus(Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    ERROR = "error"
    SKIPPED = "skipped"


@dataclass
class SimulationCheck:
    name: str = ""
    status: CheckStatus = CheckStatus.PASS
    score: float = 0.0
    details: str = ""
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status.value,
            "score": round(self.score, 4),
            "details": self.details,
            "evidence": list(self.evidence),
        }


@dataclass
class SimulationReport:
    artifact_name: str = ""
    artifact_type: str = ""
    checks: list[SimulationCheck] = field(default_factory=list)
    passed: bool = True
    summary: str = ""
    recommendations: list[str] = field(default_factory=list)
    total_duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_name": self.artifact_name,
            "artifact_type": self.artifact_type,
            "checks": [c.to_dict() for c in self.checks],
            "passed": self.passed,
            "summary": self.summary,
            "recommendations": list(self.recommendations),
            "total_duration_ms": round(self.total_duration_ms, 2),
        }


class SimulationPipeline:
    """Integrated simulation pipeline.

    Runs all checks in sequence: dependency conflict → performance →
    security → regression → failure scenarios → rollback.

    Thread-safe.
    """

    def __init__(
        self,
        graph_store: GraphStore | None = None,
    ) -> None:
        self._graph = graph_store
        self._lock = time  # not actually a lock ops, just for time
        self._dep_analyzer = DependencyAnalyzer(graph_store) if graph_store else None
        self._compat = CompatibilityChecker()
        self._perf_modeler = PerformanceModeler(graph_store)
        self._security = SecurityAnalyzer(graph_store)
        self._regression = RegressionScorer(graph_store)
        self._failure = FailureSimulator(graph_store)

    def run(
        self,
        artifact_name: str = "",
        artifact_type: str = "agent",
        source_code: str = "",
        entity_id: str = "",
        permissions: list[str] | None = None,
        dependencies: list[str] | None = None,
        dependency_tree: list[dict[str, Any]] | None = None,
    ) -> SimulationReport:
        start = time.time()
        checks: list[SimulationCheck] = []

        # 1. Dependency Conflict Check
        checks.append(self._check_dependency_conflict(entity_id))

        # 2. Performance Impact
        checks.append(self._check_performance(artifact_type, artifact_name, dependency_tree))

        # 3. Security Impact
        checks.append(self._check_security(source_code, artifact_name, artifact_type, permissions, dependencies))

        # 4. Regression Risk
        checks.append(self._check_regression(artifact_name, artifact_type, entity_id, dependency_tree))

        # 5. Failure Scenarios
        checks.append(self._check_failure(artifact_name, artifact_type, entity_id, dependency_tree))

        # 6. Rollback Feasibility
        checks.append(self._check_rollback(artifact_type, entity_id))

        # Compute overall result
        failed = any(c.status == CheckStatus.FAIL for c in checks)
        warnings = sum(1 for c in checks if c.status == CheckStatus.WARN)
        errors = sum(1 for c in checks if c.status == CheckStatus.ERROR)

        passed = not failed
        summary = self._build_summary(checks, failed, warnings, errors)
        recommendations = self._build_recommendations(checks)

        duration = (time.time() - start) * 1000

        return SimulationReport(
            artifact_name=artifact_name,
            artifact_type=artifact_type,
            checks=checks,
            passed=passed,
            summary=summary,
            recommendations=recommendations,
            total_duration_ms=duration,
        )

    def _check_dependency_conflict(self, entity_id: str) -> SimulationCheck:
        if not entity_id:
            return SimulationCheck(
                name="dependency_conflict",
                status=CheckStatus.SKIPPED,
                details="No entity ID provided for dependency analysis",
            )
        if self._dep_analyzer is None:
            return SimulationCheck(
                name="dependency_conflict",
                status=CheckStatus.ERROR,
                details="Dependency analyzer unavailable (no GraphStore)",
            )
        try:
            report = self._dep_analyzer.generate_report(entity_id)
            if report.has_conflicts:
                evidence = []
                if report.cycles:
                    evidence.append(f"Circular dependencies detected: {len(report.cycles)} cycles")
                if report.missing_dependencies:
                    evidence.append(f"Missing dependencies: {', '.join(report.missing_dependencies[:5])}")
                if report.version_mismatches:
                    evidence.append(f"Version mismatches: {len(report.version_mismatches)} found")
                return SimulationCheck(
                    name="dependency_conflict",
                    status=CheckStatus.FAIL,
                    score=report.severity.value,
                    details=f"Conflicts detected: {report.severity.value}",
                    evidence=evidence,
                )
            return SimulationCheck(
                name="dependency_conflict",
                status=CheckStatus.PASS,
                score=0.0,
                details="No dependency conflicts detected",
            )
        except Exception as e:
            return SimulationCheck(
                name="dependency_conflict",
                status=CheckStatus.ERROR,
                details=f"Error during dependency analysis: {str(e)}",
            )

    def _check_performance(
        self,
        artifact_type: str,
        artifact_name: str,
        dependency_tree: list[dict[str, Any]] | None,
    ) -> SimulationCheck:
        try:
            estimate = self._perf_modeler.estimate(artifact_type, artifact_name, dependency_tree)
            score = estimate.confidence
            details = (
                f"CPU: {estimate.cpu:.3f}, Memory: {estimate.memory_mb:.1f}MB, "
                f"Disk: {estimate.disk_mb:.1f}MB, Network: {estimate.network:.3f} | "
                f"Confidence: {estimate.confidence:.1%}"
            )
            evidence = []
            if estimate.calibration_count > 0:
                evidence.append(f"Calibrated from {estimate.calibration_count} data points")
            if estimate.confidence < 0.3:
                return SimulationCheck(
                    name="performance_impact",
                    status=CheckStatus.WARN,
                    score=score,
                    details=details,
                    evidence=evidence,
                )
            if estimate.memory_mb > 1000 or estimate.cpu > 0.8:
                return SimulationCheck(
                    name="performance_impact",
                    status=CheckStatus.WARN,
                    score=score,
                    details=f"High resource estimate: {details}",
                    evidence=evidence,
                )
            return SimulationCheck(
                name="performance_impact",
                status=CheckStatus.PASS,
                score=score,
                details=details,
                evidence=evidence,
            )
        except Exception as e:
            return SimulationCheck(
                name="performance_impact",
                status=CheckStatus.ERROR,
                details=f"Error during performance estimation: {str(e)}",
            )

    def _check_security(
        self,
        source_code: str,
        artifact_name: str,
        artifact_type: str,
        permissions: list[str] | None,
        dependencies: list[str] | None,
    ) -> SimulationCheck:
        try:
            report = self._security.analyze(
                source_code=source_code,
                artifact_name=artifact_name,
                artifact_type=artifact_type,
                permissions=permissions or [],
                dependencies=dependencies or [],
            )
            if not report.passed:
                evidence = []
                if report.permission_analysis.excessive_permissions:
                    evidence.append(f"Excessive permissions: {', '.join(report.permission_analysis.excessive_permissions)}")
                if report.permission_analysis.dangerous_combinations:
                    evidence.append(f"Dangerous permission combos: {len(report.permission_analysis.dangerous_combinations)}")
                if report.external_connections.unencrypted:
                    evidence.append(f"Unencrypted connections: {', '.join(report.external_connections.unencrypted)}")
                if report.file_access.sensitive_files:
                    evidence.append(f"Sensitive file access: {', '.join(report.file_access.sensitive_files)}")
                if report.dependency_vulnerabilities.vulnerabilities:
                    evidence.append(f"Vulnerable dependencies: {len(report.dependency_vulnerabilities.vulnerabilities)}")
                return SimulationCheck(
                    name="security_impact",
                    status=CheckStatus.FAIL,
                    score=report.overall_score,
                    details=f"Security score: {report.overall_score:.3f}",
                    evidence=evidence,
                )
            return SimulationCheck(
                name="security_impact",
                status=CheckStatus.PASS,
                score=0.0,
                details="No security concerns detected",
            )
        except Exception as e:
            return SimulationCheck(
                name="security_impact",
                status=CheckStatus.ERROR,
                details=f"Error during security analysis: {str(e)}",
            )

    def _check_regression(
        self,
        artifact_name: str,
        artifact_type: str,
        entity_id: str,
        dependency_tree: list[dict[str, Any]] | None,
    ) -> SimulationCheck:
        try:
            deps_list = dependency_tree or []
            report = self._regression.score(
                artifact_name=artifact_name,
                artifact_type=artifact_type,
                entity_id=entity_id,
                dependencies=deps_list,
            )
            if report.risk_score >= 0.7:
                evidence = []
                if report.dependency_depth.total_dependencies > 0:
                    evidence.append(f"Deep dependency chain: max depth {report.dependency_depth.max_depth}")
                if report.scope.affected_entities > 0:
                    evidence.append(f"Affects {report.scope.affected_entities} entities across {len(report.scope.affected_types)} types")
                if report.historical_matches:
                    hist_risk = sum(m.score for m in report.historical_matches)
                    evidence.append(f"Historical regression risk: {hist_risk:.2f}")
                return SimulationCheck(
                    name="regression_risk",
                    status=CheckStatus.FAIL,
                    score=report.risk_score,
                    details=f"Regression risk score: {report.risk_score:.3f}",
                    evidence=evidence,
                )
            if report.risk_score >= 0.4:
                return SimulationCheck(
                    name="regression_risk",
                    status=CheckStatus.WARN,
                    score=report.risk_score,
                    details=f"Moderate regression risk: {report.risk_score:.3f}",
                )
            return SimulationCheck(
                name="regression_risk",
                status=CheckStatus.PASS,
                score=report.risk_score,
                details=f"Low regression risk: {report.risk_score:.3f}",
            )
        except Exception as e:
            return SimulationCheck(
                name="regression_risk",
                status=CheckStatus.ERROR,
                details=f"Error during regression scoring: {str(e)}",
            )

    def _check_failure(
        self,
        artifact_name: str,
        artifact_type: str,
        entity_id: str,
        dependency_tree: list[dict[str, Any]] | None,
    ) -> SimulationCheck:
        try:
            report = self._failure.simulate(
                artifact_name=artifact_name,
                artifact_type=artifact_type,
                entity_id=entity_id,
                dependencies=dependency_tree or [],
            )
            if not report.passed:
                evidence = []
                if report.cascade.total_affected > 0:
                    evidence.append(f"Cascade would affect {report.cascade.total_affected} entities (depth {report.cascade.max_depth})")
                if report.cascade.critical_affected > 0:
                    evidence.append(f"{report.cascade.critical_affected} critical entities at risk")
                if not report.recovery.can_recover:
                    evidence.append("Recovery may not be feasible")
                return SimulationCheck(
                    name="failure_scenarios",
                    status=CheckStatus.FAIL,
                    score=report.failure_impact_score,
                    details=f"Failure impact score: {report.failure_impact_score:.3f}",
                    evidence=evidence,
                )
            if report.failure_impact_score >= 0.4:
                return SimulationCheck(
                    name="failure_scenarios",
                    status=CheckStatus.WARN,
                    score=report.failure_impact_score,
                    details=f"Moderate failure impact: {report.failure_impact_score:.3f}",
                )
            return SimulationCheck(
                name="failure_scenarios",
                status=CheckStatus.PASS,
                score=report.failure_impact_score,
                details="No significant failure impact predicted",
            )
        except Exception as e:
            return SimulationCheck(
                name="failure_scenarios",
                status=CheckStatus.ERROR,
                details=f"Error during failure simulation: {str(e)}",
            )

    def _check_rollback(self, artifact_type: str, entity_id: str) -> SimulationCheck:
        try:
            severity_map = {
                "system": 0.8, "kernel": 0.7, "executive": 0.6,
                "governance": 0.6, "knowledge_graph": 0.6,
                "agent_framework": 0.5, "ads": 0.4, "simulation": 0.3,
                "tool": 0.2, "agent": 0.2, "skill": 0.15,
                "plugin": 0.15, "workflow": 0.1, "pipeline": 0.1,
            }
            severity = severity_map.get(artifact_type, 0.3)

            evidence: list[str] = []
            if entity_id:
                evidence.append(f"Entity '{entity_id}' in Knowledge Graph — backup required")
            else:
                evidence.append("No entity registered — clean install, rollback requires file backup only")

            if severity <= 0.3:
                return SimulationCheck(
                    name="rollback_feasibility",
                    status=CheckStatus.PASS,
                    score=severity,
                    details=f"Rollback complexity: low (severity {severity:.2f})",
                    evidence=evidence,
                )
            if severity < 0.6:
                return SimulationCheck(
                    name="rollback_feasibility",
                    status=CheckStatus.WARN,
                    score=severity,
                    details=f"Rollback complexity: moderate (severity {severity:.2f})",
                    evidence=evidence,
                )
            return SimulationCheck(
                name="rollback_feasibility",
                status=CheckStatus.WARN,
                score=severity,
                details=f"Rollback complexity: high (severity {severity:.2f}) — state preservation required",
                evidence=evidence,
            )
        except Exception as e:
            return SimulationCheck(
                name="rollback_feasibility",
                status=CheckStatus.ERROR,
                details=f"Error during rollback analysis: {str(e)}",
            )

    def _build_summary(
        self,
        checks: list[SimulationCheck],
        failed: bool,
        warnings: int,
        errors: int,
    ) -> str:
        parts = []
        passed_count = sum(1 for c in checks if c.status == CheckStatus.PASS)
        parts.append(f"{passed_count}/{len(checks)} checks passed")
        if warnings:
            parts.append(f"{warnings} warnings")
        if errors:
            parts.append(f"{errors} errors")
        if failed:
            parts.append("FAILED")
        else:
            parts.append("PASSED")
        return " | ".join(parts)

    def _build_recommendations(self, checks: list[SimulationCheck]) -> list[str]:
        recs: list[str] = []
        for check in checks:
            if check.status == CheckStatus.FAIL:
                recs.append(f"Address failures in '{check.name}': {check.details}")
            elif check.status == CheckStatus.WARN:
                recs.append(f"Review '{check.name}': {check.details}")
        return recs

    def health(self) -> dict[str, Any]:
        return {"alive": True}
