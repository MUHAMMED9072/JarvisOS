from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.autonomy.orchestrator import (
    AgentRole,
    AgentTeam,
    ConflictRecord,
    ConflictSeverity,
    Workflow,
    WorkflowOrchestrator,
    WorkflowStatus,
    WorkflowStep,
)


class TestAgentTeam:
    def test_to_dict(self):
        t = AgentTeam(team_id="t1", name="Team A", objective="Build X")
        d = t.to_dict()
        assert d["name"] == "Team A"
        assert d["objective"] == "Build X"

    def test_to_dict_defaults(self):
        t = AgentTeam()
        d = t.to_dict()
        assert d["members"] == []


class TestWorkflowStep:
    def test_to_dict(self):
        s = WorkflowStep(
            step_id="s1", name="Step 1", assigned_agent="agent_a",
            role="lead", status="running",
        )
        d = s.to_dict()
        assert d["assigned_agent"] == "agent_a"
        assert d["role"] == "lead"

    def test_to_dict_defaults(self):
        s = WorkflowStep()
        d = s.to_dict()
        assert d["depends_on"] == []
        assert d["result"] == {}


class TestWorkflow:
    def test_to_dict(self):
        w = Workflow(
            workflow_id="w1", name="Test Workflow",
            status=WorkflowStatus.RUNNING,
        )
        d = w.to_dict()
        assert d["status"] == "running"

    def test_to_dict_defaults(self):
        w = Workflow()
        d = w.to_dict()
        assert d["steps"] == []


class TestConflictRecord:
    def test_to_dict(self):
        c = ConflictRecord(
            conflict_id="c1", workflow_id="w1",
            between_agents=["a", "b"],
            description="Resource contention",
            severity=ConflictSeverity.HIGH,
        )
        d = c.to_dict()
        assert d["severity"] == "high"
        assert d["description"] == "Resource contention"

    def test_to_dict_defaults(self):
        c = ConflictRecord()
        d = c.to_dict()
        assert d["between_agents"] == []


class TestWorkflowOrchestrator:
    @pytest.fixture
    def orch(self):
        return WorkflowOrchestrator()

    def test_health(self, orch):
        assert orch.health()["alive"] is True

    def test_create_workflow(self, orch):
        wf = orch.create_workflow("Test WF", "A test workflow")
        assert wf.name == "Test WF"
        assert wf.status == WorkflowStatus.PENDING

    def test_create_workflow_with_steps(self, orch):
        steps = [
            {"name": "Step 1", "assigned_agent": "agent_a"},
            {"name": "Step 2", "depends_on": ["step_1"]},
        ]
        wf = orch.create_workflow("Multi-step", steps=steps)
        assert len(wf.steps) == 2
        assert wf.steps[0].name == "Step 1"

    def test_get_workflow(self, orch):
        wf = orch.create_workflow("Test")
        retrieved = orch.get_workflow(wf.workflow_id)
        assert retrieved is not None
        assert retrieved.name == "Test"

    def test_get_workflow_not_found(self, orch):
        assert orch.get_workflow("nonexistent") is None

    def test_register_agent(self, orch):
        orch.register_agent_available("agent_a")
        assert "agent_a" in orch._available_agents

    def test_unregister_agent(self, orch):
        orch.register_agent_available("agent_a")
        orch.unregister_agent("agent_a")
        assert "agent_a" not in orch._available_agents

    def test_form_team_with_agents(self, orch):
        orch.register_agent_available("agent_a")
        orch.register_agent_available("agent_b")
        wf = orch.create_workflow("Test")
        team = orch.form_team(wf.workflow_id)
        assert team is not None
        assert len(team.members) == 2
        assert team.members[0]["role"] == "lead"
        assert team.members[-1]["role"] == "reviewer"

    def test_form_team_no_agents(self, orch):
        wf = orch.create_workflow("Test")
        team = orch.form_team(wf.workflow_id)
        assert team is not None
        assert len(team.members) == 1
        assert team.members[0]["role"] == "coordinator"

    def test_form_team_nonexistent(self, orch):
        assert orch.form_team("nonexistent") is None

    def test_get_team(self, orch):
        orch.register_agent_available("agent_a")
        wf = orch.create_workflow("Test")
        team = orch.form_team(wf.workflow_id)
        retrieved = orch.get_team(team.team_id)
        assert retrieved is not None
        assert retrieved.team_id == team.team_id

    def test_assign_step(self, orch):
        steps = [{"name": "Step 1"}]
        wf = orch.create_workflow("Test", steps=steps)
        assert orch.assign_step(wf.workflow_id, wf.steps[0].step_id, "agent_a")
        assert wf.steps[0].assigned_agent == "agent_a"

    def test_assign_step_nonexistent(self, orch):
        wf = orch.create_workflow("Test")
        assert orch.assign_step(wf.workflow_id, "bad_step", "agent_a") is False

    def test_start_workflow(self, orch):
        wf = orch.create_workflow("Test")
        assert orch.start_workflow(wf.workflow_id) is True
        updated = orch.get_workflow(wf.workflow_id)
        assert updated is not None
        assert updated.status == WorkflowStatus.RUNNING

    def test_start_nonexistent(self, orch):
        assert orch.start_workflow("nonexistent") is False

    def test_complete_step(self, orch):
        steps = [{"name": "Step 1"}]
        wf = orch.create_workflow("Test", steps=steps)
        orch.start_workflow(wf.workflow_id)
        assert orch.complete_step(wf.workflow_id, wf.steps[0].step_id, {"ok": True})
        assert wf.steps[0].status == "completed"

    def test_fail_and_reassign_step(self, orch):
        orch.register_agent_available("agent_b")
        steps = [{"name": "Step 1", "assigned_agent": "agent_a"}]
        wf = orch.create_workflow("Test", steps=steps)
        orch.start_workflow(wf.workflow_id)
        assert orch.fail_step(wf.workflow_id, wf.steps[0].step_id, "Error")
        # Should reassign to agent_b since agent_a failed
        assert wf.steps[0].retry_count == 1

    def test_fail_step_no_reassign(self, orch):
        steps = [{"name": "Step 1", "assigned_agent": "agent_a"}]
        wf = orch.create_workflow("Test", steps=steps)
        orch.start_workflow(wf.workflow_id)
        assert orch.fail_step(wf.workflow_id, wf.steps[0].step_id, "Error", reassign=False)
        assert wf.steps[0].status == "failed"

    def test_workflow_completes_when_all_steps_done(self, orch):
        steps = [{"name": "S1"}, {"name": "S2"}]
        wf = orch.create_workflow("Test", steps=steps)
        orch.start_workflow(wf.workflow_id)
        orch.complete_step(wf.workflow_id, wf.steps[0].step_id)
        orch.complete_step(wf.workflow_id, wf.steps[1].step_id)
        updated = orch.get_workflow(wf.workflow_id)
        assert updated is not None
        assert updated.status == WorkflowStatus.COMPLETED

    def test_report_conflict(self, orch):
        conflict = orch.report_conflict(
            "w1", ["agent_a", "agent_b"],
            "Both want same resource",
            ConflictSeverity.HIGH,
        )
        assert conflict.between_agents == ["agent_a", "agent_b"]
        assert conflict.severity == ConflictSeverity.HIGH
        assert conflict.resolved is False

    def test_resolve_conflict(self, orch):
        conflict = orch.report_conflict("w1", ["a", "b"], "Disagreement")
        assert orch.resolve_conflict(conflict.conflict_id, "Assign to agent_a")
        assert conflict.resolved is True
        assert conflict.resolution == "Assign to agent_a"

    def test_resolve_nonexistent(self, orch):
        assert orch.resolve_conflict("nonexistent", "ignore") is False

    def test_pause_resume_workflow(self, orch):
        wf = orch.create_workflow("Test")
        orch.start_workflow(wf.workflow_id)
        assert orch.pause_workflow(wf.workflow_id) is True
        assert wf.status == WorkflowStatus.PAUSED
        assert orch.resume_workflow(wf.workflow_id) is True
        assert wf.status == WorkflowStatus.RUNNING

    def test_pause_not_running(self, orch):
        wf = orch.create_workflow("Test")
        # PENDING, not RUNNING
        assert orch.pause_workflow(wf.workflow_id) is False

    def test_get_next_ready_steps(self, orch):
        steps = [
            {"name": "S1", "assigned_agent": "a"},
            {"name": "S2", "depends_on": ["s1_fake"]},
        ]
        wf = orch.create_workflow("Test", steps=steps)
        ready = orch.get_next_ready_steps(wf.workflow_id)
        assert len(ready) == 1
        assert ready[0].name == "S1"

    def test_get_workflow_progress(self, orch):
        steps = [{"name": "S1"}, {"name": "S2"}, {"name": "S3"}]
        wf = orch.create_workflow("Test", steps=steps)
        progress = orch.get_workflow_progress(wf.workflow_id)
        assert progress["total_steps"] == 3
        assert progress["progress_pct"] == 0.0

    def test_statistics(self, orch):
        wf = orch.create_workflow("Test 1")
        orch.start_workflow(wf.workflow_id)
        wf2 = orch.create_workflow("Test 2")
        stats = orch.get_statistics()
        assert stats["total_workflows"] == 2
        assert stats["running"] >= 1

    def test_with_event_bus(self):
        mock_bus = MagicMock()
        orch = WorkflowOrchestrator(event_bus=mock_bus)
        orch.create_workflow("Test")
        assert mock_bus.publish.called

    def test_with_graph_store(self):
        mock_graph = MagicMock()
        orch = WorkflowOrchestrator(graph_store=mock_graph)
        orch.create_workflow("Test")
        assert mock_graph.create_entity.called
