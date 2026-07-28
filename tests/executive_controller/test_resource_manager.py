from __future__ import annotations

import threading

import pytest

from app.executive_controller.resource_manager import ResourceManager, ResourceQuota, ResourceUsage


class TestResourceUsage:
    def test_to_dict_contains_keys(self) -> None:
        u = ResourceUsage()
        d = u.to_dict()
        assert "cpu_percent" in d
        assert "memory_percent" in d
        assert "memory_rss_bytes" in d
        assert "timestamp" in d

    def test_to_dict_returns_float_values(self) -> None:
        u = ResourceUsage(cpu_percent=12.5, memory_rss=1024)
        d = u.to_dict()
        assert d["cpu_percent"] == 12.5
        assert d["memory_rss_bytes"] == 1024


class TestResourceManager:
    def test_track_and_is_tracked(self) -> None:
        rm = ResourceManager()
        rm.track("component-a")
        assert rm.is_tracked("component-a") is True

    def test_not_tracked(self) -> None:
        rm = ResourceManager()
        assert rm.is_tracked("nothing") is False

    def test_untrack(self) -> None:
        rm = ResourceManager()
        rm.track("component-a")
        assert rm.untrack("component-a") is True
        assert rm.is_tracked("component-a") is False

    def test_untrack_missing_returns_false(self) -> None:
        rm = ResourceManager()
        assert rm.untrack("nothing") is False

    def test_get_tracked_components(self) -> None:
        rm = ResourceManager()
        rm.track("a")
        rm.track("b")
        assert sorted(rm.get_tracked_components()) == ["a", "b"]

    def test_get_usage_returns_usage_object(self) -> None:
        rm = ResourceManager()
        rm.track("test-1")
        usage = rm.get_usage("test-1")
        assert isinstance(usage, ResourceUsage)

    def test_get_system_usage(self) -> None:
        rm = ResourceManager()
        usage = rm.get_system_usage()
        assert usage.cpu_percent >= 0
        assert usage.timestamp > 0

    def test_set_and_get_quota(self) -> None:
        rm = ResourceManager()
        quota = ResourceQuota(cpu_percent_max=50.0, memory_mb_max=512.0)
        rm.set_quota("component-a", quota)
        retrieved = rm.get_quota("component-a")
        assert retrieved is not None
        assert retrieved.cpu_percent_max == 50.0
        assert retrieved.memory_mb_max == 512.0

    def test_get_quota_none_when_not_set(self) -> None:
        rm = ResourceManager()
        assert rm.get_quota("nothing") is None

    def test_remove_quota(self) -> None:
        rm = ResourceManager()
        rm.set_quota("a", ResourceQuota())
        assert rm.remove_quota("a") is True
        assert rm.get_quota("a") is None

    def test_remove_quota_missing(self) -> None:
        rm = ResourceManager()
        assert rm.remove_quota("nothing") is False

    def test_check_quota_no_violations(self) -> None:
        rm = ResourceManager()
        rm.track("test")
        violations = rm.check_quota("test")
        assert violations == []

    def test_check_quota_no_quota_set(self) -> None:
        rm = ResourceManager()
        rm.track("test")
        # No quota set means no violations
        assert rm.check_quota("test") == []

    def test_get_all_usage(self) -> None:
        rm = ResourceManager()
        rm.track("a")
        rm.track("b")
        all_u = rm.get_all_usage()
        assert "a" in all_u
        assert "b" in all_u

    def test_to_dict(self) -> None:
        rm = ResourceManager()
        rm.track("test")
        d = rm.to_dict()
        assert "tracked" in d
        assert "quotas" in d
        assert "system_usage" in d
        assert "test" in d["tracked"]

    def test_thread_safety(self) -> None:
        rm = ResourceManager()
        errors: list[Exception] = []

        def worker() -> None:
            for i in range(100):
                try:
                    cid = f"comp-{i}"
                    rm.track(cid)
                    rm.is_tracked(cid)
                    rm.get_usage(cid)
                    rm.untrack(cid)
                except Exception as e:
                    errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(errors) == 0
