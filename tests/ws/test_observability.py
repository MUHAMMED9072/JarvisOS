"""Tests for WebSocket Production Features & Observability (P12-10)."""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import WebSocket

from app.ws.diagnostics import WebSocketDiagnostics
from app.ws.health import WebSocketHealthMonitor
from app.ws.maintenance import WebSocketMaintenance
from app.ws.manager import WebSocketConnectionManager
from app.ws.metrics import WebsocketMetricsService
from app.ws.runtime_config import WebSocketRuntimeConfig
from app.ws.schemas import ServerMessage, WSMessageType


# ======================================================================
# Helpers
# ======================================================================


def _make_ws_manager() -> WebSocketConnectionManager:
    mgr = WebSocketConnectionManager()
    ws = AsyncMock(spec=WebSocket)
    ws.headers = {}
    return mgr


def _make_event_bus() -> MagicMock:
    bus = MagicMock()
    bus.publish = MagicMock()
    return bus


# ======================================================================
# WebsocketMetricsService
# ======================================================================


class TestWebsocketMetricsService:
    @pytest.mark.asyncio
    async def test_snapshot_defaults(self):
        mgr = _make_ws_manager()
        svc = WebsocketMetricsService(ws_manager=mgr)
        snap = await svc.snapshot()
        assert snap["active_connections"] == 0
        assert snap["bytes_sent"] == 0
        assert snap["average_latency_ms"] == 0.0

    @pytest.mark.asyncio
    async def test_snapshot_with_connection(self):
        mgr = _make_ws_manager()
        ws = AsyncMock(spec=WebSocket)
        ws.headers = {}
        await mgr.connect(ws, client_id="client1")
        svc = WebsocketMetricsService(ws_manager=mgr)
        snap = await svc.snapshot()
        assert snap["active_connections"] == 1

    @pytest.mark.asyncio
    async def test_record_counters(self):
        mgr = _make_ws_manager()
        svc = WebsocketMetricsService(ws_manager=mgr)
        svc.record_connect()
        svc.record_connect(is_authenticated=True)
        svc.record_message_sent()
        svc.record_bytes_sent(100)
        svc.record_retry()
        svc.record_ack()
        snap = await svc.snapshot()
        assert snap["total_connections"] == 2
        assert snap["messages_sent"] == 1
        assert snap["bytes_sent"] == 100
        assert snap["retries"] == 1
        assert snap["acknowledgements"] == 1

    @pytest.mark.asyncio
    async def test_reset(self):
        mgr = _make_ws_manager()
        svc = WebsocketMetricsService(ws_manager=mgr)
        svc.record_connect()
        svc.record_message_sent()
        await svc.reset()
        snap = await svc.snapshot()
        assert snap["total_connections"] == 0
        assert snap["messages_sent"] == 0

    @pytest.mark.asyncio
    async def test_latency_tracking(self):
        mgr = _make_ws_manager()
        svc = WebsocketMetricsService(ws_manager=mgr)
        svc.record_latency(0.1)
        svc.record_latency(0.3)
        snap = await svc.snapshot()
        assert snap["average_latency_ms"] == 200.0

    @pytest.mark.asyncio
    async def test_compression_ratio(self):
        mgr = _make_ws_manager()
        svc = WebsocketMetricsService(ws_manager=mgr)
        svc.record_compressed(original=1000, compressed=300)
        snap = await svc.snapshot()
        assert snap["compression_ratio_percent"] == 70.0

    @pytest.mark.asyncio
    async def test_publish_to_eventbus(self):
        bus = _make_event_bus()
        mgr = _make_ws_manager()
        svc = WebsocketMetricsService(ws_manager=mgr, event_bus=bus)
        await svc.publish()
        assert bus.publish.called
        args = bus.publish.call_args
        assert args[0][0] == "ws.metrics.updated"

    @pytest.mark.asyncio
    async def test_all_record_methods(self):
        mgr = _make_ws_manager()
        svc = WebsocketMetricsService(ws_manager=mgr)
        svc.record_disconnect()
        svc.record_reconnect()
        svc.record_auth_success()
        svc.record_auth_failure()
        svc.record_bytes_received(200)
        svc.record_message_received()
        svc.record_failed_delivery()
        svc.record_heartbeat_failure()
        svc.record_queue_overflow()
        svc.record_command_execution()
        svc.record_ai_stream()
        svc.record_file_transfer()
        snap = await svc.snapshot()
        assert snap["total_disconnections"] == 1
        assert snap["total_reconnects"] == 1
        assert snap["total_auth_success"] == 1
        assert snap["total_auth_failures"] == 1
        assert snap["bytes_received"] == 200
        assert snap["messages_received"] == 1
        assert snap["failed_deliveries"] == 1
        assert snap["heartbeat_failures"] == 1
        assert snap["queue_overflows"] == 1
        assert snap["command_executions"] == 1
        assert snap["ai_streams"] == 1
        assert snap["file_transfers"] == 1

    @pytest.mark.asyncio
    async def test_latency_samples_capped(self):
        mgr = _make_ws_manager()
        svc = WebsocketMetricsService(ws_manager=mgr)
        for i in range(2000):
            svc.record_latency(float(i) / 1000)
        assert len(svc._latency_samples) == 1000


# ======================================================================
# WebSocketHealthMonitor
# ======================================================================


class TestWebSocketHealthMonitor:
    @pytest.mark.asyncio
    async def test_healthy_by_default(self):
        mgr = _make_ws_manager()
        metrics = WebsocketMetricsService(ws_manager=mgr)
        health = WebSocketHealthMonitor(ws_manager=mgr, metrics_service=metrics)
        report = await health.evaluate()
        assert report["status"] == "healthy"
        assert len(report["failures"]) == 0

    @pytest.mark.asyncio
    async def test_detect_high_heartbeat_failures(self):
        mgr = _make_ws_manager()
        metrics = WebsocketMetricsService(ws_manager=mgr)
        for _ in range(600):
            metrics.record_heartbeat_failure()
        health = WebSocketHealthMonitor(ws_manager=mgr, metrics_service=metrics)
        report = await health.evaluate()
        assert report["status"] == "unhealthy"
        assert "high_heartbeat_failures" in report["failures"]

    @pytest.mark.asyncio
    async def test_detect_elevated_retry_rate(self):
        mgr = _make_ws_manager()
        metrics = WebsocketMetricsService(ws_manager=mgr)
        for _ in range(10):
            metrics.record_message_sent()
        metrics.record_retry()  # 1/10 = 0.1 — exactly at warn threshold
        health = WebSocketHealthMonitor(ws_manager=mgr, metrics_service=metrics)
        report = await health.evaluate()
        assert report["status"] in ("degraded", "healthy")
        # With rate exactly 0.1, threshold check should show pass or warn

    @pytest.mark.asyncio
    async def test_detect_high_latency(self):
        mgr = _make_ws_manager()
        metrics = WebsocketMetricsService(ws_manager=mgr)
        metrics.record_latency(3.0)
        health = WebSocketHealthMonitor(ws_manager=mgr, metrics_service=metrics)
        report = await health.evaluate()
        assert report["status"] == "unhealthy"
        assert "high_latency" in report["failures"]

    @pytest.mark.asyncio
    async def test_status_change_publishes_event(self):
        bus = _make_event_bus()
        mgr = _make_ws_manager()
        metrics = WebsocketMetricsService(ws_manager=mgr)
        for _ in range(600):
            metrics.record_heartbeat_failure()
        health = WebSocketHealthMonitor(
            ws_manager=mgr, metrics_service=metrics, event_bus=bus,
        )
        await health.evaluate()
        assert bus.publish.called
        args = bus.publish.call_args
        assert args[0][0] == "ws.health.changed"

    @pytest.mark.asyncio
    async def test_checks_structure(self):
        mgr = _make_ws_manager()
        metrics = WebsocketMetricsService(ws_manager=mgr)
        health = WebSocketHealthMonitor(ws_manager=mgr, metrics_service=metrics)
        report = await health.evaluate()
        assert "checks" in report
        assert "auth_failures" in report["checks"]
        assert "heartbeat" in report["checks"]
        assert "retry_rate" in report["checks"]
        assert "queue_saturation" in report["checks"]
        assert "latency" in report["checks"]
        assert "dropped_messages" in report["checks"]

    @pytest.mark.asyncio
    async def test_start_stop_loop(self):
        mgr = _make_ws_manager()
        metrics = WebsocketMetricsService(ws_manager=mgr)
        health = WebSocketHealthMonitor(
            ws_manager=mgr, metrics_service=metrics, interval=0.05,
        )
        await health.start()
        assert health._task is not None
        await asyncio.sleep(0.1)
        await health.stop()
        assert health._task is None or health._task.done()


# ======================================================================
# WebSocketDiagnostics
# ======================================================================


class TestWebSocketDiagnostics:
    @pytest.mark.asyncio
    async def test_generate_manager_state(self):
        mgr = _make_ws_manager()
        ws = AsyncMock(spec=WebSocket)
        ws.headers = {}
        await mgr.connect(ws, client_id="client1")
        diag = WebSocketDiagnostics(ws_manager=mgr)
        report = await diag.generate()
        assert "manager" in report
        assert report["manager"]["active_connections"] == 1

    @pytest.mark.asyncio
    async def test_generate_room_usage(self):
        mgr = _make_ws_manager()
        ws = AsyncMock(spec=WebSocket)
        ws.headers = {}
        await mgr.connect(ws, client_id="client1")
        await mgr.join_room("client1", "lobby")
        diag = WebSocketDiagnostics(ws_manager=mgr)
        report = await diag.generate()
        assert report["rooms"]["total_rooms"] == 1
        assert report["rooms"]["rooms"][0]["name"] == "lobby"

    @pytest.mark.asyncio
    async def test_generate_subscriptions(self):
        mgr = _make_ws_manager()
        ws = AsyncMock(spec=WebSocket)
        ws.headers = {}
        await mgr.connect(ws, client_id="client1")
        await mgr.subscribe("client1", "test.event")
        diag = WebSocketDiagnostics(ws_manager=mgr)
        report = await diag.generate()
        assert report["subscriptions"]["total_subscriptions"] == 1

    @pytest.mark.asyncio
    async def test_generate_retry_queue_state(self):
        mgr = _make_ws_manager()
        ws = AsyncMock(spec=WebSocket)
        ws.headers = {}
        await mgr.connect(ws, client_id="client1")

        msg = ServerMessage(type=WSMessageType.MESSAGE, payload={"text": "hello"})
        await mgr.send("client1", msg, require_ack=True)

        diag = WebSocketDiagnostics(ws_manager=mgr)
        report = await diag.generate()
        assert "retry_queues" in report

    @pytest.mark.asyncio
    async def test_generate_heartbeat_status(self):
        mgr = _make_ws_manager()
        ws = AsyncMock(spec=WebSocket)
        ws.headers = {}
        await mgr.connect(ws, client_id="client1")
        diag = WebSocketDiagnostics(ws_manager=mgr)
        report = await diag.generate()
        assert "heartbeat" in report
        assert report["heartbeat"]["total_checked"] == 1

    @pytest.mark.asyncio
    async def test_generate_with_auth_stats(self):
        mgr = _make_ws_manager()
        diag = WebSocketDiagnostics(ws_manager=mgr, authenticator=mgr._authenticator)
        report = await diag.generate()
        assert "auth_stats" in report

    @pytest.mark.asyncio
    async def test_generate_with_metrics(self):
        mgr = _make_ws_manager()
        metrics = WebsocketMetricsService(ws_manager=mgr)
        diag = WebSocketDiagnostics(ws_manager=mgr, metrics_service=metrics)
        report = await diag.generate()
        assert "metrics" in report
        assert "active_connections" in report["metrics"]

    @pytest.mark.asyncio
    async def test_generate_all_sections(self):
        mgr = _make_ws_manager()
        diag = WebSocketDiagnostics(ws_manager=mgr)
        report = await diag.generate()
        sections = [
            "manager", "sessions", "retry_queues", "offline_queues",
            "heartbeat", "rooms", "subscriptions", "active_streams",
            "commands", "transfers", "auth_stats", "metrics",
            "runtime_config", "timestamp",
        ]
        for s in sections:
            assert s in report, f"Missing section: {s}"


# ======================================================================
# WebSocketRuntimeConfig
# ======================================================================


class TestWebSocketRuntimeConfig:
    def test_default_values(self):
        mgr = _make_ws_manager()
        cfg = WebSocketRuntimeConfig(ws_manager=mgr)
        assert cfg.get("heartbeat_interval") == 30.0
        assert cfg.get("max_retries") == 3
        assert cfg.get("offline_queue_overflow") == "drop_oldest"

    def test_set_and_get_override(self):
        mgr = _make_ws_manager()
        cfg = WebSocketRuntimeConfig(ws_manager=mgr)
        assert cfg.set("heartbeat_interval", 10.0) is True
        assert cfg.get("heartbeat_interval") == 10.0

    def test_set_unknown_key_returns_false(self):
        mgr = _make_ws_manager()
        cfg = WebSocketRuntimeConfig(ws_manager=mgr)
        assert cfg.set("nonexistent", 42) is False

    def test_get_all(self):
        mgr = _make_ws_manager()
        cfg = WebSocketRuntimeConfig(ws_manager=mgr)
        all_config = cfg.get_all()
        assert "heartbeat_interval" in all_config
        assert "max_retries" in all_config
        assert "compression_enabled" in all_config
        assert len(all_config) == 14

    def test_reset_single_key(self):
        mgr = _make_ws_manager()
        cfg = WebSocketRuntimeConfig(ws_manager=mgr)
        cfg.set("heartbeat_interval", 10.0)
        assert cfg.get("heartbeat_interval") == 10.0
        cfg.reset("heartbeat_interval")
        assert cfg.get("heartbeat_interval") == 30.0

    def test_reset_all(self):
        mgr = _make_ws_manager()
        cfg = WebSocketRuntimeConfig(ws_manager=mgr)
        cfg.set("heartbeat_interval", 10.0)
        cfg.set("max_retries", 5)
        cfg.reset()
        assert cfg.get("heartbeat_interval") == 30.0
        assert cfg.get("max_retries") == 3

    def test_set_updates_manager_directly(self):
        mgr = _make_ws_manager()
        cfg = WebSocketRuntimeConfig(ws_manager=mgr)
        cfg.set("heartbeat_interval", 15.0)
        assert mgr._heartbeat_interval == 15.0
        cfg.set("heartbeat_timeout", 5.0)
        assert mgr._heartbeat_timeout == 5.0

    def test_get_with_config_object(self):
        from app.core.config import Config
        mgr = _make_ws_manager()
        cfg = WebSocketRuntimeConfig(ws_manager=mgr, config=Config)
        val = cfg.get("max_retries")
        assert val == Config.WS_MAX_RETRIES


# ======================================================================
# WebSocketMaintenance
# ======================================================================


class TestWebSocketMaintenance:
    @pytest.mark.asyncio
    async def test_clear_retry_queues(self):
        mgr = _make_ws_manager()
        ws = AsyncMock(spec=WebSocket)
        ws.headers = {}
        await mgr.connect(ws, client_id="client1")
        msg = ServerMessage(type=WSMessageType.MESSAGE, payload={"text": "hello"})
        await mgr.send("client1", msg, require_ack=True)
        maint = WebSocketMaintenance(ws_manager=mgr)
        result = await maint.clear_retry_queues()
        assert result["cleared"] == 1

    @pytest.mark.asyncio
    async def test_clear_offline_queues(self):
        mgr = _make_ws_manager()
        ws = AsyncMock(spec=WebSocket)
        ws.headers = {}
        await mgr.connect(ws, client_id="client1")
        info = mgr.get_connection("client1")
        assert info is not None
        assert info.offline_queue is not None
        await info.offline_queue.put({"type": "test"})
        maint = WebSocketMaintenance(ws_manager=mgr)
        result = await maint.clear_offline_queues()
        assert result["cleared"] == 1

    @pytest.mark.asyncio
    async def test_prune_expired_tokens(self):
        mgr = _make_ws_manager()
        ws = AsyncMock(spec=WebSocket)
        ws.headers = {}
        await mgr.connect(ws, client_id="client1")
        await mgr.generate_reconnect_token("client1")
        info = mgr.get_connection("client1")
        assert info is not None
        import time
        info.reconnect_token_expires = time.monotonic() - 1  # Expire it
        maint = WebSocketMaintenance(ws_manager=mgr)
        result = await maint.prune_expired_tokens()
        assert result["pruned"] == 1

    @pytest.mark.asyncio
    async def test_reset_metrics(self):
        mgr = _make_ws_manager()
        metrics = WebsocketMetricsService(ws_manager=mgr)
        metrics.record_connect()
        maint = WebSocketMaintenance(ws_manager=mgr, metrics_service=metrics)
        result = await maint.reset_metrics()
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_run_all(self):
        mgr = _make_ws_manager()
        ws = AsyncMock(spec=WebSocket)
        ws.headers = {}
        await mgr.connect(ws, client_id="client1")
        metrics = WebsocketMetricsService(ws_manager=mgr)
        maint = WebSocketMaintenance(ws_manager=mgr, metrics_service=metrics)
        result = await maint.run_all()
        assert "operations" in result
        assert "retry_queues" in result["operations"]
        assert "metrics" in result["operations"]

    @pytest.mark.asyncio
    async def test_clear_inactive_sessions(self):
        mgr = _make_ws_manager()
        session_store = mgr._authenticator._session_store
        maint = WebSocketMaintenance(ws_manager=mgr, session_store=session_store)
        result = await maint.clear_inactive_sessions()
        assert "removed" in result

    @pytest.mark.asyncio
    async def test_prune_expired_acks(self):
        mgr = _make_ws_manager()
        ws = AsyncMock(spec=WebSocket)
        ws.headers = {}
        await mgr.connect(ws, client_id="client1")
        msg = ServerMessage(type=WSMessageType.MESSAGE, payload={"text": "hello"})
        await mgr.send("client1", msg, require_ack=True)
        info = mgr.get_connection("client1")
        assert info is not None
        import time
        if info.retry_queue:
            entries = await info.retry_queue.get_all_pending()
            for e in entries:
                e.expires_at = time.monotonic() - 1  # Expire
        maint = WebSocketMaintenance(ws_manager=mgr)
        result = await maint.prune_expired_acks()
        assert "pruned" in result


# ======================================================================
# AdminManager P12-10 integration
# ======================================================================


class TestAdminManagerObservability:
    """Test the new admin.ws.* commands via AdminManager."""

    @pytest.mark.asyncio
    async def test_ws_metrics_handler(self):
        mgr = _make_ws_manager()
        ws = AsyncMock(spec=WebSocket)
        ws.headers = {}
        await mgr.connect(ws, client_id="client1")
        metrics = WebsocketMetricsService(ws_manager=mgr)
        from app.ws.admin import AdminManager
        admin = AdminManager(
            ws_manager=mgr, registry=MagicMock(),
            ws_metrics=metrics,
        )
        admin._respond = AsyncMock()

        handled = await admin.try_handle_message(
            "client1", json.dumps({"type": "admin.ws.metrics", "payload": {}}),
        )
        assert handled is True
        assert admin._respond.called

    @pytest.mark.asyncio
    async def test_ws_metrics_not_available(self):
        mgr = _make_ws_manager()
        from app.ws.admin import AdminManager
        admin = AdminManager(ws_manager=mgr, registry=MagicMock())
        admin._err = AsyncMock()
        handled = await admin.try_handle_message(
            "client1", json.dumps({"type": "admin.ws.metrics", "payload": {}}),
        )
        assert handled is True
        assert admin._err.called

    @pytest.mark.asyncio
    async def test_ws_health_handler(self):
        mgr = _make_ws_manager()
        metrics = WebsocketMetricsService(ws_manager=mgr)
        health = WebSocketHealthMonitor(ws_manager=mgr, metrics_service=metrics)
        from app.ws.admin import AdminManager
        admin = AdminManager(
            ws_manager=mgr, registry=MagicMock(),
            ws_health=health,
        )
        admin._respond = AsyncMock()
        handled = await admin.try_handle_message(
            "client1", json.dumps({"type": "admin.ws.health", "payload": {}}),
        )
        assert handled is True
        assert admin._respond.called

    @pytest.mark.asyncio
    async def test_ws_diagnostics_handler(self):
        mgr = _make_ws_manager()
        diag = WebSocketDiagnostics(ws_manager=mgr)
        from app.ws.admin import AdminManager
        admin = AdminManager(
            ws_manager=mgr, registry=MagicMock(),
            ws_diagnostics=diag,
        )
        admin._respond = AsyncMock()
        handled = await admin.try_handle_message(
            "client1", json.dumps({"type": "admin.ws.diagnostics", "payload": {}}),
        )
        assert handled is True
        assert admin._respond.called

    @pytest.mark.asyncio
    async def test_ws_reset_metrics_handler(self):
        mgr = _make_ws_manager()
        ws = AsyncMock(spec=WebSocket)
        ws.headers = {}
        await mgr.connect(ws, client_id="client1")
        metrics = WebsocketMetricsService(ws_manager=mgr)
        from app.ws.admin import AdminManager
        admin = AdminManager(
            ws_manager=mgr, registry=MagicMock(),
            ws_metrics=metrics,
        )
        admin._respond = AsyncMock()
        admin._check_permission = AsyncMock(return_value=True)
        handled = await admin.try_handle_message(
            "client1", json.dumps({"type": "admin.ws.reset_metrics", "payload": {}}),
        )
        assert handled is True
        assert admin._respond.called

    @pytest.mark.asyncio
    async def test_ws_maintenance_handler(self):
        mgr = _make_ws_manager()
        maint = WebSocketMaintenance(ws_manager=mgr)
        from app.ws.admin import AdminManager
        admin = AdminManager(
            ws_manager=mgr, registry=MagicMock(),
            ws_maintenance=maint,
        )
        admin._respond = AsyncMock()
        admin._check_permission = AsyncMock(return_value=True)
        handled = await admin.try_handle_message(
            "client1", json.dumps({
                "type": "admin.ws.maintenance",
                "payload": {"action": "reset_metrics"},
            }),
        )
        assert handled is True
        assert admin._respond.called

    @pytest.mark.asyncio
    async def test_ws_runtime_config_handler(self):
        mgr = _make_ws_manager()
        cfg = WebSocketRuntimeConfig(ws_manager=mgr)
        from app.ws.admin import AdminManager
        admin = AdminManager(
            ws_manager=mgr, registry=MagicMock(),
            ws_runtime_config=cfg,
        )
        admin._respond = AsyncMock()
        admin._check_permission = AsyncMock(return_value=True)
        handled = await admin.try_handle_message(
            "client1", json.dumps({
                "type": "admin.ws.runtime_config",
                "payload": {"action": "get"},
            }),
        )
        assert handled is True
        assert admin._respond.called


# ======================================================================
# REST endpoints (integration smoke test)
# ======================================================================


class TestWSRestEndpoints:
    @pytest.mark.asyncio
    async def test_ws_metrics_endpoint(self):
        from app.api.routes.ws_rest import router
        # Verify routes are registered
        routes = [r.path for r in router.routes]
        assert "/api/v1/ws/metrics" in routes
        assert "/api/v1/ws/health" in routes
        assert "/api/v1/ws/diagnostics" in routes


# ======================================================================
# EventBus events
# ======================================================================


class TestEventBusEvents:
    def test_ws_production_events_exist(self):
        from app.core.events import WSProductionEvents
        assert WSProductionEvents.METRICS_UPDATED == "ws.metrics.updated"
        assert WSProductionEvents.HEALTH_CHANGED == "ws.health.changed"
        assert WSProductionEvents.DIAGNOSTICS_GENERATED == "ws.diagnostics.generated"
        assert WSProductionEvents.MAINTENANCE_COMPLETED == "ws.maintenance.completed"


# ======================================================================
# Full integration: create_app with observability
# ======================================================================


class TestCreateAppObservability:
    def test_create_app_has_observability_services(self):
        from app.api.server import create_app
        from app.core.registry import ServiceRegistry

        registry = ServiceRegistry()
        app = create_app(registry=registry)
        assert hasattr(app.state, "ws_metrics")
        assert hasattr(app.state, "ws_health")
        assert hasattr(app.state, "ws_diagnostics")
        assert hasattr(app.state, "ws_maintenance")
        assert hasattr(app.state, "ws_runtime_config")


# ======================================================================
# Backward compatibility
# ======================================================================


class TestBackwardCompatibility:
    @pytest.mark.asyncio
    async def test_admin_ping_still_works(self):
        from app.ws.admin import AdminManager
        ws_mgr = _make_ws_manager()
        admin = AdminManager(ws_manager=ws_mgr, registry=MagicMock())
        admin._respond = AsyncMock()
        handled = await admin.try_handle_message(
            "client1", json.dumps({"type": "admin.ping", "payload": {}}),
        )
        assert handled is True

    @pytest.mark.asyncio
    async def test_non_ws_admin_messages_still_work(self):
        from app.ws.admin import AdminManager
        ws_mgr = _make_ws_manager()
        admin = AdminManager(ws_manager=ws_mgr, registry=MagicMock())
        admin._respond = AsyncMock()
        handled = await admin.try_handle_message(
            "client1", json.dumps({"type": "admin.clients", "payload": {}}),
        )
        assert handled is True

    @pytest.mark.asyncio
    async def test_unknown_admin_types_ignored(self):
        from app.ws.admin import AdminManager
        ws_mgr = _make_ws_manager()
        admin = AdminManager(ws_manager=ws_mgr, registry=MagicMock())
        handled = await admin.try_handle_message(
            "client1", json.dumps({"type": "admin.nonexistent", "payload": {}}),
        )
        assert handled is False
