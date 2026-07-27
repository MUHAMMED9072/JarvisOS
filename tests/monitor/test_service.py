"""Tests for SystemMonitorService (P12-04)."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.event_bus import EventBus
from app.core.registry import ServiceRegistry
from app.monitor.service import SystemMonitorService


# ==========================================================================
# Fixtures
# ==========================================================================


@pytest.fixture
def registry():
    r = ServiceRegistry()
    r.register("event_bus", EventBus())
    return r


@pytest.fixture
def event_bus(registry):
    return registry.get("event_bus")


@pytest.fixture
def mock_psutil():
    """Patches psutil module with controlled return values."""
    patches = [
        patch("app.monitor.service.psutil.cpu_percent", return_value=45.0),
        patch("app.monitor.service.psutil.cpu_count", side_effect=lambda logical=True: 8 if logical else 4),
        patch("app.monitor.service.psutil.cpu_freq", return_value=MagicMock(current=2400)),
        patch("app.monitor.service.psutil.virtual_memory", return_value=MagicMock(
            total=16_000_000_000, available=8_000_000_000, used=8_000_000_000, percent=50.0,
        )),
        patch("app.monitor.service.psutil.swap_memory", return_value=MagicMock(
            total=8_000_000_000, used=2_000_000_000, percent=25.0,
        )),
        patch("app.monitor.service.psutil.disk_usage", return_value=MagicMock(
            total=500_000_000_000, used=250_000_000_000, free=250_000_000_000, percent=50.0,
        )),
        patch("app.monitor.service.psutil.disk_io_counters", return_value=MagicMock(
            read_bytes=1_000_000_000, write_bytes=500_000_000,
        )),
        patch("app.monitor.service.psutil.net_io_counters", return_value=MagicMock(
            bytes_recv=10_000_000, bytes_sent=5_000_000,
        )),
        patch("app.monitor.service.psutil.pids", return_value=list(range(200))),
        patch("app.monitor.service.psutil.process_iter", return_value=[]),
        patch("app.monitor.service.psutil.Process", return_value=MagicMock(
            memory_info=MagicMock(return_value=MagicMock(rss=200_000_000)),
        )),
    ]
    for p in patches:
        p.start()
    yield
    for p in patches:
        p.stop()


# ==========================================================================
# Metrics Collection
# ==========================================================================


class TestMetricsCollection:
    @pytest.mark.asyncio
    async def test_snapshot_contains_all_keys(self, registry, event_bus, mock_psutil):
        monitor = SystemMonitorService(registry, event_bus, interval=60)
        data = await monitor.snapshot()
        assert "timestamp" in data
        assert "uptime_seconds" in data
        assert "cpu" in data
        assert "ram" in data
        assert "swap" in data
        assert "disk" in data
        assert "disk_io" in data
        assert "network" in data
        assert "processes" in data
        assert "python" in data
        assert "ai" in data
        assert "services" in data

    @pytest.mark.asyncio
    async def test_cpu_metrics(self, registry, event_bus, mock_psutil):
        monitor = SystemMonitorService(registry, event_bus, interval=60)
        data = await monitor.snapshot()
        cpu = data["cpu"]
        assert cpu["percent"] == 45.0
        assert cpu["frequency_mhz"] == 2400
        assert cpu["count_logical"] == 8
        assert cpu["count_physical"] == 4

    @pytest.mark.asyncio
    async def test_ram_metrics(self, registry, event_bus, mock_psutil):
        monitor = SystemMonitorService(registry, event_bus, interval=60)
        data = await monitor.snapshot()
        ram = data["ram"]
        assert ram["total_bytes"] == 16_000_000_000
        assert ram["available_bytes"] == 8_000_000_000
        assert ram["percent"] == 50.0

    @pytest.mark.asyncio
    async def test_disk_metrics(self, registry, event_bus, mock_psutil):
        monitor = SystemMonitorService(registry, event_bus, interval=60)
        data = await monitor.snapshot()
        disk = data["disk"]
        assert disk["percent"] == 50.0
        assert disk["total_bytes"] == 500_000_000_000

    @pytest.mark.asyncio
    async def test_process_metrics(self, registry, event_bus, mock_psutil):
        monitor = SystemMonitorService(registry, event_bus, interval=60)
        data = await monitor.snapshot()
        assert data["processes"]["count"] == 200

    @pytest.mark.asyncio
    async def test_python_memory(self, registry, event_bus, mock_psutil):
        monitor = SystemMonitorService(registry, event_bus, interval=60)
        data = await monitor.snapshot()
        assert data["python"]["memory_bytes"] == 200_000_000
        assert data["python"]["memory_mb"] == 190.73

    @pytest.mark.asyncio
    async def test_uptime_increasing(self, registry, event_bus, mock_psutil):
        monitor = SystemMonitorService(registry, event_bus, interval=60)
        data1 = await monitor.snapshot()
        await asyncio.sleep(0.01)
        data2 = await monitor.snapshot()
        assert data2["uptime_seconds"] > data1["uptime_seconds"]


# ==========================================================================
# Threshold Warnings
# ==========================================================================


class TestThresholdWarnings:
    @pytest.mark.asyncio
    async def test_no_warnings_normal(self, registry, event_bus, mock_psutil):
        monitor = SystemMonitorService(registry, event_bus, interval=60)
        data = await monitor.snapshot()
        warnings = monitor._check_thresholds(data)
        assert len(warnings) == 0

    @pytest.mark.asyncio
    async def test_high_cpu_warning(self, registry, event_bus, mock_psutil):
        with patch("app.monitor.service.psutil.cpu_percent", return_value=95.0):
            monitor = SystemMonitorService(registry, event_bus, interval=60)
            data = await monitor.snapshot()
            warnings = monitor._check_thresholds(data)
            types = [w["type"] for w in warnings]
            assert "high_cpu" in types

    @pytest.mark.asyncio
    async def test_high_ram_warning(self, registry, event_bus, mock_psutil):
        with patch("app.monitor.service.psutil.virtual_memory", return_value=MagicMock(
            total=16_000_000_000, available=1_000_000_000, used=15_000_000_000, percent=95.0,
        )):
            monitor = SystemMonitorService(registry, event_bus, interval=60)
            data = await monitor.snapshot()
            warnings = monitor._check_thresholds(data)
            types = [w["type"] for w in warnings]
            assert "high_ram" in types

    @pytest.mark.asyncio
    async def test_low_disk_warning(self, registry, event_bus, mock_psutil):
        with patch("app.monitor.service.psutil.disk_usage", return_value=MagicMock(
            total=500_000_000_000, used=490_000_000_000, free=10_000_000_000, percent=98.0,
        )):
            monitor = SystemMonitorService(registry, event_bus, interval=60)
            data = await monitor.snapshot()
            warnings = monitor._check_thresholds(data)
            types = [w["type"] for w in warnings]
            assert "low_disk" in types

    @pytest.mark.asyncio
    async def test_multiple_warnings(self, registry, event_bus, mock_psutil):
        with (
            patch("app.monitor.service.psutil.cpu_percent", return_value=95.0),
            patch("app.monitor.service.psutil.virtual_memory", return_value=MagicMock(
                total=16_000_000_000, available=1_000_000_000, used=15_000_000_000, percent=95.0,
            )),
            patch("app.monitor.service.psutil.disk_usage", return_value=MagicMock(
                total=500_000_000_000, used=490_000_000_000, free=10_000_000_000, percent=98.0,
            )),
        ):
            monitor = SystemMonitorService(registry, event_bus, interval=60)
            data = await monitor.snapshot()
            warnings = monitor._check_thresholds(data)
            assert len(warnings) == 3

    @pytest.mark.asyncio
    async def test_custom_threshold(self, registry, event_bus, mock_psutil):
        with patch("app.monitor.service.psutil.cpu_percent", return_value=85.0):
            monitor = SystemMonitorService(registry, event_bus, interval=60)
            await monitor.set_threshold("cpu_percent", 80.0)
            data = await monitor.snapshot()
            warnings = monitor._check_thresholds(data)
            types = [w["type"] for w in warnings]
            assert "high_cpu" in types


# ==========================================================================
# Health
# ==========================================================================


class TestHealth:
    @pytest.mark.asyncio
    async def test_healthy(self, registry, event_bus, mock_psutil):
        monitor = SystemMonitorService(registry, event_bus, interval=60)
        data = await monitor.snapshot()
        health = monitor._health(data)
        assert health["status"] == "healthy"
        assert health["issues"] == []

    @pytest.mark.asyncio
    async def test_degraded(self, registry, event_bus, mock_psutil):
        with patch("app.monitor.service.psutil.cpu_percent", return_value=95.0):
            monitor = SystemMonitorService(registry, event_bus, interval=60)
            data = await monitor.snapshot()
            health = monitor._health(data)
            assert health["status"] == "degraded"
            assert len(health["issues"]) >= 1


# ==========================================================================
# Event Publishing
# ==========================================================================


class TestEventPublishing:
    @pytest.mark.asyncio
    async def test_publishes_metrics(self, registry, event_bus, mock_psutil):
        received = []
        event_bus.subscribe("system.metrics", lambda **kw: received.append(kw))
        monitor = SystemMonitorService(registry, event_bus, interval=0.1)
        monitor.start()
        await asyncio.sleep(0.3)
        await monitor.stop()
        assert len(received) >= 1
        data = received[0].get("data", {})
        assert "cpu" in data

    @pytest.mark.asyncio
    async def test_publishes_health(self, registry, event_bus, mock_psutil):
        received = []
        event_bus.subscribe("system.health", lambda **kw: received.append(kw))
        monitor = SystemMonitorService(registry, event_bus, interval=0.1)
        monitor.start()
        await asyncio.sleep(0.3)
        await monitor.stop()
        assert len(received) >= 1
        assert "status" in received[0].get("data", {})

    @pytest.mark.asyncio
    async def test_no_warnings_normal(self, registry, event_bus, mock_psutil):
        warnings = []
        event_bus.subscribe("system.warning", lambda **kw: warnings.append(kw))
        monitor = SystemMonitorService(registry, event_bus, interval=0.1)
        monitor.start()
        await asyncio.sleep(0.3)
        await monitor.stop()
        assert len(warnings) == 0


# ==========================================================================
# Lifecycle
# ==========================================================================


class TestLifecycle:
    @pytest.mark.asyncio
    async def test_start_stop(self, registry, event_bus, mock_psutil):
        monitor = SystemMonitorService(registry, event_bus, interval=60)
        assert not monitor.running
        monitor.start()
        assert monitor.running
        await monitor.stop()
        assert not monitor.running

    @pytest.mark.asyncio
    async def test_start_idempotent(self, registry, event_bus, mock_psutil):
        monitor = SystemMonitorService(registry, event_bus, interval=60)
        monitor.start()
        task_id = id(monitor._task)
        monitor.start()
        assert id(monitor._task) == task_id
        await monitor.stop()

    @pytest.mark.asyncio
    async def test_stop_idempotent(self, registry, event_bus, mock_psutil):
        monitor = SystemMonitorService(registry, event_bus, interval=60)
        await monitor.stop()
        assert not monitor.running

    @pytest.mark.asyncio
    async def test_stop_cleans_up_task(self, registry, event_bus, mock_psutil):
        monitor = SystemMonitorService(registry, event_bus, interval=0.05)
        monitor.start()
        await asyncio.sleep(0.12)
        await monitor.stop()
        assert monitor._task is None or monitor._task.done()


# ==========================================================================
# Configurable Interval
# ==========================================================================


class TestConfigurableInterval:
    @pytest.mark.asyncio
    async def test_get_set_interval(self, registry, event_bus, mock_psutil):
        monitor = SystemMonitorService(registry, event_bus, interval=5.0)
        assert await monitor.get_interval() == 5.0
        await monitor.set_interval(10.0)
        assert await monitor.get_interval() == 10.0

    @pytest.mark.asyncio
    async def test_interval_affects_publish_rate(self, registry, event_bus, mock_psutil):
        received = []
        event_bus.subscribe("system.metrics", lambda **kw: received.append(kw))
        monitor = SystemMonitorService(registry, event_bus, interval=0.2)
        monitor.start()
        await asyncio.sleep(0.5)
        await monitor.stop()
        # With 0.2s interval, we expect 2-3 publishes in 0.5s
        assert 1 <= len(received) <= 4


# ==========================================================================
# Thread Safety / Concurrent Access
# ==========================================================================


class TestConcurrentAccess:
    @pytest.mark.asyncio
    async def test_concurrent_snapshots(self, registry, event_bus, mock_psutil):
        monitor = SystemMonitorService(registry, event_bus, interval=60)
        results = await asyncio.gather(
            monitor.snapshot(),
            monitor.snapshot(),
            monitor.snapshot(),
        )
        assert len(results) == 3
        for data in results:
            assert "cpu" in data

    @pytest.mark.asyncio
    async def test_concurrent_set_threshold(self, registry, event_bus, mock_psutil):
        monitor = SystemMonitorService(registry, event_bus, interval=60)
        await asyncio.gather(
            monitor.set_threshold("cpu_percent", 80.0),
            monitor.set_threshold("ram_percent", 85.0),
            monitor.set_threshold("disk_percent", 90.0),
        )
        thresholds = await monitor.get_thresholds()
        assert thresholds["cpu_percent"] == 80.0
        assert thresholds["ram_percent"] == 85.0
        assert thresholds["disk_percent"] == 90.0

    @pytest.mark.asyncio
    async def test_set_interval_during_run(self, registry, event_bus, mock_psutil):
        monitor = SystemMonitorService(registry, event_bus, interval=0.1)
        monitor.start()
        await monitor.set_interval(0.5)
        assert await monitor.get_interval() == 0.5
        await monitor.stop()


# ==========================================================================
# Service Cleanup
# ==========================================================================


class TestCleanup:
    @pytest.mark.asyncio
    async def test_stop_without_start(self, registry, event_bus, mock_psutil):
        monitor = SystemMonitorService(registry, event_bus, interval=60)
        await monitor.stop()
        assert not monitor.running

    @pytest.mark.asyncio
    async def test_stop_twice(self, registry, event_bus, mock_psutil):
        monitor = SystemMonitorService(registry, event_bus, interval=0.1)
        monitor.start()
        await monitor.stop()
        await monitor.stop()
        assert not monitor.running

    @pytest.mark.asyncio
    async def test_no_leaked_tasks(self, registry, event_bus, mock_psutil):
        monitor = SystemMonitorService(registry, event_bus, interval=0.05)
        monitor.start()
        await asyncio.sleep(0.15)
        await monitor.stop()
        await asyncio.sleep(0.05)
        tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        assert not any(t is monitor._task for t in tasks if t is not None)


# ==========================================================================
# WebSocket Integration
# ==========================================================================


class TestWebSocketIntegration:
    @pytest.mark.asyncio
    async def test_event_forwarded_to_subscribed_client(self, registry, event_bus, mock_psutil):
        """Verify that system.metrics events flow through EventBus to WS."""
        from app.ws.manager import WebSocketConnectionManager
        from app.ws.bridge import EventStreamBridge
        from unittest.mock import AsyncMock

        ws_mgr = WebSocketConnectionManager()
        bridge = EventStreamBridge(event_bus=event_bus, ws_manager=ws_mgr)
        bridge.start()

        ws = AsyncMock()
        ws.headers = {}
        await ws_mgr.connect(ws, client_id="monitor-test")
        await ws_mgr.subscribe("monitor-test", "system.metrics")

        monitor = SystemMonitorService(registry, event_bus, interval=0.1)
        monitor.start()
        await asyncio.sleep(0.3)
        await monitor.stop()
        bridge.stop()

        await asyncio.sleep(0.1)
        assert ws.send_json.await_count >= 1

    @pytest.mark.asyncio
    async def test_multiple_clients_receive_metrics(self, registry, event_bus, mock_psutil):
        from app.ws.manager import WebSocketConnectionManager
        from app.ws.bridge import EventStreamBridge
        from unittest.mock import AsyncMock

        ws_mgr = WebSocketConnectionManager()
        bridge = EventStreamBridge(event_bus=event_bus, ws_manager=ws_mgr)
        bridge.start()

        ws1 = AsyncMock()
        ws1.headers = {}
        ws2 = AsyncMock()
        ws2.headers = {}
        await ws_mgr.connect(ws1, client_id="mon-client-1")
        await ws_mgr.connect(ws2, client_id="mon-client-2")
        await ws_mgr.subscribe("mon-client-1", "system.metrics")
        await ws_mgr.subscribe("mon-client-2", "system.metrics")

        monitor = SystemMonitorService(registry, event_bus, interval=0.1)
        monitor.start()
        await asyncio.sleep(0.35)
        await monitor.stop()
        bridge.stop()

        await asyncio.sleep(0.1)
        assert ws1.send_json.await_count >= 1
        assert ws2.send_json.await_count >= 1

    @pytest.mark.asyncio
    async def test_unsubscribed_client_does_not_receive(self, registry, event_bus, mock_psutil):
        from app.ws.manager import WebSocketConnectionManager
        from app.ws.bridge import EventStreamBridge
        from unittest.mock import AsyncMock

        ws_mgr = WebSocketConnectionManager()
        bridge = EventStreamBridge(event_bus=event_bus, ws_manager=ws_mgr)
        bridge.start()

        ws = AsyncMock()
        ws.headers = {}
        await ws_mgr.connect(ws, client_id="no-sub")

        monitor = SystemMonitorService(registry, event_bus, interval=0.1)
        monitor.start()
        await asyncio.sleep(0.3)
        await monitor.stop()
        bridge.stop()

        await asyncio.sleep(0.1)
        assert ws.send_json.await_count == 0


# ==========================================================================
# Backward Compatibility
# ==========================================================================


class TestBackwardCompatibility:
    def test_ws_message_types_extended(self):
        from app.ws.schemas import WSMessageType
        assert WSMessageType.SYSTEM_METRICS.value == "system.metrics"
        assert WSMessageType.SYSTEM_HEALTH.value == "system.health"
        assert WSMessageType.SYSTEM_WARNING.value == "system.warning"

    @pytest.mark.asyncio
    async def test_health_endpoint_still_works(self):
        from app.api.server import create_app
        from fastapi.testclient import TestClient

        app = create_app()
        client = TestClient(app)
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200

    def test_system_monitor_registered(self):
        from app.monitor.service import SystemMonitorService
        svc = SystemMonitorService(
            registry=MagicMock(),
            event_bus=MagicMock(),
        )
        assert hasattr(svc, "start")
        assert hasattr(svc, "stop")
        assert hasattr(svc, "snapshot")
        assert hasattr(svc, "set_interval")
        assert hasattr(svc, "set_threshold")
        assert hasattr(svc, "get_interval")
        assert hasattr(svc, "get_thresholds")
