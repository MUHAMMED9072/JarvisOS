from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.autonomy.build_orchestrator import (
    BuildCancelledError,
    BuildOrchestrator,
    BuildResult,
    BuildStatus,
    CHECKPOINT_DIR,
    Stage,
    StageResult,
)


class TestStageResult:
    def test_to_dict(self):
        sr = StageResult(
            stage=Stage.INTERPRET, status="passed",
            duration_ms=150.0, output={"goal": "test"},
        )
        d = sr.to_dict()
        assert d["stage"] == "interpret"
        assert d["status"] == "passed"
        assert d["has_output"] is True

    def test_to_dict_defaults(self):
        sr = StageResult()
        d = sr.to_dict()
        assert d["has_output"] is False


class TestBuildResult:
    def test_to_dict(self):
        br = BuildResult(
            build_id="b1", request="Build a bot",
            status=BuildStatus.COMPLETED,
            summary="Done", commit_hash="abc123",
            started_at=100.0, completed_at=200.0,
        )
        d = br.to_dict()
        assert d["build_id"] == "b1"
        assert d["duration_s"] == 100.0
        assert d["status"] == "completed"

    def test_to_dict_defaults(self):
        br = BuildResult()
        d = br.to_dict()
        assert d["stages"] == {}


class TestBuildOrchestrator:
    @pytest.fixture
    def orch(self):
        for d in [CHECKPOINT_DIR, "runtime/build_history"]:
            p = Path(d)
            if p.exists():
                for f in p.iterdir():
                    f.unlink(missing_ok=True)
        mock_ai = MagicMock()
        mock_ai.ask.return_value = "Python tool"
        mock_ads = MagicMock()
        mock_ads.run.return_value = MagicMock(to_dict=lambda: {"artifact": "test"})
        mock_sim = MagicMock()
        mock_sim.run.return_value = MagicMock(to_dict=lambda: {"passed": True})
        mock_sandbox = MagicMock()
        mock_sandbox.run_code.return_value = MagicMock(to_dict=lambda: {"passed": True})
        mock_sandbox.run_tests.return_value = MagicMock(to_dict=lambda: {"passed": True})
        return BuildOrchestrator(
            ai_manager=mock_ai,
            ads_pipeline=mock_ads,
            simulation_pipeline=mock_sim,
            sandbox=mock_sandbox,
        )

    def test_health(self, orch):
        assert orch.health()["alive"] is True

    def test_build_empty_orch(self, orch):
        result = orch.build("Build a web scraper")
        assert result.build_id != ""
        assert result.request == "Build a web scraper"
        assert result.status == BuildStatus.COMPLETED
        assert len(result.stages) > 0
        for stage_name, sr in result.stages.items():
            assert sr.status == "passed", f"Stage {stage_name} failed: {sr.error}"

    def test_build_all_stages_present(self, orch):
        result = orch.build("Build a REST API")
        stage_names = {s.value for s in Stage}
        actual = set(result.stages.keys())
        for s in stage_names:
            assert s in actual, f"Missing stage: {s}"

    def test_build_with_ai_manager(self):
        mock_ai = MagicMock()
        mock_ai.ask.return_value = "Python REST API tool"
        orch = BuildOrchestrator(ai_manager=mock_ai)
        result = orch.build("Build an API tool")
        interpret = result.stages.get("interpret")
        assert interpret is not None
        assert interpret.status == "passed"
        assert mock_ai.ask.called

    @staticmethod
    def _fast_mocks(**overrides):
        mock_ai = MagicMock()
        mock_ai.ask.return_value = "Python tool"
        mock_ads = MagicMock()
        mock_ads.run.return_value = MagicMock(to_dict=lambda: {"artifact": "test"})
        mock_sim = MagicMock()
        mock_sim.run.return_value = MagicMock(to_dict=lambda: {"passed": True})
        base = {"ai_manager": mock_ai, "ads_pipeline": mock_ads, "simulation_pipeline": mock_sim}
        base.update(overrides)
        return base

    def test_build_with_memory(self):
        mock_memory = MagicMock()
        mock_memory.search.return_value = []
        orch = BuildOrchestrator(memory=mock_memory, **self._fast_mocks())
        result = orch.build("Build a CLI tool")
        ctx = result.stages.get("context")
        assert ctx is not None
        assert ctx.status == "passed"

    def test_build_with_graph_store(self):
        mock_graph = MagicMock()
        mock_graph.get_entities_by_type.return_value = []
        orch = BuildOrchestrator(graph_store=mock_graph, **self._fast_mocks())
        result = orch.build("Build a test suite")
        ctx = result.stages.get("context")
        assert ctx is not None
        assert ctx.status == "passed"

    def test_build_with_intelligence_pipeline(self):
        mock_intel = MagicMock()
        mock_session = MagicMock()
        mock_session.session_data = {"plan": "task_graph_data"}
        mock_intel.run.return_value = mock_session
        orch = BuildOrchestrator(intelligence_pipeline=mock_intel, **self._fast_mocks())
        result = orch.build("Build a notification system")
        plan = result.stages.get("plan")
        assert plan is not None
        assert plan.status == "passed"
        assert mock_intel.run.called

    def test_build_with_agent_registry(self):
        mock_reg = MagicMock()
        mock_agent = MagicMock()
        mock_agent.agent_id = "agent_1"
        mock_agent.name = "DevAgent"
        mock_reg.list.return_value = [mock_agent]
        orch = BuildOrchestrator(agent_registry=mock_reg, **self._fast_mocks())
        result = orch.build("Build with agents")
        agent_s = result.stages.get("agent_select")
        assert agent_s is not None
        assert agent_s.status == "passed"

    def test_build_with_tool_registry(self):
        mock_reg = MagicMock()
        mock_tool = MagicMock()
        mock_tool.name = "python_tool"
        mock_reg.list_tools.return_value = [mock_tool]
        orch = BuildOrchestrator(tool_registry=mock_reg, **self._fast_mocks())
        result = orch.build("Build with tools")
        tool_s = result.stages.get("tool_select")
        assert tool_s is not None
        assert tool_s.status == "passed"

    def test_build_with_ads_pipeline(self):
        mock_ads = MagicMock()
        mock_report = MagicMock()
        mock_report.to_dict.return_value = {"artifact": "test"}
        mock_ads.run.return_value = mock_report
        orch = BuildOrchestrator(**self._fast_mocks(ads_pipeline=mock_ads))
        result = orch.build("Build via ADS")
        ads_s = result.stages.get("ads_generate")
        assert ads_s is not None
        assert ads_s.status == "passed"

    def test_build_with_sandbox(self):
        mock_sandbox = MagicMock()
        mock_sandbox.run_code.return_value = MagicMock()
        mock_sandbox.run_code.return_value.to_dict.return_value = {"passed": True}
        orch = BuildOrchestrator(**self._fast_mocks(), sandbox=mock_sandbox)
        result = orch.build("Build and sandbox")
        sandbox_s = result.stages.get("sandbox")
        assert sandbox_s is not None
        assert sandbox_s.status == "passed"

    def test_build_with_simulation(self):
        mock_sim = MagicMock()
        mock_report = MagicMock()
        mock_report.to_dict.return_value = {"passed": True}
        mock_sim.run.return_value = mock_report
        orch = BuildOrchestrator(**self._fast_mocks(simulation_pipeline=mock_sim))
        result = orch.build("Build and simulate")
        sim_s = result.stages.get("simulate")
        assert sim_s is not None
        assert sim_s.status == "passed"

    def test_build_with_governance(self):
        mock_gov = MagicMock()
        mock_decision = MagicMock()
        mock_decision.to_dict.return_value = {"approved": True}
        mock_gov.evaluate.return_value = mock_decision
        orch = BuildOrchestrator(governance=mock_gov, **self._fast_mocks())
        result = orch.build("Build with governance")
        gov_s = result.stages.get("govern")
        assert gov_s is not None
        assert gov_s.status == "passed"

    def test_build_with_git_tool_execute(self):
        mock_git = MagicMock()
        mock_result = MagicMock()
        mock_result.output = "abc123def"
        mock_git.execute.return_value = mock_result
        orch = BuildOrchestrator(git_tool=mock_git, **self._fast_mocks())
        result = orch.build("Build with git commit")
        git_s = result.stages.get("git_commit")
        assert git_s is not None
        assert git_s.status == "passed"

    def test_build_with_git_tool_callable(self):
        def fake_git(action: str, **kwargs: str) -> str:
            return "abc123"
        orch = BuildOrchestrator(git_tool=fake_git, **self._fast_mocks())
        result = orch.build("Build with callable git")
        git_s = result.stages.get("git_commit")
        assert git_s is not None
        assert git_s.status == "passed"

    def test_build_with_all_components(self):
        mock_ai = MagicMock()
        mock_ai.ask.return_value = "Python tool"
        mock_memory = MagicMock()
        mock_memory.search.return_value = []
        mock_graph = MagicMock()
        mock_graph.get_entities_by_type.return_value = []
        mock_intel = MagicMock()
        mock_intel.run.return_value = MagicMock(session_data={"plan": "plan_data"})
        mock_agent_reg = MagicMock()
        mock_agent_reg.list.return_value = [MagicMock(agent_id="a1", name="Dev")]
        mock_tool_reg = MagicMock()
        mock_tool_reg.list_tools.return_value = [MagicMock(name="py_tool")]
        mock_ads = MagicMock()
        mock_ads.run.return_value = MagicMock(to_dict=lambda: {"artifact": "test"})
        mock_sandbox = MagicMock()
        mock_sandbox.run_code.return_value = MagicMock(to_dict=lambda: {"passed": True})
        mock_sim = MagicMock()
        mock_sim.run.return_value = MagicMock(to_dict=lambda: {"passed": True})
        mock_gov = MagicMock()
        mock_gov.evaluate.return_value = MagicMock(to_dict=lambda: {"approved": True})
        mock_git = MagicMock()
        mock_git.execute.return_value = MagicMock(output="abc123")
        mock_bus = MagicMock()

        orch = BuildOrchestrator(
            ai_manager=mock_ai,
            memory=mock_memory,
            graph_store=mock_graph,
            intelligence_pipeline=mock_intel,
            ads_pipeline=mock_ads,
            simulation_pipeline=mock_sim,
            governance=mock_gov,
            agent_registry=mock_agent_reg,
            tool_registry=mock_tool_reg,
            git_tool=mock_git,
            sandbox=mock_sandbox,
            event_bus=mock_bus,
        )
        result = orch.build("Build a complete feature")
        assert result.status == BuildStatus.COMPLETED
        assert mock_ai.ask.called
        assert mock_memory.search.called
        assert mock_graph.get_entities_by_type.called
        assert mock_intel.run.called
        assert mock_ads.run.called
        assert mock_bus.publish.called
        git_s = result.stages.get("git_commit")
        assert git_s is not None
        assert git_s.status == "passed"

    # ── Lookup / listing / statistics ──────────────────────────────

    def test_get_build(self, orch):
        result = orch.build("Build a scraper")
        retrieved = orch.get_build(result.build_id)
        assert retrieved is not None
        assert retrieved.build_id == result.build_id

    def test_get_build_not_found(self, orch):
        assert orch.get_build("nonexistent") is None

    def test_list_builds(self, orch):
        orch.build("Build A")
        orch.build("Build B")
        assert len(orch.list_builds()) == 2

    def test_statistics(self, orch):
        orch.build("Build A")
        orch.build("Build B")
        stats = orch.get_statistics()
        assert stats["total_builds"] == 2
        assert stats["successful"] == 2
        assert stats["success_rate"] == 100.0

    def test_build_with_event_bus(self):
        mock_bus = MagicMock()
        orch = BuildOrchestrator(event_bus=mock_bus, **self._fast_mocks())
        orch.build("Build with events")
        assert mock_bus.publish.called

    # ── Async build ────────────────────────────────────────────────

    def test_build_async(self, orch):
        build_id = orch.build_async("Async build")
        assert build_id != ""
        time.sleep(1.5)
        result = orch.get_build(build_id)
        assert result is not None
        assert result.status == BuildStatus.COMPLETED

    def test_cancel_build(self, orch):
        build_id = orch.build_async("Cancellable build")
        assert orch.cancel_build(build_id) is True
        time.sleep(3.0)
        result = orch.get_build(build_id)
        assert result is not None
        assert result.status in (BuildStatus.CANCELLED, BuildStatus.COMPLETED)

    def test_cancel_build_not_found(self, orch):
        assert orch.cancel_build("nonexistent") is False

    # ── Search builds ──────────────────────────────────────────────

    def test_search_builds(self, orch):
        orch.build("Build a REST API")
        orch.build("Build a CLI tool")
        results = orch.search_builds(query="REST")
        assert len(results) == 1

    def test_search_builds_by_status(self, orch):
        orch.build("Normal build")
        results = orch.search_builds(status="completed")
        assert len(results) == 1

    def test_search_builds_empty(self, orch):
        assert orch.search_builds(query="nonexistent") == []

    # ── Checkpoint / resume ────────────────────────────────────────

    def test_list_checkpoints_empty(self):
        assert BuildOrchestrator.list_checkpoints() == []

    def test_checkpoint_created_during_build(self, orch):
        orch.build("Checkpoint test")
        cps = BuildOrchestrator.list_checkpoints()
        assert len(cps) >= 1
        cp = cps[0]
        assert "checkpoint_id" in cp
        assert cp["stages_completed"] > 0

    def test_build_resume_from_checkpoint(self, orch):
        first = orch.build("Resumable build")
        assert first.status == BuildStatus.COMPLETED
        cps = BuildOrchestrator.list_checkpoints()
        assert len(cps) >= 1
        resume_id = cps[0]["checkpoint_id"]
        resumed = orch.build("Resumable build", checkpoint_id=resume_id)
        assert resumed.status == BuildStatus.COMPLETED
        assert resumed.request == "Resumable build"

    # ── Build history persistence ──────────────────────────────────

    def test_build_history_saved(self, orch):
        orch.build("History build")
        history_dir = Path("runtime/build_history")
        json_files = list(history_dir.glob("*.json"))
        assert len(json_files) >= 1
        data = json.loads(json_files[0].read_text(encoding="utf-8"))
        assert data["request"] == "History build"
        assert data["status"] == "completed"

    def test_build_history_loaded_on_restart(self, orch):
        orch.build("Persisted build")
        new_orch = BuildOrchestrator(**self._fast_mocks())
        builds = new_orch.list_builds()
        assert len(builds) >= 1
        match = [b for b in builds if b.request == "Persisted build"]
        assert len(match) == 1

    # ── Retry logic ────────────────────────────────────────────────

    def test_retry_on_transient_failure(self):
        call_count = [0]

        def flaky_interpret(result, request):
            call_count[0] += 1
            if call_count[0] < 3:
                raise ValueError("transient error")
            return {"goal": request, "raw": "ok", "artifact_type": "auto"}

        class FlakyOrch(BuildOrchestrator):
            def __init__(self):
                super().__init__(**TestBuildOrchestrator._fast_mocks())

            def _interpret(self, request):
                return flaky_interpret(None, request)

        orch = FlakyOrch()
        result = orch.build("Retry test")
        assert result.status == BuildStatus.COMPLETED
        assert call_count[0] == 3

    def test_retry_exhausted_fails(self):
        call_count = [0]

        def always_fail(result, request):
            call_count[0] += 1
            raise ValueError("persistent error")

        class FailingOrch(BuildOrchestrator):
            def __init__(self):
                super().__init__(**TestBuildOrchestrator._fast_mocks())

            def _interpret(self, request):
                return always_fail(None, request)

        orch = FailingOrch()
        result = orch.build("Fail test")
        assert result.status == BuildStatus.FAILED
        interpret_s = result.stages.get("interpret")
        assert interpret_s is not None
        assert interpret_s.status == "failed"
        assert "persistent error" in interpret_s.error
        assert call_count[0] == 3

    # ── Edge cases ─────────────────────────────────────────────────

    def test_build_empty_request(self, orch):
        result = orch.build("")
        assert result.status == BuildStatus.COMPLETED

    def test_build_long_request(self, orch):
        long_req = "Build " + "x" * 5000
        result = orch.build(long_req)
        assert result.status == BuildStatus.COMPLETED

    def test_build_cancelled_during_stages(self, orch):
        class SlowInterpretOrch(BuildOrchestrator):
            def __init__(self):
                super().__init__(**TestBuildOrchestrator._fast_mocks())

            def _interpret(self, request):
                time.sleep(2.0)
                return {"goal": request, "raw": "ok", "artifact_type": "auto"}

        orch = SlowInterpretOrch()
        build_id = orch.build_async("Slow build")
        time.sleep(0.2)
        orch.cancel_build(build_id)
        time.sleep(3.0)
        result = orch.get_build(build_id)
        assert result is not None
        assert result.status == BuildStatus.CANCELLED

    def test_stage_result_duration(self, orch):
        result = orch.build("Duration test")
        for sr in result.stages.values():
            assert sr.duration_ms >= 0
