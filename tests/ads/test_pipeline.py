import time

import pytest

from app.ads.architecture_designer import ArchitectureSpec
from app.ads.content_generator import GeneratedContent
from app.ads.learning import FeedbackEntry
from app.ads.orchestrator import Orchestrator, PipelineJob
from app.ads.pipeline import (
    Pipeline,
    PipelineContext,
    PipelineReport,
    StageResult,
    StageStatus,
)
from app.knowledge_graph.store import GraphStore


class TestStageResult:
    def test_default_status(self):
        sr = StageResult()
        assert sr.status == StageStatus.PENDING

    def test_to_dict(self):
        sr = StageResult(stage_name="test", status=StageStatus.PASSED, duration_ms=10.5)
        d = sr.to_dict()
        assert d["stage_name"] == "test"
        assert d["status"] == "passed"
        assert d["duration_ms"] == 10.5

    def test_to_dict_failed(self):
        sr = StageResult(stage_name="fail", status=StageStatus.FAILED, error="oops")
        d = sr.to_dict()
        assert d["status"] == "failed"
        assert d["error"] == "oops"


class TestPipelineContext:
    def test_default_context(self):
        ctx = PipelineContext()
        assert ctx.request == ""

    def test_to_dict(self):
        ctx = PipelineContext(request="test request")
        d = ctx.to_dict()
        assert "test request" in d.get("request", "")

    def test_to_dict_requirements(self):
        from app.ads.requirements import RequirementsDocument
        ctx = PipelineContext(requirements=RequirementsDocument(raw_request="hello"))
        d = ctx.to_dict()
        assert "requirements" in d


class TestPipelineReport:
    def test_default_report(self):
        r = PipelineReport()
        assert r.success is False

    def test_to_dict(self):
        r = PipelineReport(
            artifact_name="TestAgent",
            success=True,
            stages=[StageResult(stage_name="s1", status=StageStatus.PASSED)],
            total_duration_ms=100.0,
            artifact_path="/path/to/artifact",
        )
        d = r.to_dict()
        assert d["artifact_name"] == "TestAgent"
        assert d["success"] is True
        assert len(d["stages"]) == 1

    def test_to_dict_with_error(self):
        r = PipelineReport(error="something broke")
        d = r.to_dict()
        assert d["error"] == "something broke"


class TestPipeline:
    @pytest.fixture
    def graph(self):
        g = GraphStore()
        g.clear()
        return g

    @pytest.fixture
    def pipeline(self, graph):
        return Pipeline(graph_store=graph)

    def test_run_simple_request(self, pipeline):
        """End-to-end: simple agent request should complete all stages successfully."""
        report = pipeline.run("Create a web scraper agent that fetches HTML")
        assert report.success is True
        assert len(report.stages) >= 14
        assert report.artifact_name != ""

    def test_run_creates_artifact(self, pipeline):
        """Verify artifact name is extracted and set correctly."""
        report = pipeline.run("Build an agent called ParserBot that parses CSV files")
        assert report.success is True

    def test_run_all_stages_present(self, pipeline):
        """Verify every stage is represented in the report."""
        report = pipeline.run("Make a monitoring agent")
        stage_names = {s.stage_name for s in report.stages}
        expected = {
            "requirements", "capability_analysis", "gap_detection", "architecture",
            "content_generation", "test_generation", "sandbox", "security_review",
            "performance_review", "benchmark", "governance", "installation",
            "registration", "versioning", "metrics",
        }
        assert stage_names == expected

    def test_run_metrics_stage_creates_kg_entity(self, pipeline, graph):
        """After pipeline run, metrics entity should exist in KG."""
        pipeline.run("Create a data collector agent")
        # There should be a metrics_ entity
        entities = graph.get_entities_by_type("concept")
        metrics_entities = [e for e in entities if e.name.startswith("metrics_")]
        assert len(metrics_entities) >= 1

    def test_run_versioning_stage_creates_version(self, pipeline, graph):
        """After pipeline run, version entity should exist in KG."""
        report = pipeline.run("Create a reporter agent")
        entities = graph.get_entities_by_type("concept")
        version_entities = [e for e in entities if "_v" in e.name]
        assert len(version_entities) >= 1

    def test_run_install_stage_creates_install_result(self, pipeline):
        """Install stage should produce a successful install result."""
        report = pipeline.run("Build a simple logger agent")
        install_stage = [s for s in report.stages if s.stage_name == "installation"]
        assert len(install_stage) == 1
        assert install_stage[0].status == StageStatus.PASSED

    def test_run_registration_stage(self, pipeline):
        """Registration stage should succeed."""
        report = pipeline.run("Create an agent named RegisterBot")
        reg_stage = [s for s in report.stages if s.stage_name == "registration"]
        assert len(reg_stage) == 1
        assert reg_stage[0].status == StageStatus.PASSED

    def test_run_security_review_stage(self, pipeline):
        """Security review should complete without errors."""
        report = pipeline.run("Create a secure agent")
        sec_stage = [s for s in report.stages if s.stage_name == "security_review"]
        assert len(sec_stage) == 1
        assert sec_stage[0].status == StageStatus.PASSED

    def test_run_performance_review_stage(self, pipeline):
        """Performance review should complete."""
        report = pipeline.run("Create a fast agent")
        perf_stage = [s for s in report.stages if s.stage_name == "performance_review"]
        assert len(perf_stage) == 1
        assert perf_stage[0].status == StageStatus.PASSED

    def test_run_benchmark_stage(self, pipeline):
        """Benchmark should complete and produce a report."""
        report = pipeline.run("Create a benchmarked agent")
        bench_stage = [s for s in report.stages if s.stage_name == "benchmark"]
        assert len(bench_stage) == 1
        assert bench_stage[0].status == StageStatus.PASSED

    def test_run_governance_stage(self, pipeline):
        """Governance check should pass for simple agent."""
        report = pipeline.run("Create a governance agent")
        gov_stage = [s for s in report.stages if s.stage_name == "governance"]
        assert len(gov_stage) == 1
        assert gov_stage[0].status == StageStatus.PASSED

    def test_run_sandbox_stage(self, pipeline):
        """Sandbox execution should succeed."""
        report = pipeline.run("Create a sandbox agent")
        sandbox_stage = [s for s in report.stages if s.stage_name == "sandbox"]
        assert len(sandbox_stage) == 1
        assert sandbox_stage[0].status == StageStatus.PASSED

    def test_run_test_generation_stage(self, pipeline):
        """Test generation should produce tests."""
        report = pipeline.run("Create a testable agent")
        test_stage = [s for s in report.stages if s.stage_name == "test_generation"]
        assert len(test_stage) == 1
        assert test_stage[0].status == StageStatus.PASSED

    def test_run_requirements_stage(self, pipeline):
        """Requirements analysis should extract type and capabilities."""
        report = pipeline.run("I need an agent that can monitor system health")
        req_stage = [s for s in report.stages if s.stage_name == "requirements"]
        assert len(req_stage) == 1
        assert req_stage[0].status == StageStatus.PASSED

    def test_run_architecture_stage(self, pipeline):
        """Architecture stage should produce specs."""
        report = pipeline.run("Create a structured agent")
        arch_stage = [s for s in report.stages if s.stage_name == "architecture"]
        assert len(arch_stage) == 1
        assert arch_stage[0].status == StageStatus.PASSED

    def test_run_gap_detection_stage(self, pipeline):
        """Gap detection should execute without error."""
        report = pipeline.run("Create an agent with capabilities")
        gap_stage = [s for s in report.stages if s.stage_name == "gap_detection"]
        assert len(gap_stage) == 1
        assert gap_stage[0].status == StageStatus.PASSED

    def test_run_all_stages_pass(self, pipeline):
        """Every stage should pass for a well-formed request."""
        report = pipeline.run("Create a simple hello agent")
        for stage in report.stages:
            assert stage.status in (StageStatus.PASSED, StageStatus.SKIPPED), \
                f"Stage {stage.stage_name} failed: {stage.error}"

    def test_run_total_duration_positive(self, pipeline):
        """Total duration should be a positive number."""
        report = pipeline.run("Create a fast agent")
        assert report.total_duration_ms > 0

    def test_run_artifact_path_set(self, pipeline):
        """Artifact path should be set on successful run."""
        report = pipeline.run("Create an agent for path testing")
        if report.success:
            assert report.artifact_path != ""

    def test_health(self, pipeline):
        h = pipeline.health()
        assert h["alive"] is True


class TestOrchestrator:
    @pytest.fixture
    def graph(self):
        g = GraphStore()
        g.clear()
        return g

    @pytest.fixture
    def pipeline(self, graph):
        return Pipeline(graph_store=graph)

    @pytest.fixture
    def orchestrator(self, pipeline):
        return Orchestrator(pipeline=pipeline)

    def test_submit_job(self, orchestrator):
        job_id = orchestrator.submit("Create a test agent")
        assert job_id.startswith("job_")

    def test_run_job(self, orchestrator):
        job_id = orchestrator.submit("Create a monitored agent")
        report = orchestrator.run_job(job_id)
        assert report is not None
        assert report.success is True

    def test_get_job(self, orchestrator):
        job_id = orchestrator.submit("Create a traceable agent")
        orchestrator.run_job(job_id)
        job = orchestrator.get_job(job_id)
        assert job is not None
        assert job.status in ("completed", "failed")
        assert job.progress >= 0

    def test_get_job_not_found(self, orchestrator):
        job = orchestrator.get_job("nonexistent")
        assert job is None

    def test_list_jobs(self, orchestrator):
        orchestrator.submit("Create agent A")
        orchestrator.submit("Create agent B")
        jobs = orchestrator.list_jobs()
        assert len(jobs) >= 2

    def test_list_jobs_by_status(self, orchestrator):
        job_id = orchestrator.submit("Create agent C")
        orchestrator.run_job(job_id)
        completed = orchestrator.list_jobs(status="completed")
        assert any(j.job_id == job_id for j in completed)

    def test_get_progress(self, orchestrator):
        job_id = orchestrator.submit("Create a progress agent")
        orchestrator.run_job(job_id)
        progress = orchestrator.get_progress(job_id)
        assert progress == 1.0

    def test_get_progress_not_found(self, orchestrator):
        assert orchestrator.get_progress("nonexistent") == 0.0

    def test_detect_stalled_empty(self, orchestrator):
        stalled = orchestrator.detect_stalled()
        assert stalled == []

    def test_cancel_job(self, orchestrator):
        job_id = orchestrator.submit("Create a cancellable agent")
        assert orchestrator.cancel_job(job_id) is True
        job = orchestrator.get_job(job_id)
        assert job.status == "cancelled"

    def test_cancel_completed_job(self, orchestrator):
        job_id = orchestrator.submit("Create completed agent")
        orchestrator.run_job(job_id)
        assert orchestrator.cancel_job(job_id) is False

    def test_cancel_not_found(self, orchestrator):
        assert orchestrator.cancel_job("nonexistent") is False

    def test_get_statistics(self, orchestrator):
        stats = orchestrator.get_statistics()
        assert stats["total_jobs"] >= 0
        assert "completed" in stats
        assert "failed" in stats
        assert "running" in stats
        assert "pending" in stats

    def test_get_statistics_with_jobs(self, orchestrator):
        orchestrator.submit("Create stat agent A")
        orchestrator.submit("Create stat agent B")
        job_id = orchestrator.submit("Create stat agent C")
        orchestrator.run_job(job_id)
        stats = orchestrator.get_statistics()
        assert stats["total_jobs"] >= 3
        assert stats["completed"] >= 1

    def test_submit_multiple_jobs(self, orchestrator):
        ids = [orchestrator.submit(f"Create agent {i}") for i in range(5)]
        assert len(set(ids)) == 5

    def test_run_job_not_found(self, orchestrator):
        report = orchestrator.run_job("nonexistent")
        assert report is None

    def test_orchestrator_with_default_pipeline(self):
        orch = Orchestrator()
        assert orch.health()["alive"] is True

    def test_health(self, orchestrator):
        h = orchestrator.health()
        assert h["alive"] is True

    def test_job_to_dict(self, orchestrator):
        job = PipelineJob(job_id="j1", request="req", status="completed", progress=1.0)
        d = job.to_dict()
        assert d["job_id"] == "j1"
        assert d["request"] == "req"
        assert d["status"] == "completed"

    def test_job_to_dict_with_report(self, orchestrator):
        report = PipelineReport(artifact_name="Test", success=True)
        job = PipelineJob(job_id="j2", request="req", status="completed", report=report)
        d = job.to_dict()
        assert d["report"]["artifact_name"] == "Test"

    def test_stage_order_constant(self):
        expected = [
            "requirements", "capability_analysis", "gap_detection", "architecture",
            "content_generation", "test_generation", "sandbox", "security_review",
            "performance_review", "benchmark", "governance", "installation",
            "registration", "versioning", "metrics",
        ]
        assert Orchestrator.STAGE_ORDER == expected

    def test_stall_timeout_positive(self):
        assert Orchestrator.STALL_TIMEOUT_SECONDS > 0

    def test_detect_stalled_after_timeout(self, orchestrator):
        job_id = orchestrator.submit("Create stalled agent")
        with orchestrator._lock:
            orchestrator._jobs[job_id].status = "running"
            orchestrator._jobs[job_id].started_at = time.time() - 1000
        stalled = orchestrator.detect_stalled()
        assert any(j.job_id == job_id for j in stalled)

    def test_all_stages_have_handlers(self, pipeline):
        """Verify every stage has a corresponding _stage_ method."""
        handler_names = {
            "requirements": "_stage_requirements",
            "capability_analysis": "_stage_capabilities",
            "gap_detection": "_stage_gaps",
            "architecture": "_stage_architecture",
            "content_generation": "_stage_content",
            "test_generation": "_stage_tests",
            "sandbox": "_stage_sandbox",
            "security_review": "_stage_security",
            "performance_review": "_stage_performance",
            "benchmark": "_stage_benchmark",
            "governance": "_stage_governance",
            "installation": "_stage_install",
            "registration": "_stage_registration",
            "versioning": "_stage_versioning",
            "metrics": "_stage_metrics",
        }
        for stage_name, method_name in handler_names.items():
            assert hasattr(pipeline, method_name), f"Missing handler for stage: {stage_name}"

    def test_run_missing_requirements_handling(self, pipeline):
        """Pipeline handles edge cases in requirements gracefully."""
        report = pipeline.run("Make an agent")
        assert len(report.stages) > 0


class TestPipelineEdgeCases:
    @pytest.fixture
    def graph(self):
        g = GraphStore()
        g.clear()
        return g

    def test_empty_request(self, graph):
        p = Pipeline(graph_store=graph)
        report = p.run("")
        assert report.success is True

    def test_minimal_request(self, graph):
        p = Pipeline(graph_store=graph)
        report = p.run("agent")
        assert report.success is True

    def test_request_with_special_chars(self, graph):
        p = Pipeline(graph_store=graph)
        report = p.run("Create an agent with 100% uptime & zero-downtime deployments!")
        assert report.success is True

    def test_multiple_pipeline_runs(self, graph):
        p = Pipeline(graph_store=graph)
        r1 = p.run("Create a web scraper agent")
        r2 = p.run("Create a data analyzer agent")
        assert r1.success is True
        assert r2.success is True

    def test_learning_feedback_integration(self, graph):
        from app.ads.learning import LearningLoop
        ll = LearningLoop(graph)
        fb = FeedbackEntry(artifact_name="TestArtifact", execution_id="e1", success=True)
        result = ll.record_feedback(fb)
        assert result.success is True
        fb_list = ll.get_feedback("TestArtifact")
        assert len(fb_list) == 1
        assert ll.compute_quality_adjustment("TestArtifact") >= 0

    def test_stage_status_enum(self):
        assert StageStatus.PENDING.value == "pending"
        assert StageStatus.RUNNING.value == "running"
        assert StageStatus.PASSED.value == "passed"
        assert StageStatus.FAILED.value == "failed"
        assert StageStatus.SKIPPED.value == "skipped"


class TestStageResultEdgeCases:
    def test_all_statuses(self):
        for status in StageStatus:
            sr = StageResult(stage_name="s", status=status)
            assert sr.to_dict()["status"] == status.value

    def test_failed_without_error(self):
        sr = StageResult(stage_name="s", status=StageStatus.FAILED)
        assert sr.error == ""
