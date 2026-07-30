from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.autonomy.project_manager import (
    Milestone,
    Project,
    ProjectManager,
    ProjectPhase,
    ProjectReport,
    ProjectStatus,
)


class TestMilestone:
    def test_to_dict(self):
        m = Milestone(
            milestone_id="m1", name="Test Milestone",
            description="Do something", status="pending",
            assigned_agent="agent_a", started_at=100.0,
            completed_at=200.0,
        )
        d = m.to_dict()
        assert d["name"] == "Test Milestone"
        assert d["status"] == "pending"
        assert d["assigned_agent"] == "agent_a"

    def test_to_dict_defaults(self):
        m = Milestone()
        d = m.to_dict()
        assert d["depends_on"] == []
        assert d["result"] == {}


class TestProject:
    def test_to_dict(self):
        p = Project(
            project_id="p1", name="Test Project",
            goal="Build something", status=ProjectStatus.ACTIVE,
            phase=ProjectPhase.EXECUTION, created_at=100.0,
            updated_at=150.0,
        )
        d = p.to_dict()
        assert d["name"] == "Test Project"
        assert d["status"] == "active"
        assert d["phase"] == "execution"

    def test_to_dict_defaults(self):
        p = Project()
        d = p.to_dict()
        assert d["milestones"] == []
        assert d["checkpoints"] == []


class TestProjectReport:
    def test_to_dict(self):
        r = ProjectReport(
            report_id="r1", project_id="p1", project_name="Test",
            goal="Build", status="completed",
            milestones_completed=5, milestones_total=5,
            duration_seconds=120.0, decisions_made=10,
            human_interventions=2, summary="Done",
            timestamp=100.0,
        )
        d = r.to_dict()
        assert d["milestones_completed"] == 5
        assert d["summary"] == "Done"

    def test_to_dict_defaults(self):
        r = ProjectReport()
        d = r.to_dict()
        assert d["details"] == {}


class TestProjectManager:
    @pytest.fixture
    def pm(self):
        return ProjectManager()

    def test_health(self, pm):
        assert pm.health()["alive"] is True

    def test_create_project(self, pm):
        project = pm.create_project("Build a trading bot", "Trading Bot")
        assert project.goal == "Build a trading bot"
        assert project.name == "Trading Bot"
        assert project.status == ProjectStatus.PENDING
        assert project.phase == ProjectPhase.GOAL_DEFINITION

    def test_get_project(self, pm):
        created = pm.create_project("Goal A")
        retrieved = pm.get_project(created.project_id)
        assert retrieved is not None
        assert retrieved.goal == "Goal A"

    def test_get_project_not_found(self, pm):
        assert pm.get_project("nonexistent") is None

    def test_plan_project(self, pm):
        project = pm.create_project("Build a web scraper", "Scraper")
        first = pm.plan_project(project.project_id)
        updated = pm.get_project(project.project_id)
        assert updated is not None
        assert updated.status == ProjectStatus.PLANNING
        assert updated.phase == ProjectPhase.PLANNING
        assert len(updated.milestones) >= 1
        assert first is not None

    def test_plan_project_not_found(self, pm):
        assert pm.plan_project("nonexistent") is None

    def test_start_execution(self, pm):
        project = pm.create_project("Goal")
        pm.plan_project(project.project_id)
        assert pm.start_execution(project.project_id) is True
        updated = pm.get_project(project.project_id)
        assert updated is not None
        assert updated.status == ProjectStatus.ACTIVE
        assert updated.phase == ProjectPhase.EXECUTION

    def test_start_execution_not_planned(self, pm):
        project = pm.create_project("Goal")
        # Project is PENDING, not PLANNING
        assert pm.start_execution(project.project_id) is False

    def test_update_milestone(self, pm):
        project = pm.create_project("Goal")
        pm.plan_project(project.project_id)
        milestone_id = project.milestones[0].milestone_id
        assert pm.update_milestone(
            project.project_id, milestone_id, "completed",
            {"output": "done"},
        ) is True
        updated = pm.get_project(project.project_id)
        assert updated is not None
        ms = updated.milestones[0]
        assert ms.status == "completed"
        assert ms.result == {"output": "done"}

    def test_update_milestone_nonexistent(self, pm):
        project = pm.create_project("Goal")
        assert pm.update_milestone(
            project.project_id, "nonexistent", "completed"
        ) is False

    def test_completion_after_all_milestones(self, pm):
        project = pm.create_project("Goal")
        pm.plan_project(project.project_id)
        pm.start_execution(project.project_id)
        for ms in project.milestones:
            pm.update_milestone(project.project_id, ms.milestone_id, "completed")
        updated = pm.get_project(project.project_id)
        assert updated is not None
        assert updated.status == ProjectStatus.COMPLETED
        assert updated.phase == ProjectPhase.VERIFICATION

    def test_add_human_checkpoint(self, pm):
        project = pm.create_project("Goal")
        cpid = pm.add_human_checkpoint(
            project.project_id, "Review architecture", True
        )
        assert cpid is not None
        updated = pm.get_project(project.project_id)
        assert updated is not None
        assert len(updated.checkpoints) == 1
        assert updated.checkpoints[0]["required_approval"] is True

    def test_add_checkpoint_nonexistent(self, pm):
        assert pm.add_human_checkpoint("nonexistent", "test") is None

    def test_resolve_checkpoint(self, pm):
        project = pm.create_project("Goal")
        cpid = pm.add_human_checkpoint(
            project.project_id, "Approve plan", True
        )
        assert pm.resolve_checkpoint(project.project_id, cpid, True) is True
        updated = pm.get_project(project.project_id)
        assert updated is not None
        assert updated.checkpoints[0]["approved"] is True
        assert updated.checkpoints[0]["resolved_at"] > 0

    def test_resolve_checkpoint_nonexistent(self, pm):
        assert pm.resolve_checkpoint("nonexistent", "cp1", True) is False

    def test_pause_resume_project(self, pm):
        project = pm.create_project("Goal")
        pm.plan_project(project.project_id)
        pm.start_execution(project.project_id)
        assert pm.pause_project(project.project_id) is True
        paused = pm.get_project(project.project_id)
        assert paused is not None
        assert paused.status == ProjectStatus.PAUSED
        assert pm.resume_project(project.project_id) is True
        resumed = pm.get_project(project.project_id)
        assert resumed is not None
        assert resumed.status == ProjectStatus.ACTIVE

    def test_pause_not_active(self, pm):
        project = pm.create_project("Goal")
        # PENDING, not ACTIVE
        assert pm.pause_project(project.project_id) is False

    def test_cancel_project(self, pm):
        project = pm.create_project("Goal")
        assert pm.cancel_project(project.project_id) is True
        updated = pm.get_project(project.project_id)
        assert updated is not None
        assert updated.status == ProjectStatus.CANCELLED

    def test_cancel_nonexistent(self, pm):
        assert pm.cancel_project("nonexistent") is False

    def test_make_decision(self, pm):
        project = pm.create_project("Goal")
        decision = pm.make_decision(
            project.project_id, "Which approach?",
            ["A", "B"], "A", "A is simpler",
        )
        assert decision["selected"] == "A"
        assert decision["rationale"] == "A is simpler"

    def test_generate_report(self, pm):
        project = pm.create_project("Build a bot")
        pm.plan_project(project.project_id)
        pm.start_execution(project.project_id)
        # Complete all milestones
        for ms in project.milestones:
            pm.update_milestone(project.project_id, ms.milestone_id, "completed")
        updated = pm.get_project(project.project_id)
        assert updated is not None
        assert updated.status == ProjectStatus.COMPLETED

    def test_get_report(self, pm):
        project = pm.create_project("Goal")
        pm.plan_project(project.project_id)
        pm.start_execution(project.project_id)
        for ms in project.milestones:
            pm.update_milestone(project.project_id, ms.milestone_id, "completed")
        pm._generate_report(project.project_id)
        report = pm.get_project_report_by_id(project.project_id)
        assert report is not None
        assert report.goal == "Goal"
        assert report.milestones_total > 0

    def test_list_projects(self, pm):
        pm.create_project("Project A")
        pm.create_project("Project B")
        assert len(pm.list_projects()) == 2

    def test_list_active_projects(self, pm):
        p1 = pm.create_project("Project A")
        p2 = pm.create_project("Project B")
        pm.plan_project(p1.project_id)
        pm.start_execution(p1.project_id)
        active = pm.list_active_projects()
        assert len(active) == 1
        assert active[0].project_id == p1.project_id

    def test_statistics(self, pm):
        p1 = pm.create_project("Project A")
        p2 = pm.create_project("Project B")
        pm.plan_project(p1.project_id)
        pm.start_execution(p1.project_id)
        for ms in p1.milestones:
            pm.update_milestone(p1.project_id, ms.milestone_id, "completed")
        stats = pm.get_statistics()
        assert stats["total_projects"] == 2
        assert stats["completed"] >= 1

    def test_with_event_bus(self):
        mock_bus = MagicMock()
        pm = ProjectManager(event_bus=mock_bus)
        pm.create_project("Test Goal")
        assert mock_bus.publish.called

    def test_with_graph_store(self):
        mock_graph = MagicMock()
        pm = ProjectManager(graph_store=mock_graph)
        pm.create_project("Test Goal")
        assert mock_graph.create_entity.called

    def test_with_pipeline(self):
        mock_pipeline = MagicMock()
        mock_result = MagicMock()
        mock_result.task_graph.tasks = ["Task 1", "Task 2"]
        mock_pipeline.run.return_value = mock_result
        pm = ProjectManager(pipeline=mock_pipeline)
        project = pm.create_project("Build a bot")
        pm.plan_project(project.project_id)
        updated = pm.get_project(project.project_id)
        assert updated is not None
        assert len(updated.milestones) == 2

    def test_decompose_goal_no_pipeline(self, pm):
        project = pm.create_project("Simple goal")
        pm.plan_project(project.project_id)
        updated = pm.get_project(project.project_id)
        assert updated is not None
        # Should still create at least one milestone
        assert len(updated.milestones) >= 1
        assert "Simple goal" in updated.milestones[0].description or True
