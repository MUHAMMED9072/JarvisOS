from app.simulation.dependency_analyzer import DependencyAnalyzer, DependencyNode, ConflictReport, ConflictSeverity
from app.simulation.compatibility_checker import CompatibilityChecker, VersionRange, CompatibilityResult
from app.simulation.impact_estimator import ImpactEstimator, ImpactEstimate, ResourceImpact
from app.simulation.performance_modeler import PerformanceModeler, PerformanceEstimate, CalibrationEntry, ModelCalibration
from app.simulation.performance_modeler import PerformanceModeler, PerformanceEstimate, CalibrationEntry, ModelCalibration
from app.simulation.security_analyzer import (
    SecurityAnalyzer, SecurityImpactReport, PermissionAnalysis,
    ExternalConnectionAnalysis, FileAccessAnalysis,
    DependencyVulnerability, DependencyVulnerabilityCheck,
)
from app.simulation.regression_scorer import (
    RegressionScorer, RegressionRiskReport, DependencyDepthAnalysis,
    ScopeAnalysis, HistoricalMatch,
)

__all__ = [
    "DependencyAnalyzer", "DependencyNode", "ConflictReport", "ConflictSeverity",
    "CompatibilityChecker", "VersionRange", "CompatibilityResult",
    "ImpactEstimator", "ImpactEstimate", "ResourceImpact",
    "PerformanceModeler", "PerformanceEstimate", "CalibrationEntry", "ModelCalibration",
    "SecurityAnalyzer", "SecurityImpactReport", "PermissionAnalysis",
    "ExternalConnectionAnalysis", "FileAccessAnalysis",
    "DependencyVulnerability", "DependencyVulnerabilityCheck",
    "RegressionScorer", "RegressionRiskReport", "DependencyDepthAnalysis",
    "ScopeAnalysis", "HistoricalMatch",
]
