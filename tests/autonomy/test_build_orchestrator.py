from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.autonomy.build_orchestrator import (
    BuildOrchestrator,
    BuildResult,
    BuildStatus,
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
        return BuildOrchestrator()

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

    def test_build_with_memory(self):
        mock_memory = MagicMock()
        mock_memory.search.return_value = []
        orch = BuildOrchestrator(memory=mock_memory)
        result = orch.build("Build a CLI tool")
        ctx = result.stages.get("context")
        assert ctx is not None
        assert ctx.status == "passed"

    def test_build_with_graph_store(self):
        mock_graph = MagicMock()
        mock_graph.get_entities_by_type.return_value = []
        orch = BuildOrchestrator(graph_store=mock_graph)
        result = orch.build("Build a test suite")
        ctx = result.stages.get("context")
        assert ctx is not None
        assert ctx.status == "passed"

    def test_build_with_intelligence_pipeline(self):
        mock_pipeline = MagicMock()
        mock_result = MagicMock()
        mock_result.task_graph = "task_graph_data"
        mock_pipeline.run.return_value = mock_result
        orch = BuildOrchestrator(intelligence_pipeline=mock_pipeline)
        result = orch.build("Build a notification system")
        plan = result.stages.get("plan")
        assert plan is not None
        assert plan.status == "passed"
        assert mock_pipeline.run.called

    def test_build_with_agent_registry(self):
        mock_reg = MagicMock()
        mock_agent = MagicMock()
        mock_agent.agent_id = "agent_1"
        mock_agent.name = "DevAgent"
        mock_reg.list_agents.return_value = [mock_agent]
        orch = BuildOrchestrator(agent_registry=mock_reg)
        result = orch.build("Build with agents")
        agent_s = result.stages.get("agent_select")
        assert agent_s is not None
        assert agent_s.status == "passed"

    def test_build_with_tool_registry(self):
        mock_reg = MagicMock()
        mock_tool = MagicMock()
        mock_tool.name = "python_tool"
        mock_reg.list_tools.return_value = [mock_tool]
        orch = BuildOrchestrator(tool_registry=mock_reg)
        result = orch.build("Build with tools")
        tool_s = result.stages.get("tool_select")
        assert tool_s is not None
        assert tool_s.status == "passed"

    def test_build_with_ads_pipeline(self):
        mock_ads = MagicMock()
        mock_ads.run.return_value = MagicMock()
        mock_ads.run.return_value.to_dict.return_value = {"artifact": "test"}
        orch = BuildOrchestrator(ads_pipeline=mock_ads)
        result = orch.build("Build via ADS")
        ads_s = result.stages.get("ads_generate")
        assert ads_s is not None
        assert ads_s.status == "passed"

    def test_build_with_sandbox(self):
        mock_sandbox = MagicMock()
        mock_sandbox.execute.return_value = MagicMock()
        mock_sandbox.execute.return_value.to_dict.return_value = {"passed": True}
        orch = BuildOrchestrator(sandbox=mock_sandbox)
        result = orch.build("Build and sandbox")
        sandbox_s = result.stages.get("sandbox")
        assert sandbox_s is not None
        assert sandbox_s.status == "passed"

    def test_build_with_simulation(self):
        mock_sim = MagicMock()
        mock_sim.run.return_value = MagicMock()
        mock_sim.run.return_value.to_dict.return_value = {"pass": True}
        orch = BuildOrchestrator(simulation_pipeline=mock_sim)
        result = orch.build("Build and simulate")
        sim_s = result.stages.get("simulate")
        assert sim_s is not None
        assert sim_s.status == "passed"

    def test_build_with_governance(self):
        mock_gov = MagicMock()
        mock_gov.evaluate.return_value = MagicMock()
        mock_gov.evaluate.return_value.to_dict.return_value = {"approved": True}
        orch = BuildOrchestrator(governance=mock_gov)
        result = orch.build("Build with governance")
        gov_s = result.stages.get("govern")
        assert gov_s is not None
        assert gov_s.status == "passed"

    def test_build_with_git_tool(self):
        mock_git = MagicMock()
        mock_git.commit.return_value = MagicMock()
        mock_git.commit.return_value.hash = "abc123def"
        orch = BuildOrchestrator(git_tool=mock_git)
        result = orch.build("Build with git commit")
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
        mock_pipeline = MagicMock()
        mock_pipeline.run.return_value = MagicMock(task_graph="plan")
        mock_reg = MagicMock()
        mock_reg.list_agents.return_value = []
        mock_reg.list_tools.return_value = []
        mock_ads = MagicMock()
        mock_ads.run.return_value = MagicMock()
        mock_ads.run.return_value.to_dict.return_value = {"artifact": "test"}
        mock_sandbox = MagicMock()
        mock_sandbox.execute.return_value = MagicMock()
        mock_sandbox.execute.return_value.to_dict.return_value = {"passed": True}
        mock_sim = MagicMock()
        mock_sim.run.return_value = MagicMock()
        mock_sim.run.return_value.to_dict.return_value = {"pass": True}
        mock_gov = MagicMock()
        mock_gov.evaluate.return_value = MagicMock()
        mock_gov.evaluate.return_value.to_dict.return_value = {"approved": True}
        # git_tool as a simple object with commit() method
        class FakeGit:
            def commit(self, message: str = "") -> Any:
                r = MagicMock()
                r.hash = "abc123"
                return r
        mock_git = FakeGit()
        mock_bus = MagicMock()

        orch = BuildOrchestrator(
            ai_manager=mock_ai,
            memory=mock_memory,
            graph_store=mock_graph,
            intelligence_pipeline=mock_pipeline,
            ads_pipeline=mock_ads,
            simulation_pipeline=mock_sim,
            governance=mock_gov,
            agent_registry=mock_reg,
            tool_registry=mock_reg,
            git_tool=mock_git,
            sandbox=mock_sandbox,
            event_bus=mock_bus,
        )
        result = orch.build("Build a complete feature")
        assert result.status == BuildStatus.COMPLETED
        assert mock_ai.ask.called
        assert mock_memory.search.called
        assert mock_graph.get_entities_by_type.called
        assert mock_pipeline.run.called
        assert mock_ads.run.called
        assert mock_bus.publish.called
        git_s = result.stages.get("git_commit")
        assert git_s is not None
        assert git_s.status == "passed"

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
        orch = BuildOrchestrator(event_bus=mock_bus)
        orch.build("Build with events")
        assert mock_bus.publish.called

    def test_build_with_project_manager(self):
        mock_pm = MagicMock()
        mock_pm._generate_report.return_value = None
        orch = BuildOrchestrator(project_manager=mock_pm)
        result = orch.build("Build with PM")
        assert result.status == BuildStatus.COMPLETED
