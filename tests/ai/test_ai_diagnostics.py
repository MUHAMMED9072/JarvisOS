"""Tests for AI observability and diagnostics infrastructure."""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock, PropertyMock

import pytest

from app.ai.diagnostics import AIDiagnosticsService, MetricsCollector, ProviderStats
from app.ai.manager import AIManager
from app.ai.providers.base import AIProvider, AIResponse, ProviderCapability
from app.ai.router import AIRouter
from app.ai.routing import RoutingConfig
from app.core.config import Config


# ==========================================================================
# _ThreadSafeCounter tests (via MetricsCollector operations)
# ==========================================================================


class TestMetricsCollection:
    """Basic metrics recording, snapshot, and reset."""

    def test_successful_request_records_total_and_success(self):
        mc = MetricsCollector()
        mc.requests.record(True, 100.0)
        snap = mc.requests.snapshot()
        assert snap["total"] == 1
        assert snap["success"] == 1
        assert snap["failure"] == 0

    def test_failed_request_records_total_and_failure(self):
        mc = MetricsCollector()
        mc.requests.record(False)
        snap = mc.requests.snapshot()
        assert snap["total"] == 1
        assert snap["success"] == 0
        assert snap["failure"] == 1

    def test_latency_tracking(self):
        mc = MetricsCollector()
        mc.requests.record(True, 50.0)
        mc.requests.record(True, 150.0)
        mc.requests.record(True, 100.0)
        snap = mc.requests.snapshot()
        assert snap["total_latency_ms"] == 300.0
        assert snap["min_latency_ms"] == 50.0
        assert snap["max_latency_ms"] == 150.0

    def test_reset_clears_all_counters(self):
        mc = MetricsCollector()
        mc.requests.record(True, 50.0)
        mc.requests.reset()
        snap = mc.requests.snapshot()
        assert snap["total"] == 0
        assert snap["total_latency_ms"] == 0.0

    def test_snapshot_returns_all_operation_groups(self):
        mc = MetricsCollector()
        snap = mc.snapshot()
        expected_keys = {
            "requests", "routing", "streaming", "planning",
            "reasoning", "tools", "conversations", "memory",
            "errors", "retries", "providers",
            "uptime_seconds", "timestamp",
        }
        assert set(snap.keys()) == expected_keys
        assert snap["uptime_seconds"] >= 0
        assert snap["timestamp"] > 0


class TestThreadSafety:
    """Metrics collector is safe for concurrent access."""

    def test_concurrent_records(self):
        mc = MetricsCollector()
        n = 100
        barrier = threading.Barrier(n)
        results: list[Exception | None] = [None] * n

        def record(i: int) -> None:
            try:
                barrier.wait()
                mc.requests.record(True, float(i))
                mc.routing.record(i % 2 == 0, float(i))
                mc.streaming.record(True)
            except Exception as e:
                results[i] = e

        threads = [
            threading.Thread(target=record, args=(i,)) for i in range(n)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert all(r is None for r in results)
        snap = mc.snapshot()
        assert snap["requests"]["total"] == n


# ==========================================================================
# ProviderStats tests
# ==========================================================================


class TestProviderStats:
    """Per-provider metrics tracking."""

    def test_record_metrics(self):
        mc = MetricsCollector()
        mc.record_provider_request("test-provider", True, 50.0, 100, 50)
        mc.record_provider_request("test-provider", True, 30.0, 200, 100)
        snap = mc.snapshot()
        ps = snap["providers"]["test-provider"]
        assert ps["total_requests"] == 2
        assert ps["successful_requests"] == 2
        assert ps["total_latency_ms"] == 80.0
        assert ps["total_prompt_tokens"] == 300
        assert ps["total_completion_tokens"] == 150

    def test_provider_retry_tracking(self):
        mc = MetricsCollector()
        mc.record_provider_retry("test-provider", 1)
        mc.record_provider_retry("test-provider", 2)
        snap = mc.snapshot()
        assert snap["providers"]["test-provider"]["retry_count"] == 2

    def test_unknown_provider_returns_empty(self):
        mc = MetricsCollector()
        snap = mc.snapshot()
        assert "nonexistent" not in snap["providers"]

    def test_for_provider_creates_on_demand(self):
        mc = MetricsCollector()
        ps = mc.for_provider("auto-created")
        assert isinstance(ps, ProviderStats)
        snap = mc.snapshot()
        assert "auto-created" in snap["providers"]


# ==========================================================================
# MetricsCollector full snapshot & reset
# ==========================================================================


class TestMetricsCollector:
    """Full collector-level snapshot and reset."""

    def test_reset_clears_everything(self):
        mc = MetricsCollector()
        mc.requests.record(True)
        mc.routing.record(True)
        mc.streaming.record(False)
        mc.planning.record(True, 100.0)
        mc.reasoning.record(False)
        mc.tools.record(True)
        mc.conversations.record(True)
        mc.memory.record(False)
        mc.errors.record(True)
        mc.retries.record(True)
        mc.record_provider_request("p1", True, 50.0)

        mc.reset()

        snap = mc.snapshot()
        assert snap["requests"]["total"] == 0
        assert snap["routing"]["total"] == 0
        assert snap["streaming"]["total"] == 0
        assert snap["planning"]["total"] == 0
        assert snap["reasoning"]["total"] == 0
        assert snap["tools"]["total"] == 0
        assert snap["conversations"]["total"] == 0
        assert snap["memory"]["total"] == 0
        assert snap["errors"]["total"] == 0
        assert snap["retries"]["total"] == 0
        assert snap["providers"] == {}

    def test_multiple_records_aggregate_correctly(self):
        mc = MetricsCollector()
        for i in range(10):
            mc.requests.record(i % 2 == 0, float(i * 10))
        snap = mc.requests.snapshot()
        assert snap["total"] == 10
        assert snap["success"] == 5
        assert snap["failure"] == 5


# ==========================================================================
# AIDiagnosticsService tests
# ==========================================================================


class TestAIDiagnosticsService:
    """Diagnostics service snapshot and reset."""

    def test_snapshot_includes_features(self):
        ds = AIDiagnosticsService()
        snap = ds.snapshot()
        assert "features" in snap
        assert snap["features"]["streaming"] is True
        assert snap["features"]["planning"] is True
        assert snap["features"]["reasoning"] is True

    def test_snapshot_includes_uptime_and_timestamp(self):
        ds = AIDiagnosticsService()
        snap = ds.snapshot()
        assert snap["uptime_seconds"] >= 0
        assert snap["timestamp"] > 0

    def test_snapshot_with_router_health(self):
        mc = MetricsCollector()
        ds = AIDiagnosticsService(mc)
        router = MagicMock()
        router.providers = {"p1": MagicMock(), "p2": MagicMock()}
        router.provider_status.return_value = type("Status", (), {"name": "AVAILABLE"})()
        snap = ds.snapshot(router=router)
        assert "health" in snap
        assert "p1" in snap["health"]
        assert "p2" in snap["health"]

    def test_reset_clears_metrics(self):
        mc = MetricsCollector()
        ds = AIDiagnosticsService(mc)
        mc.requests.record(True, 50.0)
        ds.reset()
        snap = ds.snapshot()
        assert snap["requests"]["total"] == 0

    def test_metrics_property(self):
        mc = MetricsCollector()
        ds = AIDiagnosticsService(mc)
        assert ds.metrics is mc

    def test_default_metrics_created(self):
        ds = AIDiagnosticsService()
        assert ds.metrics is not None
        snap = ds.snapshot()
        assert snap["requests"]["total"] == 0


# ==========================================================================
# Integration: Metrics via AIManager.ask()
# ==========================================================================


class _MockProvider(AIProvider):
    def __init__(self, name: str = "mock"):
        self.provider_name = name
        self._model = "mock-model"

    def generate(self, prompt: str, **kwargs) -> AIResponse:
        return AIResponse(
            f"response to: {prompt}",
            provider=self.provider_name,
            model=self._model,
            latency_ms=10.0,
        )


class TestAIManagerMetrics:
    """AIManager records metrics via MetricsCollector."""

    @pytest.fixture
    def manager(self):
        mc = MetricsCollector()
        rc = RoutingConfig(providers=("mock",))
        router = AIRouter(routing_config=rc, metrics_collector=mc)
        router.providers = {"mock": _MockProvider("mock")}
        mgr = AIManager(router=router, metrics_collector=mc)
        return mc, mgr

    def test_ask_records_success(self, manager):
        mc, mgr = manager
        mgr.ask(provider="mock", prompt="hello")
        snap = mc.snapshot()
        assert snap["requests"]["total"] == 1
        assert snap["requests"]["success"] == 1
        assert snap["requests"]["total_latency_ms"] > 0

    def test_ask_records_failure(self, manager):
        mc, mgr = manager
        with pytest.raises(ValueError):
            mgr.ask(provider="nonexistent", prompt="hello")
        snap = mc.snapshot()
        assert snap["requests"]["total"] == 1
        assert snap["requests"]["failure"] == 1

    def test_ask_records_provider_metrics(self, manager):
        mc, mgr = manager
        mgr.ask(provider="mock", prompt="hello")
        snap = mc.snapshot()
        assert "mock" in snap["providers"]
        assert snap["providers"]["mock"]["total_requests"] == 1

    def test_ask_conversation_path_records_metrics(self, manager):
        mc, mgr = manager
        conv = mgr.create_conversation(
            provider="mock", model="mock-model",
        )
        mgr.ask(
            provider="mock", prompt="hello",
            conversation_id=conv.conversation_id,
        )
        snap = mc.snapshot()
        assert snap["requests"]["total"] == 1
        assert snap["requests"]["success"] == 1

    def test_ask_stream_records_streaming_metric(self, manager):
        mc, mgr = manager
        stream = mgr.ask_stream(provider="mock", prompt="hello")
        for _ in stream:
            pass
        snap = mc.snapshot()
        assert snap["streaming"]["total"] >= 1
        assert snap["streaming"]["success"] >= 1

    def test_plan_records_planning_metrics(self, manager):
        mc, mgr = manager
        result = mgr.plan("test objective", provider="mock")
        snap = mc.snapshot()
        assert snap["planning"]["total"] == 1

    def test_reason_records_reasoning_metrics(self, manager):
        mc, mgr = manager
        result = mgr.reason("test objective", provider="mock")
        snap = mc.snapshot()
        assert snap["reasoning"]["total"] == 1


# ==========================================================================
# Integration: Metrics via AIRouter
# ==========================================================================


class TestAIRouterMetrics:
    """AIRouter records routing and provider metrics."""

    @pytest.fixture
    def router(self):
        mc = MetricsCollector()
        rc = RoutingConfig(providers=("mock-a", "mock-b"))
        router = AIRouter(routing_config=rc, metrics_collector=mc)
        router.providers = {
            "mock-a": _MockProvider("mock-a"),
            "mock-b": _MockProvider("mock-b"),
        }
        return mc, router

    def test_ask_records_provider_metrics(self, router):
        mc, r = router
        r.ask("mock-a", "hello")
        snap = mc.snapshot()
        assert "mock-a" in snap["providers"]
        assert snap["providers"]["mock-a"]["total_requests"] == 1
        assert snap["providers"]["mock-a"]["successful_requests"] == 1

    def test_ask_routed_records_routing_metrics(self, router):
        mc, r = router
        r.ask_routed("hello")
        snap = mc.snapshot()
        assert snap["routing"]["total"] >= 1

    def test_ask_routed_failure_records_error(self, router):
        mc, r = router
        r.routing_config = RoutingConfig(providers=())
        with pytest.raises(ValueError):
            r.ask_routed("hello")
        snap = mc.snapshot()
        assert snap["routing"]["total"] >= 1
        assert snap["routing"]["failure"] >= 1

    def test_retry_tracking_via_decorator(self, router):
        mc, r = router
        mc.retries.record(True)
        snap = mc.snapshot()
        assert snap["retries"]["total"] == 1


# ==========================================================================
# Edge cases
# ==========================================================================


class TestEdgeCases:
    """Metrics collector handles edge cases gracefully."""

    def test_zero_latency_recorded(self):
        mc = MetricsCollector()
        mc.requests.record(True, 0.0)
        snap = mc.requests.snapshot()
        assert snap["total"] == 1
        assert snap["total_latency_ms"] == 0.0

    def test_single_record_min_equals_max(self):
        mc = MetricsCollector()
        mc.requests.record(True, 42.0)
        snap = mc.requests.snapshot()
        assert snap["min_latency_ms"] == 42.0
        assert snap["max_latency_ms"] == 42.0

    def test_metrics_collector_no_providers(self):
        mc = MetricsCollector()
        snap = mc.snapshot()
        assert snap["providers"] == {}

    def test_retries_counter_happy_path(self):
        mc = MetricsCollector()
        mc.record_retry(1, 3, "ProviderTimeoutError")
        snap = mc.snapshot()
        assert snap["retries"]["total"] == 1
