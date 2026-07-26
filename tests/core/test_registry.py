from __future__ import annotations

import threading

import pytest

from app.core.registry import ServiceRegistry


class TestServiceRegistry:
    @pytest.fixture
    def registry(self):
        return ServiceRegistry()

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def test_register_stores_service(self, registry):
        registry.register("db", {"host": "localhost"})
        assert registry.get("db") == {"host": "localhost"}

    def test_register_multiple_services(self, registry):
        registry.register("a", 1)
        registry.register("b", 2)
        assert registry.get("a") == 1
        assert registry.get("b") == 2

    def test_register_duplicate_raises(self, registry):
        registry.register("svc", "first")
        with pytest.raises(ValueError, match="already registered"):
            registry.register("svc", "second")

    def test_register_preserves_original_on_duplicate(self, registry):
        registry.register("svc", "first")
        try:
            registry.register("svc", "second")
        except ValueError:
            pass
        assert registry.get("svc") == "first"

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def test_get_existing_service(self, registry):
        registry.register("logger", object())
        assert registry.get("logger") is not None

    def test_get_missing_raises(self, registry):
        with pytest.raises(KeyError, match="not found"):
            registry.get("nonexistent")

    def test_get_returns_exact_object(self, registry):
        obj = {"key": "val"}
        registry.register("cfg", obj)
        assert registry.get("cfg") is obj

    # ------------------------------------------------------------------
    # exists
    # ------------------------------------------------------------------

    def test_exists_returns_true(self, registry):
        registry.register("svc", 1)
        assert registry.exists("svc") is True

    def test_exists_returns_false(self, registry):
        assert registry.exists("missing") is False

    def test_exists_after_remove(self, registry):
        registry.register("svc", 1)
        registry.remove("svc")
        assert registry.exists("svc") is False

    # ------------------------------------------------------------------
    # remove
    # ------------------------------------------------------------------

    def test_remove_existing(self, registry):
        registry.register("svc", 1)
        registry.remove("svc")
        assert registry.exists("svc") is False

    def test_remove_missing_is_noop(self, registry):
        registry.remove("nonexistent")

    def test_remove_does_not_affect_others(self, registry):
        registry.register("a", 1)
        registry.register("b", 2)
        registry.remove("a")
        assert registry.get("b") == 2

    # ------------------------------------------------------------------
    # list_services
    # ------------------------------------------------------------------

    def test_list_services_empty(self, registry):
        assert registry.list_services() == []

    def test_list_services_returns_sorted(self, registry):
        registry.register("z", 1)
        registry.register("a", 2)
        registry.register("m", 3)
        assert registry.list_services() == ["a", "m", "z"]

    def test_list_services_after_remove(self, registry):
        registry.register("keep", 1)
        registry.register("remove", 2)
        registry.remove("remove")
        assert "remove" not in registry.list_services()

    # ------------------------------------------------------------------
    # Thread safety
    # ------------------------------------------------------------------

    def test_concurrent_register_unique_names(self, registry):
        """Multiple threads can register different services concurrently."""
        results: dict[str, bool] = {}
        lock = threading.Lock()

        def register_name(name: str):
            try:
                registry.register(name, name)
                with lock:
                    results[name] = True
            except Exception:
                with lock:
                    results[name] = False

        threads = [
            threading.Thread(target=register_name, args=(f"svc_{i}",))
            for i in range(20)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        for i in range(20):
            assert results.get(f"svc_{i}") is True
            assert registry.get(f"svc_{i}") == f"svc_{i}"

    def test_concurrent_reads_are_safe(self, registry):
        """Multiple concurrent readers do not raise."""
        registry.register("shared", 42)

        results: list[int] = []

        def read():
            results.append(registry.get("shared"))

        threads = [threading.Thread(target=read) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert all(v == 42 for v in results)

    def test_lock_is_reentrant(self, registry):
        """Internal methods can call each other without deadlock."""
        registry.register("svc", 42)
        registry._lock.acquire()
        try:
            assert registry.exists("svc") is True
            assert registry.get("svc") == 42
        finally:
            registry._lock.release()

    # ------------------------------------------------------------------
    # get_optional
    # ------------------------------------------------------------------

    def test_get_optional_returns_none_when_missing(self, registry):
        assert registry.get_optional("nonexistent") is None

    def test_get_optional_returns_service_when_exists(self, registry):
        registry.register("svc", 42)
        assert registry.get_optional("svc") == 42

    def test_get_optional_returns_exact_object(self, registry):
        obj = {"key": "val"}
        registry.register("cfg", obj)
        assert registry.get_optional("cfg") is obj

    def test_get_optional_does_not_raise(self, registry):
        registry.get_optional("missing")  # no exception

    def test_get_optional_is_thread_safe(self, registry):
        registry.register("safe", 99)
        results: list[int] = []

        def read():
            v = registry.get_optional("safe")
            results.append(v)

        threads = [threading.Thread(target=read) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert all(v == 99 for v in results)
        assert registry.get_optional("missing") is None

    def test_register_duplicate_under_contention(self, registry):
        """Only one thread succeeds when registering the same name."""
        registry.register("contended", "original")
        successes: list[int] = []

        def attempt():
            try:
                registry.register("contended", "new")
                successes.append(1)
            except ValueError:
                successes.append(0)

        threads = [threading.Thread(target=attempt) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert sum(successes) == 0
        assert registry.get("contended") == "original"
