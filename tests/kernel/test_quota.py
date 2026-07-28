"""Tests for the kernel resource quota system."""

from __future__ import annotations

import threading
import time

import pytest

from app.kernel.security.quota import QuotaExceeded, QuotaRegistry, QuotaResult, ResourceQuota, ResourceType


class TestResourceQuota:
    def test_is_unlimited_by_default(self):
        q = ResourceQuota(resource_type=ResourceType.CPU)
        assert q.is_unlimited() is True

    def test_is_unlimited_false_when_hard_limit_set(self):
        q = ResourceQuota(resource_type=ResourceType.CPU, hard_limit=100.0)
        assert q.is_unlimited() is False

    def test_is_exceeded_true(self):
        q = ResourceQuota(resource_type=ResourceType.CPU, hard_limit=100.0)
        q.current_usage = 101.0
        assert q.is_exceeded() is True

    def test_is_exceeded_false(self):
        q = ResourceQuota(resource_type=ResourceType.CPU, hard_limit=100.0)
        q.current_usage = 50.0
        assert q.is_exceeded() is False

    def test_is_exceeded_unlimited(self):
        q = ResourceQuota(resource_type=ResourceType.CPU)
        q.current_usage = 999999.0
        assert q.is_exceeded() is False

    def test_is_warning_true(self):
        q = ResourceQuota(resource_type=ResourceType.CPU, soft_limit=80.0, hard_limit=100.0)
        q.current_usage = 90.0
        assert q.is_warning() is True

    def test_is_warning_false(self):
        q = ResourceQuota(resource_type=ResourceType.CPU, soft_limit=80.0)
        q.current_usage = 50.0
        assert q.is_warning() is False

    def test_record_increases_usage(self):
        q = ResourceQuota(resource_type=ResourceType.CPU)
        q.record(10.0)
        assert q.current_usage == 10.0
        q.record(5.0)
        assert q.current_usage == 15.0

    def test_record_updates_peak(self):
        q = ResourceQuota(resource_type=ResourceType.CPU)
        q.record(10.0)
        assert q.peak_usage == 10.0
        q.record(5.0)
        assert q.peak_usage == 15.0
        q.record(2.0)
        assert q.peak_usage == 17.0

    def test_reset_clears_usage(self):
        q = ResourceQuota(resource_type=ResourceType.CPU)
        q.record(50.0)
        q.reset()
        assert q.current_usage == 0.0
        assert q.peak_usage == 50.0  # peak preserved

    def test_to_dict(self):
        q = ResourceQuota(resource_type=ResourceType.MEMORY, soft_limit=500.0, hard_limit=1000.0)
        d = q.to_dict()
        assert d["resource_type"] == "memory"
        assert d["soft_limit"] == 500.0
        assert d["hard_limit"] == 1000.0


class TestQuotaRegistry:
    @pytest.fixture
    def registry(self):
        return QuotaRegistry()

    def test_set_default(self, registry):
        q = ResourceQuota(resource_type=ResourceType.CPU, hard_limit=100.0)
        registry.set_default(q)
        assert registry.get_default(ResourceType.CPU) is q

    def test_get_default_none(self, registry):
        assert registry.get_default(ResourceType.CPU) is None

    def test_set_quota(self, registry):
        q = ResourceQuota(resource_type=ResourceType.CPU, hard_limit=50.0)
        registry.set_quota("alice", q)
        retrieved = registry.get_quota("alice", ResourceType.CPU)
        assert retrieved.hard_limit == 50.0

    def test_get_quota_falls_back_to_default(self, registry):
        default = ResourceQuota(resource_type=ResourceType.CPU, hard_limit=100.0)
        registry.set_default(default)
        q = registry.get_quota("alice", ResourceType.CPU)
        assert q.hard_limit == 100.0

    def test_get_quota_creates_unlimited_when_no_default(self, registry):
        q = registry.get_quota("alice", ResourceType.CPU)
        assert q.is_unlimited() is True

    def test_remove_actor(self, registry):
        registry.set_quota("alice", ResourceQuota(resource_type=ResourceType.CPU))
        registry.remove_actor("alice")
        assert "alice" not in registry.list_actors()

    def test_list_actors(self, registry):
        registry.set_quota("alice", ResourceQuota(resource_type=ResourceType.CPU))
        registry.set_quota("bob", ResourceQuota(resource_type=ResourceType.MEMORY))
        assert "alice" in registry.list_actors()
        assert "bob" in registry.list_actors()

    def test_check_allows_unlimited(self, registry):
        result = registry.check("alice", ResourceType.CPU, amount=999999.0)
        assert result.allowed is True

    def test_check_blocks_exceeded(self, registry):
        q = ResourceQuota(resource_type=ResourceType.CPU, hard_limit=100.0)
        registry.set_quota("alice", q)
        result = registry.check("alice", ResourceType.CPU, amount=101.0)
        assert result.allowed is False
        assert result.exceeded is True

    def test_check_warns_before_exceeded(self, registry):
        q = ResourceQuota(resource_type=ResourceType.CPU, soft_limit=80.0, hard_limit=100.0)
        q.current_usage = 70.0
        registry.set_quota("alice", q)
        result = registry.check("alice", ResourceType.CPU, amount=15.0)
        assert result.allowed is True
        assert result.warning is True

    def test_consume_raises_on_exceeded(self, registry):
        q = ResourceQuota(resource_type=ResourceType.CPU, hard_limit=100.0)
        q.current_usage = 95.0
        registry.set_quota("alice", q)
        with pytest.raises(QuotaExceeded) as exc:
            registry.consume("alice", ResourceType.CPU, amount=10.0)
        assert exc.value.actor == "alice"
        assert exc.value.resource_type == ResourceType.CPU

    def test_consume_records_usage(self, registry):
        q = ResourceQuota(resource_type=ResourceType.CPU, hard_limit=100.0)
        registry.set_quota("alice", q)
        registry.consume("alice", ResourceType.CPU, amount=10.0)
        registry.consume("alice", ResourceType.CPU, amount=20.0)
        q2 = registry.get_quota("alice", ResourceType.CPU)
        assert q2.current_usage == 30.0

    def test_consume_returns_result(self, registry):
        q = ResourceQuota(resource_type=ResourceType.CPU, hard_limit=100.0)
        registry.set_quota("alice", q)
        result = registry.consume("alice", ResourceType.CPU, amount=10.0)
        assert result.allowed is True
        assert result.resource_type == ResourceType.CPU

    def test_reset_actor(self, registry):
        q = ResourceQuota(resource_type=ResourceType.CPU, hard_limit=100.0)
        q.current_usage = 50.0
        registry.set_quota("alice", q)
        registry.reset_actor("alice")
        q2 = registry.get_quota("alice", ResourceType.CPU)
        assert q2.current_usage == 0.0

    def test_reset_all(self, registry):
        q1 = ResourceQuota(resource_type=ResourceType.CPU, hard_limit=100.0)
        q1.current_usage = 50.0
        q2 = ResourceQuota(resource_type=ResourceType.MEMORY, hard_limit=500.0)
        q2.current_usage = 200.0
        registry.set_quota("alice", q1)
        registry.set_quota("alice", q2)
        registry.reset_all()
        assert registry.get_quota("alice", ResourceType.CPU).current_usage == 0.0
        assert registry.get_quota("alice", ResourceType.MEMORY).current_usage == 0.0

    def test_get_stats(self, registry):
        q = ResourceQuota(resource_type=ResourceType.CPU, hard_limit=100.0)
        q.current_usage = 30.0
        registry.set_quota("alice", q)
        stats = registry.get_stats("alice")
        assert "cpu" in stats
        assert stats["cpu"]["current_usage"] == 30.0
        assert stats["cpu"]["hard_limit"] == 100.0

    def test_get_stats_empty_actor(self, registry):
        stats = registry.get_stats("nonexistent")
        assert stats == {}

    def test_window_reset(self, registry):
        q = ResourceQuota(resource_type=ResourceType.API_CALLS, hard_limit=100.0, window_seconds=0.01)
        q.current_usage = 50.0
        registry.set_quota("alice", q)
        time.sleep(0.02)
        # Check triggers window reset
        result = registry.check("alice", ResourceType.API_CALLS, amount=10.0)
        q2 = registry.get_quota("alice", ResourceType.API_CALLS)
        assert q2.current_usage == 0.0
        assert result.allowed is True

    def test_thread_safe_concurrent_ops(self, registry):
        def set_and_check(i):
            q = ResourceQuota(resource_type=ResourceType.CPU, hard_limit=1000.0)
            registry.set_quota(f"user-{i}", q)
            result = registry.check(f"user-{i}", ResourceType.CPU, amount=10.0)
            assert result.allowed is True

        threads = [threading.Thread(target=set_and_check, args=(i,)) for i in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(registry.list_actors()) == 50


class TestQuotaResult:
    def test_default_allowed_true(self):
        result = QuotaResult(allowed=True)
        assert result.allowed is True

    def test_exceeded_result(self):
        result = QuotaResult(allowed=False, exceeded=True, resource_type=ResourceType.CPU, current_usage=100.0, hard_limit=50.0)
        assert result.exceeded is True
        assert result.resource_type == ResourceType.CPU

    def test_warning_result(self):
        result = QuotaResult(allowed=True, warning=True)
        assert result.warning is True


class TestQuotaExceeded:
    def test_exception_attributes(self):
        exc = QuotaExceeded("alice", ResourceType.CPU, 100.0, 150.0)
        assert exc.actor == "alice"
        assert exc.resource_type == ResourceType.CPU
        assert exc.limit == 100.0
        assert exc.current == 150.0
        assert "alice" in str(exc)
        assert "cpu" in str(exc)
