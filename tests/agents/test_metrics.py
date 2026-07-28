from __future__ import annotations

import time

import pytest

from app.agents.metrics import AgentMetrics, MetricSnapshot
from app.knowledge_graph.store import GraphStore


class TestMetricSnapshot:
    def test_success_rate(self):
        s = MetricSnapshot(execution_count=10, success_count=7, failure_count=3)
        assert abs(s.success_rate - 0.7) < 0.001

    def test_success_rate_zero(self):
        s = MetricSnapshot()
        assert s.success_rate == 1.0

    def test_percentile(self):
        s = MetricSnapshot(latencies=[1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
        assert abs(s.percentile(50) - 5.5) < 0.01
        assert abs(s.percentile(95) - 9.55) < 0.01
        assert abs(s.percentile(99) - 9.91) < 0.01

    def test_percentile_empty(self):
        s = MetricSnapshot()
        assert s.percentile(50) == 0.0

    def test_to_dict(self):
        s = MetricSnapshot(agent_id="a1", execution_count=5, latencies=[1, 2, 3])
        d = s.to_dict()
        assert d["agent_id"] == "a1"
        assert d["execution_count"] == 5
        assert "latency_p50" in d


class TestAgentMetrics:
    @pytest.fixture
    def metrics(self):
        return AgentMetrics(graph_store=GraphStore())

    def test_record_and_get(self, metrics):
        metrics.record_execution("agent-1", success=True, latency=0.5)
        snap = metrics.get_snapshot("agent-1")
        assert snap is not None
        assert snap["execution_count"] == 1
        assert snap["success_count"] == 1

    def test_record_multiple(self, metrics):
        for i in range(5):
            metrics.record_execution("a1", success=True, latency=float(i))
        snap = metrics.get_snapshot("a1")
        assert snap["execution_count"] == 5
        assert snap["success_count"] == 5

    def test_record_failure(self, metrics):
        metrics.record_execution("a1", success=False, latency=2.0)
        snap = metrics.get_snapshot("a1")
        assert snap["failure_count"] == 1
        assert snap["success_count"] == 0

    def test_get_nonexistent(self, metrics):
        assert metrics.get_snapshot("no-such-agent") is None

    def test_query_all(self, metrics):
        metrics.record_execution("a1", True, 0.1)
        metrics.record_execution("a2", True, 0.2)
        all_snaps = metrics.query_all()
        assert len(all_snaps) == 2

    def test_query_by_type(self, metrics):
        metrics.record_execution("a1", True, 0.5)
        assert metrics.query_by_type("a1", "execution_count") == 1
        assert metrics.query_by_type("a1", "nonexistent") == 0.0

    def test_query_by_type_nonexistent(self, metrics):
        assert metrics.query_by_type("nobody", "execution_count") == 0.0

    def test_different_windows(self, metrics):
        metrics.record_execution("a1", True, 0.1)
        snap_5min = metrics.get_snapshot("a1", "5min")
        snap_1hr = metrics.get_snapshot("a1", "1hr")
        assert snap_5min is not None
        assert snap_1hr is not None

    def test_health(self, metrics):
        h = metrics.health()
        assert h["alive"] is True

    def test_kg_persistence(self, metrics):
        metrics.record_execution("a1", True, 0.1)
        # Check that KG entity was created
        entities = metrics._graph_store.get_entities_by_type("agent_metrics")
        assert len(entities) >= 1

    def test_historical_query(self, metrics):
        import time
        now = time.time()
        metrics.record_execution("a1", True, 0.1)
        time.sleep(0.01)
        metrics.record_execution("a1", False, 0.2)
        results = metrics.query_time_range("a1", now, time.time() + 1)
        assert len(results) >= 2

    def test_historical_query_empty(self, metrics):
        assert metrics.query_time_range("no-agent", 0, time.time()) == []


class TestAgentMetricsWithBus:
    @pytest.fixture
    def bus(self):
        from app.agents.communication.bus import MessageBus
        return MessageBus()

    @pytest.fixture
    def metrics(self, bus):
        return AgentMetrics(bus=bus)

    def test_bus_publishing(self, metrics, bus):
        received = []
        def handler(m):
            received.append(m)
        bus.subscribe("metrics", handler)
        metrics.record_execution("a1", True, 0.1)
        assert len(received) >= 1
        assert received[0].msg_type.value == "metrics"


class TestAgentMetricsConcurrency:
    def test_concurrent_recording(self):
        import threading
        m = AgentMetrics()
        barrier = threading.Barrier(10)

        def record(idx: int) -> None:
            barrier.wait()
            for _ in range(10):
                m.record_execution(f"agent_{idx}", success=(idx % 2 == 0), latency=0.1)

        threads = [threading.Thread(target=record, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        for i in range(10):
            snap = m.get_snapshot(f"agent_{i}")
            assert snap is not None
            assert snap["execution_count"] == 10
