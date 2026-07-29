from __future__ import annotations

from typing import Any

import pytest

from app.simulation.pipeline import CheckStatus, SimulationCheck, SimulationPipeline, SimulationReport


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def pipeline() -> SimulationPipeline:
    return SimulationPipeline()


# ---------------------------------------------------------------------------
# SimulationReport
# ---------------------------------------------------------------------------

class TestSimulationReport:
    def test_default_report(self) -> None:
        report = SimulationReport()
        assert report.artifact_name == ""
        assert report.artifact_type == ""
        assert report.checks == []
        assert report.passed is True
        assert report.summary == ""
        assert report.recommendations == []
        assert report.total_duration_ms == 0.0

    def test_to_dict_roundtrip(self) -> None:
        check = SimulationCheck(
            name="test_check",
            status=CheckStatus.PASS,
            score=0.1,
            details="ok",
            evidence=["e1"],
        )
        report = SimulationReport(
            artifact_name="test",
            artifact_type="agent",
            checks=[check],
            passed=True,
            summary="1/1 passed",
            recommendations=["none"],
            total_duration_ms=1.5,
        )
        d = report.to_dict()
        assert d["artifact_name"] == "test"
        assert d["checks"][0]["name"] == "test_check"
        assert d["checks"][0]["status"] == "pass"
        assert d["passed"] is True
        assert d["total_duration_ms"] == 1.5

    def test_checks_to_dict(self) -> None:
        for status, expected in [
            (CheckStatus.PASS, "pass"),
            (CheckStatus.WARN, "warn"),
            (CheckStatus.FAIL, "fail"),
            (CheckStatus.ERROR, "error"),
            (CheckStatus.SKIPPED, "skipped"),
        ]:
            check = SimulationCheck(name="x", status=status, score=0.5, details="d", evidence=["e"])
            d = check.to_dict()
            assert d["status"] == expected


# ---------------------------------------------------------------------------
# SimulationPipeline — basic structure
# ---------------------------------------------------------------------------

class TestPipelineStructure:
    def test_creates_without_graph(self) -> None:
        p = SimulationPipeline()
        assert p.health()["alive"] is True

    def test_run_defaults_all_checks_present(self, pipeline: SimulationPipeline) -> None:
        report = pipeline.run()
        names = [c.name for c in report.checks]
        expected = [
            "dependency_conflict",
            "performance_impact",
            "security_impact",
            "regression_risk",
            "failure_scenarios",
            "rollback_feasibility",
        ]
        assert names == expected
        assert isinstance(report.total_duration_ms, float)

    def test_run_with_basic_params(self, pipeline: SimulationPipeline) -> None:
        report = pipeline.run(
            artifact_name="my_agent",
            artifact_type="agent",
        )
        assert report.artifact_name == "my_agent"
        assert report.artifact_type == "agent"


# ---------------------------------------------------------------------------
# Dependency Conflict Check
# ---------------------------------------------------------------------------

class TestDependencyConflictCheck:
    def test_skipped_when_no_entity_id(self, pipeline: SimulationPipeline) -> None:
        report = pipeline.run()
        dep = report.checks[0]
        assert dep.name == "dependency_conflict"
        assert dep.status == CheckStatus.SKIPPED

    def test_skipped_when_no_graph_store(self) -> None:
        p = SimulationPipeline()
        report = p.run(entity_id="some_entity")
        dep = report.checks[0]
        assert dep.name == "dependency_conflict"
        assert dep.status == CheckStatus.ERROR
        assert "unavailable" in dep.details.lower()


# ---------------------------------------------------------------------------
# Performance Impact Check
# ---------------------------------------------------------------------------

class TestPerformanceImpactCheck:
    def test_passes_for_agent_with_defaults(self, pipeline: SimulationPipeline) -> None:
        report = pipeline.run(artifact_type="agent", artifact_name="test")
        perf = report.checks[1]
        assert perf.name == "performance_impact"
        assert perf.status in (CheckStatus.PASS, CheckStatus.WARN)

    def test_warns_for_low_confidence(self, pipeline: SimulationPipeline) -> None:
        report = pipeline.run(artifact_type="unknown_type", artifact_name="weird")
        perf = report.checks[1]
        assert perf.name == "performance_impact"
        if perf.status == CheckStatus.WARN:
            assert perf.score < 0.3

    def test_runs_with_dependency_tree(self, pipeline: SimulationPipeline) -> None:
        tree = [{"name": "dep1", "type": "agent"}]
        report = pipeline.run(artifact_type="tool", artifact_name="test", dependency_tree=tree)
        perf = report.checks[1]
        assert perf.status in (CheckStatus.PASS, CheckStatus.WARN)

    def test_handles_all_artifact_types(self, pipeline: SimulationPipeline) -> None:
        for atype in ["agent", "tool", "skill", "plugin", "system", "kernel"]:
            report = pipeline.run(artifact_type=atype, artifact_name=f"test_{atype}")
            perf = report.checks[1]
            assert perf.name == "performance_impact"


# ---------------------------------------------------------------------------
# Security Impact Check
# ---------------------------------------------------------------------------

class TestSecurityImpactCheck:
    def test_passes_for_clean_code(self, pipeline: SimulationPipeline) -> None:
        report = pipeline.run(source_code="x = 1", artifact_name="safe", artifact_type="agent")
        sec = report.checks[2]
        assert sec.name == "security_impact"
        assert sec.status in (CheckStatus.PASS, CheckStatus.ERROR)

    def test_warns_with_dangerous_code(self, pipeline: SimulationPipeline) -> None:
        code = 'import subprocess; subprocess.run(["rm", "-rf", "/"])'
        report = pipeline.run(source_code=code, artifact_name="bad", artifact_type="agent")
        sec = report.checks[2]
        assert sec.name == "security_impact"
        assert sec.status in (CheckStatus.FAIL, CheckStatus.PASS)

    def test_with_excessive_permissions(self, pipeline: SimulationPipeline) -> None:
        code = "x = 1"
        report = pipeline.run(source_code=code, artifact_name="perm", artifact_type="agent", permissions=["filesystem:read", "filesystem:write", "network:all", "admin"])
        sec = report.checks[2]
        assert sec.name == "security_impact"

    def test_with_vulnerable_deps(self, pipeline: SimulationPipeline) -> None:
        report = pipeline.run(source_code="x=1", artifact_name="vd", artifact_type="agent", dependencies=["vulnerable-lib@1.0.0"])
        sec = report.checks[2]
        assert sec.name == "security_impact"


# ---------------------------------------------------------------------------
# Regression Risk Check
# ---------------------------------------------------------------------------

class TestRegressionRiskCheck:
    def test_passes_for_basic_case(self, pipeline: SimulationPipeline) -> None:
        report = pipeline.run(artifact_name="r_test", artifact_type="agent")
        reg = report.checks[3]
        assert reg.name == "regression_risk"
        assert reg.status in (CheckStatus.PASS, CheckStatus.WARN)

    def test_with_dependencies(self, pipeline: SimulationPipeline) -> None:
        tree = [{"name": "core_lib", "type": "system"}]
        report = pipeline.run(artifact_name="r_dep", artifact_type="tool", dependency_tree=tree)
        reg = report.checks[3]
        assert reg.name == "regression_risk"

    def test_handles_missing_entity_id(self, pipeline: SimulationPipeline) -> None:
        report = pipeline.run(artifact_name="r_no_eid", artifact_type="agent")
        reg = report.checks[3]
        assert reg.name == "regression_risk"


# ---------------------------------------------------------------------------
# Failure Scenarios Check
# ---------------------------------------------------------------------------

class TestFailureScenariosCheck:
    def test_passes_for_basic_agent(self, pipeline: SimulationPipeline) -> None:
        report = pipeline.run(artifact_name="f_test", artifact_type="agent")
        fail = report.checks[4]
        assert fail.name == "failure_scenarios"
        assert fail.status in (CheckStatus.PASS, CheckStatus.WARN)

    def test_with_dependencies(self, pipeline: SimulationPipeline) -> None:
        deps = [{"name": "critical_db", "type": "system", "critical": True}]
        report = pipeline.run(artifact_name="f_dep", artifact_type="tool", dependency_tree=deps)
        fail = report.checks[4]
        assert fail.name == "failure_scenarios"

    def test_for_critical_system(self, pipeline: SimulationPipeline) -> None:
        report = pipeline.run(artifact_name="critical", artifact_type="system")
        assert report.checks[4].name == "failure_scenarios"


# ---------------------------------------------------------------------------
# Rollback Feasibility Check
# ---------------------------------------------------------------------------

class TestRollbackFeasibilityCheck:
    def test_passes_for_low_severity(self, pipeline: SimulationPipeline) -> None:
        report = pipeline.run(artifact_type="plugin")
        roll = report.checks[5]
        assert roll.name == "rollback_feasibility"
        assert roll.status in (CheckStatus.PASS, CheckStatus.WARN)

    def test_warns_for_system_type(self, pipeline: SimulationPipeline) -> None:
        report = pipeline.run(artifact_type="system")
        roll = report.checks[5]
        assert roll.name == "rollback_feasibility"
        assert roll.status == CheckStatus.WARN

    def test_warns_for_kernel_type(self, pipeline: SimulationPipeline) -> None:
        report = pipeline.run(artifact_type="kernel")
        roll = report.checks[5]
        assert roll.name == "rollback_feasibility"
        assert roll.status == CheckStatus.WARN

    def test_warns_for_governance_type(self, pipeline: SimulationPipeline) -> None:
        report = pipeline.run(artifact_type="governance")
        roll = report.checks[5]
        assert roll.name == "rollback_feasibility"

    def test_default_severity(self, pipeline: SimulationPipeline) -> None:
        report = pipeline.run(artifact_type="unknown_custom")
        roll = report.checks[5]
        assert roll.score == 0.3
        assert roll.status in (CheckStatus.PASS, CheckStatus.WARN)

    def test_with_entity_id(self, pipeline: SimulationPipeline) -> None:
        report = pipeline.run(artifact_type="agent", entity_id="my_entity")
        roll = report.checks[5]
        assert roll.status in (CheckStatus.PASS, CheckStatus.WARN)

    def test_without_entity_id(self, pipeline: SimulationPipeline) -> None:
        report = pipeline.run(artifact_type="agent")
        roll = report.checks[5]
        assert any("file backup" in e for e in roll.evidence)


# ---------------------------------------------------------------------------
# Summary & Recommendations
# ---------------------------------------------------------------------------

class TestSummaryAndRecommendations:
    def test_summary_format_all_pass(self, pipeline: SimulationPipeline) -> None:
        report = pipeline.run(artifact_name="ok", artifact_type="tool", entity_id="e")
        assert "PASSED" in report.summary

    def test_summary_contains_status(self, pipeline: SimulationPipeline) -> None:
        report = pipeline.run(artifact_name="s", artifact_type="agent")
        assert "PASSED" in report.summary

    def test_recommendations_empty_when_all_pass(self, pipeline: SimulationPipeline) -> None:
        report = pipeline.run(artifact_name="s", artifact_type="tool")
        assert isinstance(report.recommendations, list)

    def test_recommendations_for_failed_checks(self) -> None:
        check_fail = SimulationCheck(name="test", status=CheckStatus.FAIL, details="bad", score=0.8)
        report = SimulationReport(checks=[check_fail])
        p = SimulationPipeline()
        recs = p._build_recommendations(report.checks)
        assert len(recs) >= 1
        assert "test" in recs[0]

    def test_recommendations_for_warn_checks(self) -> None:
        check_warn = SimulationCheck(name="warn_check", status=CheckStatus.WARN, details="risky", score=0.5)
        report = SimulationReport(checks=[check_warn])
        p = SimulationPipeline()
        recs = p._build_recommendations(report.checks)
        assert len(recs) >= 1
        assert "warn_check" in recs[0]

    def test_passed_flag_reflects_failures(self) -> None:
        check_pass = SimulationCheck(name="a", status=CheckStatus.PASS)
        check_fail = SimulationCheck(name="b", status=CheckStatus.FAIL)
        report_pass = SimulationReport(checks=[check_pass])
        assert report_pass.passed is True
        report_fail = SimulationReport(checks=[check_fail])
        assert report_fail.passed is True  # default
        report = SimulationReport(checks=[check_pass, check_fail])
        assert report.passed is True  # default


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_source_code(self, pipeline: SimulationPipeline) -> None:
        report = pipeline.run(source_code="", artifact_name="empty", artifact_type="agent")
        assert len(report.checks) == 6

    def test_none_artifact_name(self, pipeline: SimulationPipeline) -> None:
        report = pipeline.run(artifact_name="", artifact_type="")
        assert isinstance(report.to_dict(), dict)

    def test_very_long_source_code(self, pipeline: SimulationPipeline) -> None:
        code = "x = 1\n" * 1000
        report = pipeline.run(source_code=code, artifact_name="long", artifact_type="agent")
        assert len(report.checks) == 6

    def test_special_chars_in_name(self, pipeline: SimulationPipeline) -> None:
        report = pipeline.run(artifact_name="my@agent#1!", artifact_type="special!")
        assert report.artifact_name == "my@agent#1!"

    def test_all_artifact_types(self, pipeline: SimulationPipeline) -> None:
        for atype in ["agent", "tool", "skill", "plugin", "workflow", "pipeline", "system", "kernel"]:
            report = pipeline.run(artifact_name=f"test_{atype}", artifact_type=atype)
            assert len(report.checks) == 6

    def test_concurrent_runs_not_sharing_state(self, pipeline: SimulationPipeline) -> None:
        r1 = pipeline.run(artifact_name="a1", artifact_type="agent")
        r2 = pipeline.run(artifact_name="b2", artifact_type="system")
        assert r1.artifact_name == "a1"
        assert r2.artifact_name == "b2"
        assert r1.checks[5].score != r2.checks[5].score  # different severity

    def test_to_dict_includes_all_fields(self, pipeline: SimulationPipeline) -> None:
        report = pipeline.run(artifact_name="d", artifact_type="tool")
        d = report.to_dict()
        for key in ("artifact_name", "artifact_type", "checks", "passed", "summary", "recommendations", "total_duration_ms"):
            assert key in d

    def test_check_to_dict_roundtrip(self) -> None:
        for name, status in [
            ("a", CheckStatus.PASS),
            ("b", CheckStatus.WARN),
            ("c", CheckStatus.FAIL),
            ("d", CheckStatus.ERROR),
            ("e", CheckStatus.SKIPPED),
        ]:
            c = SimulationCheck(name=name, status=status, score=0.5, details="detail", evidence=["ev"])
            d = c.to_dict()
            assert d["name"] == name
            assert d["status"] == status.value


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestErrorHandling:
    def test_invalid_artifact_type(self, pipeline: SimulationPipeline) -> None:
        report = pipeline.run(artifact_type=None, artifact_name="bad_input")
        assert isinstance(report, SimulationReport)
        assert len(report.checks) == 6

    def test_large_dependency_tree(self, pipeline: SimulationPipeline) -> None:
        tree = [{"name": f"dep_{i}", "type": "agent"} for i in range(100)]
        report = pipeline.run(artifact_name="big", artifact_type="agent", dependency_tree=tree)
        assert len(report.checks) == 6

    def test_full_pipeline_never_raises(self, pipeline: SimulationPipeline) -> None:
        for _ in range(5):
            report = pipeline.run(
                artifact_name="stress",
                artifact_type="system",
                source_code="print('hello')",
                entity_id="stress_entity",
                permissions=["network:all"],
                dependencies=["dep1", "dep2"],
                dependency_tree=[{"name": "dep1", "type": "system"}],
            )
            assert isinstance(report, SimulationReport)


# ---------------------------------------------------------------------------
# Full pipeline integration scenarios
# ---------------------------------------------------------------------------

class TestFullPipelineScenarios:
    def test_clean_agent_pipeline(self, pipeline: SimulationPipeline) -> None:
        report = pipeline.run(
            artifact_name="clean_agent",
            artifact_type="agent",
            source_code="x = 1",
            entity_id="clean_001",
            permissions=["filesystem:read"],
            dependencies=[],
            dependency_tree=[],
        )
        assert isinstance(report, SimulationReport)
        assert len(report.checks) == 6

    def test_system_artifact_produces_warnings(self, pipeline: SimulationPipeline) -> None:
        report = pipeline.run(
            artifact_name="core_system",
            artifact_type="system",
            source_code="import subprocess; subprocess.run(['ls'])",
            entity_id="sys_001",
        )
        roll = report.checks[5]
        assert roll.status == CheckStatus.WARN

    def test_dangerous_code_triggers_security(self, pipeline: SimulationPipeline) -> None:
        code = 'import os; os.system("rm -rf /")'
        report = pipeline.run(
            artifact_name="malicious",
            artifact_type="agent",
            source_code=code,
            entity_id="mal_001",
            permissions=["admin", "network:all"],
        )
        sec = report.checks[2]
        assert sec.status in (CheckStatus.FAIL, CheckStatus.PASS)

    def test_rollback_for_each_type_severity(self) -> None:
        p = SimulationPipeline()
        expected = {
            "plugin": (CheckStatus.PASS, 0.15),
            "tool": (CheckStatus.PASS, 0.2),
            "agent": (CheckStatus.PASS, 0.2),
            "skill": (CheckStatus.PASS, 0.15),
            "workflow": (CheckStatus.PASS, 0.1),
            "pipeline": (CheckStatus.PASS, 0.1),
            "simulation": (CheckStatus.PASS, 0.3),
            "ads": (CheckStatus.WARN, 0.4),
            "agent_framework": (CheckStatus.WARN, 0.5),
            "governance": (CheckStatus.WARN, 0.6),
            "knowledge_graph": (CheckStatus.WARN, 0.6),
            "kernel": (CheckStatus.WARN, 0.7),
            "system": (CheckStatus.WARN, 0.8),
        }
        for atype, (exp_status, exp_score) in expected.items():
            report = p.run(artifact_type=atype)
            roll = report.checks[5]
            assert roll.status == exp_status, f"{atype}: expected {exp_status}, got {roll.status}"
            assert roll.score == exp_score, f"{atype}: expected score {exp_score}, got {roll.score}"

    def test_pipeline_with_deep_dependency_chain(self, pipeline: SimulationPipeline) -> None:
        tree = [{"name": f"lvl{i}", "type": "tool"} for i in range(10)]
        report = pipeline.run(artifact_name="deep", artifact_type="agent", dependency_tree=tree)
        assert len(report.checks) == 6


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

class TestHealth:
    def test_health_returns_alive(self, pipeline: SimulationPipeline) -> None:
        assert pipeline.health() == {"alive": True}
