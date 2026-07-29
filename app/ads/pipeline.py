from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from app.ads.architecture_designer import ArchitectureDesigner, ArchitectureSpec
from app.ads.benchmark import BenchmarkReport, BenchmarkRunner
from app.ads.capability_analysis import CapabilityAnalyzer, CapabilityAnalysisResult
from app.ads.content_generator import ContentGenerator, GeneratedContent
from app.ads.gap_detector import GapDetector, GapReport
from app.ads.governance import GovernanceChecker, GovernanceResult
from app.ads.installer import InstallResult, Installer
from app.ads.learning import LearningLoop
from app.ads.metrics import MetricsCollector
from app.ads.performance_review import PerformanceReport, PerformanceReviewer
from app.ads.registration import Registration, RegistrationResult
from app.ads.requirements import RequirementsAnalyzer, RequirementsDocument
from app.ads.sandbox import AdsSandbox, ExecutionResult
from app.ads.security_review import SecurityReport, SecurityReviewer
from app.ads.test_generator import GeneratedTests, TestGenerator
from app.ads.versioning import VersionManager
from app.knowledge_graph.store import GraphStore
from app.simulation.pipeline import SimulationPipeline


class StageStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class StageResult:
    stage_name: str = ""
    status: StageStatus = StageStatus.PENDING
    output: Any = None
    error: str = ""
    duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage_name": self.stage_name,
            "status": self.status.value,
            "error": self.error,
            "duration_ms": self.duration_ms,
        }


@dataclass
class PipelineContext:
    request: str = ""
    requirements: RequirementsDocument | None = None
    capability_result: CapabilityAnalysisResult | None = None
    gap_report: GapReport | None = None
    specs: list[ArchitectureSpec] = field(default_factory=list)
    content: GeneratedContent | None = None
    tests: GeneratedTests | None = None
    execution_result: ExecutionResult | None = None
    source_code: str = ""
    security_report: SecurityReport | None = None
    performance_report: PerformanceReport | None = None
    benchmark_report: BenchmarkReport | None = None
    simulation_report: SimulationReport | None = None
    governance_result: GovernanceResult | None = None
    install_result: InstallResult | None = None
    registration_result: RegistrationResult | None = None

    def to_dict(self) -> dict[str, Any]:
        return {k: str(v) for k, v in self.__dict__.items() if v is not None}


StageFn = Callable[[PipelineContext], Any]


@dataclass
class PipelineReport:
    artifact_name: str = ""
    success: bool = False
    stages: list[StageResult] = field(default_factory=list)
    total_duration_ms: float = 0.0
    artifact_path: str = ""
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_name": self.artifact_name,
            "success": self.success,
            "stages": [s.to_dict() for s in self.stages],
            "total_duration_ms": self.total_duration_ms,
            "artifact_path": self.artifact_path,
            "error": self.error,
        }


class Pipeline:
    """Orchestrate all ADS stages in sequence with data passing between stages."""

    def __init__(
        self,
        graph_store: GraphStore | None = None,
    ) -> None:
        self._graph_store = graph_store or GraphStore()
        self._requirements = RequirementsAnalyzer()
        self._capabilities = CapabilityAnalyzer(self._graph_store)
        self._gaps = GapDetector(self._graph_store)
        self._designer = ArchitectureDesigner()
        self._generator = ContentGenerator()
        self._test_gen = TestGenerator()
        self._sandbox = AdsSandbox()
        self._security = SecurityReviewer()
        self._performance = PerformanceReviewer()
        self._benchmark = BenchmarkRunner(self._sandbox)
        self._governance = GovernanceChecker()
        self._installer = Installer()
        self._registration = Registration(self._graph_store)
        self._versioning = VersionManager(self._graph_store)
        self._metrics = MetricsCollector(self._graph_store)
        self._learning = LearningLoop(self._graph_store)
        self._simulation = SimulationPipeline(self._graph_store)

    def run(self, request: str) -> PipelineReport:
        ctx = PipelineContext(request=request)
        stages: list[StageResult] = []
        start = time.time()

        # Stage 1: Requirements Analysis
        stages.append(self._run_stage("requirements", ctx, self._stage_requirements))
        if stages[-1].status == StageStatus.FAILED:
            return self._build_report(ctx, stages, start)

        # Stage 2: Capability Analysis
        stages.append(self._run_stage("capability_analysis", ctx, self._stage_capabilities))
        if stages[-1].status == StageStatus.FAILED:
            return self._build_report(ctx, stages, start)

        # Stage 3: Gap Detection
        stages.append(self._run_stage("gap_detection", ctx, self._stage_gaps))
        if stages[-1].status == StageStatus.FAILED:
            return self._build_report(ctx, stages, start)

        # Stage 4: Architecture Design
        stages.append(self._run_stage("architecture", ctx, self._stage_architecture))
        if stages[-1].status == StageStatus.FAILED:
            return self._build_report(ctx, stages, start)

        # Stage 5: Content Generation
        stages.append(self._run_stage("content_generation", ctx, self._stage_content))
        if stages[-1].status == StageStatus.FAILED:
            return self._build_report(ctx, stages, start)

        # Stage 6: Test Generation
        stages.append(self._run_stage("test_generation", ctx, self._stage_tests))
        if stages[-1].status == StageStatus.FAILED:
            return self._build_report(ctx, stages, start)

        # Stage 7: Sandbox Execution
        stages.append(self._run_stage("sandbox", ctx, self._stage_sandbox))
        if stages[-1].status == StageStatus.FAILED:
            return self._build_report(ctx, stages, start)

        # Stage 8: Security Review
        stages.append(self._run_stage("security_review", ctx, self._stage_security))
        if stages[-1].status == StageStatus.FAILED:
            return self._build_report(ctx, stages, start)

        # Stage 9: Performance Review
        stages.append(self._run_stage("performance_review", ctx, self._stage_performance))

        # Stage 10: Benchmark
        stages.append(self._run_stage("benchmark", ctx, self._stage_benchmark))

        # Stage 11: Simulation (run before governance to inform risk scoring)
        stages.append(self._run_stage("simulation", ctx, self._stage_simulation))

        # Stage 12: Governance
        stages.append(self._run_stage("governance", ctx, self._stage_governance))
        if stages[-1].status == StageStatus.FAILED:
            return self._build_report(ctx, stages, start)
        gov_result = ctx.governance_result
        if gov_result and not gov_result.passed:
            report = self._build_report(ctx, stages, start)
            report.success = False
            report.error = "Governance check failed"
            return report

        # Stage 13: Installation
        stages.append(self._run_stage("installation", ctx, self._stage_install))
        if stages[-1].status == StageStatus.FAILED:
            return self._build_report(ctx, stages, start)

        # Stage 14: Registration
        stages.append(self._run_stage("registration", ctx, self._stage_registration))

        # Stage 15: Versioning
        stages.append(self._run_stage("versioning", ctx, self._stage_versioning))

        # Stage 16: Metrics Initialization
        stages.append(self._run_stage("metrics", ctx, self._stage_metrics))

        report = self._build_report(ctx, stages, start)
        report.success = True
        return report

    def _run_stage(self, name: str, ctx: PipelineContext, fn: StageFn) -> StageResult:
        stage_start = time.time()
        result = StageResult(stage_name=name, status=StageStatus.RUNNING)
        try:
            output = fn(ctx)
            result.status = StageStatus.PASSED
            result.output = output
        except Exception as e:
            result.status = StageStatus.FAILED
            result.error = str(e)
        result.duration_ms = (time.time() - stage_start) * 1000
        return result

    def _stage_requirements(self, ctx: PipelineContext) -> RequirementsDocument:
        doc = self._requirements.analyze(ctx.request)
        ctx.requirements = doc
        return doc

    def _stage_capabilities(self, ctx: PipelineContext) -> CapabilityAnalysisResult:
        assert ctx.requirements is not None
        result = self._capabilities.analyze(ctx.requirements)
        ctx.capability_result = result
        return result

    def _stage_gaps(self, ctx: PipelineContext) -> GapReport:
        assert ctx.requirements is not None and ctx.capability_result is not None
        report = self._gaps.detect(ctx.requirements, ctx.capability_result)
        ctx.gap_report = report
        return report

    def _stage_architecture(self, ctx: PipelineContext) -> list[ArchitectureSpec]:
        assert ctx.requirements is not None and ctx.gap_report is not None
        specs = self._designer.design(ctx.requirements, ctx.gap_report)
        ctx.specs = specs
        return specs

    def _stage_content(self, ctx: PipelineContext) -> GeneratedContent:
        assert ctx.specs
        spec = ctx.specs[0]
        content = self._generator.generate(spec)
        ctx.content = content
        ctx.source_code = list(content.files.values())[0] if content.files else ""
        return content

    def _stage_tests(self, ctx: PipelineContext) -> GeneratedTests:
        assert ctx.specs and ctx.content is not None
        spec = ctx.specs[0]
        tests = self._test_gen.generate(spec, ctx.content)
        ctx.tests = tests
        return tests

    def _stage_sandbox(self, ctx: PipelineContext) -> ExecutionResult:
        source = ctx.source_code
        if not source and ctx.content:
            source = list(ctx.content.files.values())[0] if ctx.content.files else ""
        if not source:
            source = "class Placeholder: pass"
        result = self._sandbox.run_code(source)
        ctx.execution_result = result
        return result

    def _stage_security(self, ctx: PipelineContext) -> SecurityReport:
        source = ctx.source_code or "class Placeholder: pass"
        report = self._security.review(source)
        ctx.security_report = report
        return report

    def _stage_performance(self, ctx: PipelineContext) -> PerformanceReport:
        source = ctx.source_code or "class Placeholder: pass"
        report = self._performance.review(source)
        ctx.performance_report = report
        return report

    def _stage_benchmark(self, ctx: PipelineContext) -> BenchmarkReport:
        source = ctx.source_code or "class Placeholder: pass"
        report = self._benchmark.benchmark(source, artifact_name=ctx.specs[0].name if ctx.specs else "artifact")
        ctx.benchmark_report = report
        return report

    def _stage_simulation(self, ctx: PipelineContext) -> SimulationReport:
        artifact_name = ctx.specs[0].name if ctx.specs else "artifact"
        atype = ctx.content.manifest.get("type", "agent") if ctx.content else "agent"
        source = ctx.source_code or ""
        report = self._simulation.run(
            artifact_name=artifact_name,
            artifact_type=atype,
            source_code=source,
            entity_id=artifact_name,
            permissions=None,
            dependencies=None,
        )
        ctx.simulation_report = report
        return report

    def _stage_governance(self, ctx: PipelineContext) -> GovernanceResult:
        artifact_name = ctx.specs[0].name if ctx.specs else "artifact"
        result = self._governance.check(
            artifact_name=artifact_name,
            trust_level="low",
            security_report=ctx.security_report,
            performance_report=ctx.performance_report,
            benchmark_report=ctx.benchmark_report,
            simulation_report=ctx.simulation_report,
        )
        ctx.governance_result = result
        return result

    def _stage_install(self, ctx: PipelineContext) -> InstallResult:
        artifact_name = ctx.specs[0].name if ctx.specs else "artifact"
        assert ctx.content is not None
        result = self._installer.install(artifact_name, ctx.content)
        ctx.install_result = result
        return result

    def _stage_registration(self, ctx: PipelineContext) -> RegistrationResult:
        artifact_name = ctx.specs[0].name if ctx.specs else "artifact"
        assert ctx.content is not None
        result = self._registration.register(artifact_name, ctx.content)
        ctx.registration_result = result
        return result

    def _stage_versioning(self, ctx: PipelineContext) -> Any:
        artifact_name = ctx.specs[0].name if ctx.specs else "artifact"
        assert ctx.content is not None
        result = self._versioning.create_initial_version(artifact_name, ctx.content)
        return result

    def _stage_metrics(self, ctx: PipelineContext) -> Any:
        artifact_name = ctx.specs[0].name if ctx.specs else "artifact"
        atype = ctx.content.manifest.get("type", "agent") if ctx.content else "agent"
        bench_data = ctx.benchmark_report.to_dict() if ctx.benchmark_report else None
        result = self._metrics.initialize_baseline(artifact_name, atype, bench_data)
        return result

    def _build_report(self, ctx: PipelineContext, stages: list[StageResult], start: float) -> PipelineReport:
        artifact_name = ctx.specs[0].name if ctx.specs else ""
        install_path = ctx.install_result.install_path if ctx.install_result else ""
        return PipelineReport(
            artifact_name=artifact_name,
            stages=stages,
            total_duration_ms=(time.time() - start) * 1000,
            artifact_path=install_path,
        )

    def health(self) -> dict[str, Any]:
        return {"alive": True}
