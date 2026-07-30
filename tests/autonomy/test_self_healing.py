from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.autonomy.self_healing import (
    Anomaly,
    HealingAction,
    SelfHealingEngine,
)


class TestAnomaly:
    def test_to_dict(self):
        a = Anomaly(
            anomaly_id="a1", component="kernel", metric="cpu_usage",
            observed_value=95.0, expected_range=(0.0, 80.0),
            severity="high",
        )
        d = a.to_dict()
        assert d["metric"] == "cpu_usage"
        assert d["severity"] == "high"
        assert d["expected_max"] == 80.0

    def test_to_dict_defaults(self):
        a = Anomaly()
        d = a.to_dict()
        assert d["resolved"] is False


class TestHealingAction:
    def test_to_dict(self):
        a = HealingAction(
            action_id="act1", anomaly_id="a1",
            action_type="restart", description="Restart kernel",
            status="completed", result="OK",
        )
        d = a.to_dict()
        assert d["action_type"] == "restart"
        assert d["status"] == "completed"

    def test_to_dict_defaults(self):
        a = HealingAction()
        d = a.to_dict()
        assert d["status"] == "pending"


class TestSelfHealingEngine:
    @pytest.fixture
    def engine(self):
        return SelfHealingEngine()

    def test_health(self, engine):
        assert engine.health()["alive"] is True

    def test_set_baseline(self, engine):
        engine.set_baseline("kernel", "cpu_usage", 0.0, 80.0)
        baseline = engine.get_baseline("kernel", "cpu_usage")
        assert baseline == (0.0, 80.0)

    def test_get_baseline_default(self, engine):
        baseline = engine.get_baseline("unknown", "metric")
        assert baseline == (0.0, float("inf"))

    def test_detect_no_anomaly(self, engine):
        engine.set_baseline("kernel", "cpu_usage", 0.0, 80.0)
        result = engine.detect_anomaly("kernel", "cpu_usage", 50.0)
        assert result is None

    def test_detect_anomaly_low(self, engine):
        engine.set_baseline("kernel", "cpu_usage", 0.0, 80.0)
        anomaly = engine.detect_anomaly("kernel", "cpu_usage", 85.0)
        assert anomaly is not None
        assert anomaly.metric == "cpu_usage"
        assert anomaly.severity == "low"

    def test_detect_anomaly_medium(self, engine):
        engine.set_baseline("kernel", "cpu_usage", 0.0, 50.0)
        anomaly = engine.detect_anomaly("kernel", "cpu_usage", 95.0)
        assert anomaly is not None
        assert anomaly.severity == "medium"

    def test_detect_anomaly_high(self, engine):
        engine.set_baseline("kernel", "cpu_usage", 0.0, 20.0)
        anomaly = engine.detect_anomaly("kernel", "cpu_usage", 60.0)
        assert anomaly is not None
        assert anomaly.severity == "high"

    def test_detect_anomaly_critical(self, engine):
        engine.set_baseline("kernel", "cpu_usage", 0.0, 10.0)
        anomaly = engine.detect_anomaly("kernel", "cpu_usage", 95.0)
        assert anomaly is not None
        assert anomaly.severity == "critical"

    def test_heal_anomaly_high_cpu(self, engine):
        engine.set_baseline("kernel", "high_cpu", 0.0, 50.0)
        anomaly = engine.detect_anomaly("kernel", "high_cpu", 95.0)
        assert anomaly is not None
        action = engine.heal_anomaly(anomaly.anomaly_id)
        assert action is not None
        assert action.action_type == "restart"

    def test_heal_anomaly_high_memory(self, engine):
        engine.set_baseline("kernel", "high_memory", 0.0, 70.0)
        anomaly = engine.detect_anomaly("kernel", "high_memory", 150.0)
        assert anomaly is not None
        action = engine.heal_anomaly(anomaly.anomaly_id)
        assert action is not None
        assert action.action_type == "clear_cache"

    def test_heal_anomaly_general(self, engine):
        engine.set_baseline("kernel", "custom_metric", 0.0, 50.0)
        anomaly = engine.detect_anomaly("kernel", "custom_metric", 95.0)
        assert anomaly is not None
        action = engine.heal_anomaly(anomaly.anomaly_id)
        assert action is not None
        assert action.action_type == "restart"

    def test_heal_nonexistent(self, engine):
        assert engine.heal_anomaly("nonexistent") is None

    def test_heal_already_resolved(self, engine):
        engine.set_baseline("kernel", "cpu_usage", 0.0, 50.0)
        anomaly = engine.detect_anomaly("kernel", "cpu_usage", 95.0)
        assert anomaly is not None
        engine.heal_anomaly(anomaly.anomaly_id)
        # Second heal should return None since it's now resolved
        assert engine.heal_anomaly(anomaly.anomaly_id) is None

    def test_verify_healing_success(self, engine):
        engine.set_baseline("kernel", "cpu_usage", 0.0, 80.0)
        anomaly = engine.detect_anomaly("kernel", "cpu_usage", 95.0)
        assert anomaly is not None
        assert engine.verify_healing(anomaly.anomaly_id, 50.0) is True
        assert anomaly.resolved is True

    def test_verify_healing_failure(self, engine):
        engine.set_baseline("kernel", "cpu_usage", 0.0, 80.0)
        anomaly = engine.detect_anomaly("kernel", "cpu_usage", 95.0)
        assert anomaly is not None
        # Still anomalous, should trigger another healing attempt
        assert engine.verify_healing(anomaly.anomaly_id, 90.0) is False

    def test_verify_nonexistent(self, engine):
        assert engine.verify_healing("bad_id", 50.0) is False

    def test_get_anomaly(self, engine):
        engine.set_baseline("kernel", "cpu_usage", 0.0, 50.0)
        anomaly = engine.detect_anomaly("kernel", "cpu_usage", 95.0)
        retrieved = engine.get_anomaly(anomaly.anomaly_id)
        assert retrieved is not None
        assert retrieved.anomaly_id == anomaly.anomaly_id

    def test_get_action(self, engine):
        engine.set_baseline("kernel", "high_cpu", 0.0, 50.0)
        anomaly = engine.detect_anomaly("kernel", "high_cpu", 95.0)
        action = engine.heal_anomaly(anomaly.anomaly_id)
        assert action is not None
        retrieved = engine.get_action(action.action_id)
        assert retrieved is not None
        assert retrieved.action_id == action.action_id

    def test_list_anomalies(self, engine):
        engine.set_baseline("kernel", "cpu_usage", 0.0, 50.0)
        engine.detect_anomaly("kernel", "cpu_usage", 95.0)
        engine.detect_anomaly("kernel", "cpu_usage", 90.0)
        assert len(engine.list_anomalies()) == 2

    def test_list_anomalies_filtered(self, engine):
        engine.set_baseline("kernel", "cpu_usage", 0.0, 50.0)
        a1 = engine.detect_anomaly("kernel", "cpu_usage", 95.0)
        engine.detect_anomaly("kernel", "cpu_usage", 90.0)
        engine.heal_anomaly(a1.anomaly_id)
        unresolved = engine.list_anomalies(resolved=False)
        resolved = engine.list_anomalies(resolved=True)
        assert len(unresolved) >= 1
        assert len(resolved) >= 1

    def test_list_actions(self, engine):
        engine.set_baseline("kernel", "high_cpu", 0.0, 50.0)
        anomaly = engine.detect_anomaly("kernel", "high_cpu", 95.0)
        engine.heal_anomaly(anomaly.anomaly_id)
        assert len(engine.list_actions()) >= 1

    def test_statistics(self, engine):
        engine.set_baseline("kernel", "high_cpu", 0.0, 50.0)
        a1 = engine.detect_anomaly("kernel", "high_cpu", 95.0)
        engine.heal_anomaly(a1.anomaly_id)
        stats = engine.get_statistics()
        assert stats["total_detected"] >= 1
        assert stats["total_healed"] >= 1
        assert stats["healing_rate"] > 0

    def test_with_event_bus(self):
        mock_bus = MagicMock()
        engine = SelfHealingEngine(event_bus=mock_bus)
        engine.set_baseline("kernel", "cpu_usage", 0.0, 50.0)
        engine.detect_anomaly("kernel", "cpu_usage", 95.0)
        assert mock_bus.publish.called

    def test_with_executive_controller(self):
        mock_ec = MagicMock()
        engine = SelfHealingEngine(executive_controller=mock_ec)
        engine.set_baseline("kernel", "high_cpu", 0.0, 50.0)
        anomaly = engine.detect_anomaly("kernel", "high_cpu", 95.0)
        assert anomaly is not None
        action = engine.heal_anomaly(anomaly.anomaly_id)
        assert action is not None
        assert action.status == "completed"
