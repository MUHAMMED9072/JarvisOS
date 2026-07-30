from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.autonomy.dashboard.dashboard_service import (
    AlertConfig,
    AlertLevel,
    DashboardService,
    EvolutionRequest,
    InterventionResult,
    PolicyConfig,
    SystemSnapshot,
)


class TestAlertConfig:
    def test_to_dict(self):
        a = AlertConfig(
            alert_id="a1", name="CPU Alert",
            metric="cpu_usage", threshold=90.0,
            level=AlertLevel.ERROR,
        )
        d = a.to_dict()
        assert d["metric"] == "cpu_usage"
        assert d["level"] == "error"

    def test_to_dict_defaults(self):
        a = AlertConfig()
        d = a.to_dict()
        assert d["enabled"] is True


class TestPolicyConfig:
    def test_to_dict(self):
        p = PolicyConfig(policy_id="p1", name="Test Policy", scope="agent")
        d = p.to_dict()
        assert d["name"] == "Test Policy"
        assert d["scope"] == "agent"

    def test_to_dict_defaults(self):
        p = PolicyConfig()
        d = p.to_dict()
        assert d["parameters"] == {}


class TestEvolutionRequest:
    def test_to_dict(self):
        r = EvolutionRequest(
            request_id="r1", target_component="kernel",
            description="Optimize scheduler", risk_score=0.7,
        )
        d = r.to_dict()
        assert d["target_component"] == "kernel"
        assert d["risk_score"] == 0.7

    def test_to_dict_defaults(self):
        r = EvolutionRequest()
        d = r.to_dict()
        assert d["approved"] is False


class TestInterventionResult:
    def test_to_dict(self):
        r = InterventionResult(
            intervention_id="i1", action="pause_project",
            target="proj_1", status="completed",
            message="Paused", timestamp=100.0,
        )
        d = r.to_dict()
        assert d["action"] == "pause_project"
        assert d["status"] == "completed"

    def test_to_dict_defaults(self):
        r = InterventionResult()
        d = r.to_dict()
        assert d["action"] == ""


class TestSystemSnapshot:
    def test_to_dict(self):
        s = SystemSnapshot(
            snapshot_id="s1", timestamp=100.0,
            agents={"total": 5}, health={"overall": "healthy"},
        )
        d = s.to_dict()
        assert d["agents"]["total"] == 5
        assert d["health"]["overall"] == "healthy"

    def test_to_dict_defaults(self):
        s = SystemSnapshot()
        d = s.to_dict()
        assert d["metrics"] == {}


class TestDashboardService:
    @pytest.fixture
    def ds(self):
        return DashboardService()

    def test_health(self, ds):
        assert ds.health()["alive"] is True

    def test_take_snapshot(self, ds):
        snap = ds.take_snapshot()
        assert snap.snapshot_id != ""
        assert snap.timestamp > 0

    def test_get_latest_snapshot(self, ds):
        ds.take_snapshot()
        snap = ds.get_latest_snapshot()
        assert snap is not None

    def test_update_component_health(self, ds):
        ds.update_component_health("kernel", "healthy")
        assert ds.get_component_health("kernel") == "healthy"

    def test_get_all_health(self, ds):
        ds.update_component_health("kernel", "healthy")
        ds.update_component_health("scheduler", "degraded")
        health = ds.get_all_health()
        assert health["kernel"] == "healthy"
        assert health["scheduler"] == "degraded"

    def test_create_alert_config(self, ds):
        alert = ds.create_alert_config(
            "High CPU", "cpu_usage", 90.0, AlertLevel.WARNING,
        )
        assert alert.name == "High CPU"
        assert alert.metric == "cpu_usage"

    def test_get_alert_config(self, ds):
        alert = ds.create_alert_config("Test", "mem", 80.0)
        retrieved = ds.get_alert_config(alert.alert_id)
        assert retrieved is not None
        assert retrieved.name == "Test"

    def test_update_alert_config(self, ds):
        alert = ds.create_alert_config("Test", "cpu", 90.0)
        assert ds.update_alert_config(alert.alert_id, enabled=False)
        assert alert.enabled is False
        assert ds.update_alert_config(alert.alert_id, threshold=95.0)
        assert alert.threshold == 95.0

    def test_update_alert_nonexistent(self, ds):
        assert ds.update_alert_config("bad_id", enabled=False) is False

    def test_delete_alert_config(self, ds):
        alert = ds.create_alert_config("Test", "cpu", 90.0)
        assert ds.delete_alert_config(alert.alert_id) is True
        assert ds.get_alert_config(alert.alert_id) is None

    def test_delete_alert_nonexistent(self, ds):
        assert ds.delete_alert_config("bad_id") is False

    def test_list_alert_configs(self, ds):
        ds.create_alert_config("A1", "cpu", 90.0)
        ds.create_alert_config("A2", "mem", 80.0)
        assert len(ds.list_alert_configs()) == 2

    def test_evaluate_alerts_triggers(self, ds):
        ds.create_alert_config("CPU Alert", "cpu_usage", 80.0)
        triggered = ds.evaluate_alerts({"cpu_usage": 95.0})
        assert len(triggered) == 1
        assert triggered[0]["metric"] == "cpu_usage"

    def test_evaluate_alerts_no_trigger(self, ds):
        ds.create_alert_config("CPU Alert", "cpu_usage", 90.0)
        triggered = ds.evaluate_alerts({"cpu_usage": 50.0})
        assert len(triggered) == 0

    def test_evaluate_alerts_disabled(self, ds):
        alert = ds.create_alert_config("CPU Alert", "cpu_usage", 80.0)
        ds.update_alert_config(alert.alert_id, enabled=False)
        triggered = ds.evaluate_alerts({"cpu_usage": 95.0})
        assert len(triggered) == 0

    def test_create_policy_config(self, ds):
        policy = ds.create_policy_config(
            "Max Agents", "Limit agent count", "system",
            {"max_agents": 10},
        )
        assert policy.name == "Max Agents"
        assert policy.parameters["max_agents"] == 10

    def test_get_policy_config(self, ds):
        policy = ds.create_policy_config("Test Policy")
        retrieved = ds.get_policy_config(policy.policy_id)
        assert retrieved is not None
        assert retrieved.name == "Test Policy"

    def test_update_policy_config(self, ds):
        policy = ds.create_policy_config("Test")
        assert ds.update_policy_config(policy.policy_id, enabled=False)
        assert policy.enabled is False
        assert ds.update_policy_config(
            policy.policy_id, parameters={"key": "val"}
        )
        assert policy.parameters["key"] == "val"

    def test_list_policy_configs(self, ds):
        ds.create_policy_config("P1")
        ds.create_policy_config("P2")
        assert len(ds.list_policy_configs()) == 2

    def test_delete_policy_config(self, ds):
        policy = ds.create_policy_config("Test")
        assert ds.delete_policy_config(policy.policy_id) is True

    def test_submit_evolution_request(self, ds):
        req = ds.submit_evolution_request(
            "kernel", "Optimize scheduler", 0.7,
        )
        assert req.target_component == "kernel"
        assert req.status == "pending"

    def test_approve_evolution(self, ds):
        req = ds.submit_evolution_request("kernel", "Fix bug")
        assert ds.approve_evolution(req.request_id) is True
        assert req.approved is True
        assert req.status == "approved"

    def test_reject_evolution(self, ds):
        req = ds.submit_evolution_request("kernel", "Fix bug")
        assert ds.reject_evolution(req.request_id) is True
        assert req.approved is False
        assert req.status == "rejected"

    def test_approve_nonexistent(self, ds):
        assert ds.approve_evolution("bad_id") is False

    def test_list_evolution_requests(self, ds):
        ds.submit_evolution_request("kernel", "Fix")
        ds.submit_evolution_request("framework", "Update")
        all_req = ds.list_evolution_requests()
        assert len(all_req) == 2

    def test_list_evolution_requests_filtered(self, ds):
        ds.submit_evolution_request("kernel", "Fix")
        r2 = ds.submit_evolution_request("framework", "Update")
        ds.approve_evolution(r2.request_id)
        pending = ds.list_evolution_requests(status="pending")
        assert len(pending) == 1

    def test_execute_intervention_unknown(self, ds):
        result = ds.execute_intervention("unknown_action", "target")
        assert result.status == "failed"
        assert "Unknown" in result.message

    def test_execute_intervention_with_project_manager(self, ds):
        mock_pm = MagicMock()
        mock_pm.pause_project.return_value = True
        ds._pm = mock_pm
        result = ds.execute_intervention("pause_project", "proj_1")
        assert result.status == "completed"

    def test_execute_intervention_with_orchestrator(self, ds):
        mock_arch = MagicMock()
        mock_arch.pause_workflow.return_value = True
        ds._orchestrator = mock_arch
        result = ds.execute_intervention("pause_workflow", "wf_1")
        assert result.status == "completed"

    def test_get_intervention(self, ds):
        result = ds.execute_intervention("pause_project", "proj_1")
        retrieved = ds.get_intervention(result.intervention_id)
        assert retrieved is not None

    def test_list_interventions(self, ds):
        ds.execute_intervention("pause_project", "proj_1")
        ds.execute_intervention("resume_project", "proj_1")
        assert len(ds.list_interventions()) == 2

    def test_query_audit_log(self, ds):
        mock_graph = MagicMock()
        mock_entity = MagicMock()
        mock_entity.to_dict.return_value = {
            "name": "Test Entity", "type": "project",
        }
        mock_graph.list_entities.return_value = [mock_entity]
        ds._graph = mock_graph
        entries = ds.query_audit_log("Test")
        assert len(entries) == 1

    def test_query_audit_log_no_graph(self, ds):
        entries = ds.query_audit_log("Test")
        assert entries == []

    def test_get_system_overview(self, ds):
        overview = ds.get_system_overview()
        assert "health" in overview
        assert "timestamp" in overview

    def test_statistics(self, ds):
        ds.take_snapshot()
        ds.create_alert_config("A1", "cpu", 90.0)
        stats = ds.get_statistics()
        assert stats["total_snapshots"] >= 1
        assert stats["total_alerts"] >= 1

    def test_with_event_bus(self):
        mock_bus = MagicMock()
        ds = DashboardService(event_bus=mock_bus)
        ds.take_snapshot()
        assert mock_bus.publish.called

    def test_snapshot_with_project_manager(self, ds):
        mock_pm = MagicMock()
        mock_pm.get_statistics.return_value = {"total_projects": 5}
        ds._pm = mock_pm
        snap = ds.take_snapshot()
        assert snap.projects.get("total_projects") == 5
