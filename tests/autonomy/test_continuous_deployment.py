from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.autonomy.continuous_deployment import (
    CanaryResult,
    ContinuousDeployment,
    Deployment,
    DeploymentReport,
)


class TestDeployment:
    def test_to_dict(self):
        d = Deployment(
            deployment_id="d1", name="v2 Upgrade",
            version="2.0.0", status="completed",
            target_components=["kernel"],
        )
        result = d.to_dict()
        assert result["name"] == "v2 Upgrade"
        assert result["status"] == "completed"
        assert result["target_components"] == ["kernel"]

    def test_to_dict_defaults(self):
        d = Deployment()
        result = d.to_dict()
        assert result["rolled_back"] is False
        assert result["result"] == {}


class TestCanaryResult:
    def test_to_dict(self):
        r = CanaryResult(
            result_id="r1", deployment_id="d1",
            success_count=10, failure_count=0,
            metrics={"latency": 0.5}, healthy=True,
        )
        d = r.to_dict()
        assert d["healthy"] is True
        assert d["success_count"] == 10

    def test_to_dict_defaults(self):
        r = CanaryResult()
        d = r.to_dict()
        assert d["metrics"] == {}


class TestDeploymentReport:
    def test_to_dict(self):
        r = DeploymentReport(
            report_id="rp1", deployment_id="d1",
            name="v2", version="2.0.0", status="completed",
            canary_healthy=True, rolled_back=False,
            duration_seconds=60.0, summary="OK",
        )
        d = r.to_dict()
        assert d["status"] == "completed"
        assert d["duration_seconds"] == 60.0

    def test_to_dict_defaults(self):
        r = DeploymentReport()
        d = r.to_dict()
        assert d["target_components"] == []


class TestContinuousDeployment:
    @pytest.fixture
    def cd(self):
        return ContinuousDeployment()

    def test_health(self, cd):
        assert cd.health()["alive"] is True

    def test_create_deployment(self, cd):
        dep = cd.create_deployment("v2 Upgrade", "Upgrade kernel")
        assert dep.name == "v2 Upgrade"
        assert dep.status == "pending"
        assert dep.version == "1.1.0"

    def test_create_deployment_with_components(self, cd):
        dep = cd.create_deployment(
            "Update", target_components=["kernel", "scheduler"],
        )
        assert dep.target_components == ["kernel", "scheduler"]

    def test_create_multiple_versions(self, cd):
        d1 = cd.create_deployment("First")
        d2 = cd.create_deployment("Second")
        assert d1.version == "1.1.0"
        assert d2.version == "1.2.0"

    def test_get_deployment(self, cd):
        dep = cd.create_deployment("Test")
        retrieved = cd.get_deployment(dep.deployment_id)
        assert retrieved is not None
        assert retrieved.name == "Test"

    def test_get_deployment_not_found(self, cd):
        assert cd.get_deployment("nonexistent") is None

    def test_start_deployment(self, cd):
        dep = cd.create_deployment("Test")
        assert cd.start_deployment(dep.deployment_id) is True
        updated = cd.get_deployment(dep.deployment_id)
        assert updated is not None
        assert updated.status == "canary"

    def test_start_already_started(self, cd):
        dep = cd.create_deployment("Test")
        cd.start_deployment(dep.deployment_id)
        assert cd.start_deployment(dep.deployment_id) is False

    def test_start_nonexistent(self, cd):
        assert cd.start_deployment("bad_id") is False

    def test_canary_success_full_rollout(self, cd):
        dep = cd.create_deployment("Test")
        cd.start_deployment(dep.deployment_id)
        result = cd.record_canary_result(
            dep.deployment_id, success_count=10, failure_count=0,
        )
        assert result is not None
        assert result.healthy is True
        updated = cd.get_deployment(dep.deployment_id)
        assert updated is not None
        assert updated.status == "completed"
        assert updated.canary_healthy is True

    def test_canary_failure_rollback(self, cd):
        dep = cd.create_deployment("Test")
        cd.start_deployment(dep.deployment_id)
        result = cd.record_canary_result(
            dep.deployment_id, success_count=0, failure_count=5,
        )
        assert result is not None
        assert result.healthy is False
        updated = cd.get_deployment(dep.deployment_id)
        assert updated is not None
        assert updated.rolled_back is True
        assert updated.status == "rolled_back"

    def test_canary_nonexistent(self, cd):
        assert cd.record_canary_result("bad_id", 1, 0) is None

    def test_trigger_rollback(self, cd):
        dep = cd.create_deployment("Test")
        cd.start_deployment(dep.deployment_id)
        assert cd.trigger_rollback(dep.deployment_id, "Manual rollback") is True
        updated = cd.get_deployment(dep.deployment_id)
        assert updated is not None
        assert updated.rolled_back is True
        assert updated.result.get("rollback_reason") == "Manual rollback"

    def test_trigger_rollback_nonexistent(self, cd):
        assert cd.trigger_rollback("bad_id", "reason") is False

    def test_list_deployments(self, cd):
        cd.create_deployment("A")
        cd.create_deployment("B")
        assert len(cd.list_deployments()) == 2

    def test_get_report(self, cd):
        dep = cd.create_deployment("Test")
        cd.start_deployment(dep.deployment_id)
        cd.record_canary_result(dep.deployment_id, 10, 0)
        report = cd.get_deployment_report(dep.deployment_id)
        assert report is not None
        assert report.name == "Test"
        assert report.status == "completed"

    def test_get_report_by_id(self, cd):
        dep = cd.create_deployment("Test")
        cd.start_deployment(dep.deployment_id)
        cd.record_canary_result(dep.deployment_id, 10, 0)
        report = cd.get_deployment_report(dep.deployment_id)
        retrieved = cd.get_report(report.report_id)
        assert retrieved is not None
        assert retrieved.deployment_id == dep.deployment_id

    def test_statistics(self, cd):
        d1 = cd.create_deployment("A")
        cd.start_deployment(d1.deployment_id)
        cd.record_canary_result(d1.deployment_id, 10, 0)
        d2 = cd.create_deployment("B")
        cd.start_deployment(d2.deployment_id)
        cd.record_canary_result(d2.deployment_id, 0, 5)
        stats = cd.get_statistics()
        assert stats["total_deployments"] == 2
        assert stats["completed"] == 1
        assert stats["rolled_back"] == 1

    def test_with_event_bus(self):
        mock_bus = MagicMock()
        cd = ContinuousDeployment(event_bus=mock_bus)
        cd.create_deployment("Test")
        assert mock_bus.publish.called

    def test_with_graph_store(self):
        mock_graph = MagicMock()
        cd = ContinuousDeployment(graph_store=mock_graph)
        cd.create_deployment("Test")
        assert mock_graph.create_entity.called
