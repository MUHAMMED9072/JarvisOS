"""Tests for kernel ServiceRegistry with lifecycle support."""

from __future__ import annotations

import threading
from unittest.mock import MagicMock

import pytest

from app.core.registry import ServiceLifecycle, ServiceRegistry


class TestServiceLifecycle:
    def test_on_startup_runs_callbacks_in_order(self):
        lc = ServiceLifecycle()
        order: list[int] = []

        lc.on_startup(lambda: order.append(1))
        lc.on_startup(lambda: order.append(2))
        lc.run_startup()
        assert order == [1, 2]

    def test_on_shutdown_runs_callbacks_in_reverse_order(self):
        lc = ServiceLifecycle()
        order: list[int] = []

        lc.on_shutdown(lambda: order.append(1))
        lc.on_shutdown(lambda: order.append(2))
        lc.run_shutdown()
        assert order == [2, 1]

    def test_run_startup_no_callbacks(self):
        lc = ServiceLifecycle()
        lc.run_startup()

    def test_run_shutdown_no_callbacks(self):
        lc = ServiceLifecycle()
        lc.run_shutdown()

    def test_startup_and_shutdown_independent(self):
        lc = ServiceLifecycle()
        startup_called = False
        shutdown_called = False

        lc.on_startup(lambda: setattr(lc, "_s", True))
        lc.on_shutdown(lambda: setattr(lc, "_sd", True))
        lc.run_startup()
        assert lc._s is True
        lc.run_shutdown()
        assert lc._sd is True

    def test_multiple_startup_callbacks_all_run(self):
        lc = ServiceLifecycle()
        calls: list[int] = []

        for i in range(5):
            lc.on_startup(lambda i=i: calls.append(i))

        lc.run_startup()
        assert calls == list(range(5))


class TestServiceRegistryLifecycle:
    @pytest.fixture
    def registry(self):
        return ServiceRegistry()

    def test_register_lifecycle_after_service(self, registry):
        registry.register("svc", "value")
        lc = ServiceLifecycle()
        registry.register_lifecycle("svc", lc)
        assert registry.get_lifecycle("svc") is lc

    def test_register_lifecycle_missing_service_raises(self, registry):
        lc = ServiceLifecycle()
        with pytest.raises(KeyError, match="not found"):
            registry.register_lifecycle("nonexistent", lc)

    def test_get_lifecycle_none_when_not_registered(self, registry):
        registry.register("svc", "value")
        assert registry.get_lifecycle("svc") is None

    def test_start_all_runs_lifecycle_startups(self, registry):
        registry.register("a", MagicMock())
        registry.register("b", MagicMock())

        lc_a = ServiceLifecycle()
        lc_b = ServiceLifecycle()
        cb_a = MagicMock()
        cb_b = MagicMock()
        lc_a.on_startup(cb_a)
        lc_b.on_startup(cb_b)
        registry.register_lifecycle("a", lc_a)
        registry.register_lifecycle("b", lc_b)

        registry.start_all()
        cb_a.assert_called_once()
        cb_b.assert_called_once()

    def test_shutdown_all_in_reverse_order(self, registry):
        registry.register("a", MagicMock())
        registry.register("b", MagicMock())

        lc_a = ServiceLifecycle()
        lc_b = ServiceLifecycle()
        order: list[str] = []
        lc_a.on_shutdown(lambda: order.append("a"))
        lc_b.on_shutdown(lambda: order.append("b"))
        registry.register_lifecycle("a", lc_a)
        registry.register_lifecycle("b", lc_b)

        registry.start_all()
        registry.shutdown_all()
        assert order == ["b", "a"]

    def test_shutdown_failure_is_isolated(self, registry):
        registry.register("a", MagicMock())
        registry.register("b", MagicMock())

        lc_a = ServiceLifecycle()
        lc_b = ServiceLifecycle()
        lc_a.on_shutdown(lambda: (_ for _ in ()).throw(RuntimeError("fail")))
        cb_b = MagicMock()
        lc_b.on_shutdown(cb_b)
        registry.register_lifecycle("a", lc_a)
        registry.register_lifecycle("b", lc_b)

        registry.start_all()
        registry.shutdown_all()
        cb_b.assert_called_once()

    def test_start_all_no_lifecycles(self, registry):
        registry.register("a", MagicMock())
        registry.start_all()

    def test_shutdown_all_no_lifecycles(self, registry):
        registry.register("a", MagicMock())
        registry.start_all()
        registry.shutdown_all()

    def test_lifecycle_removed_with_service(self, registry):
        registry.register("svc", "value")
        lc = ServiceLifecycle()
        registry.register_lifecycle("svc", lc)
        registry.remove("svc")
        assert registry.get_lifecycle("svc") is None

    def test_startup_order_matches_registration_order(self, registry):
        registry.register("first", MagicMock())
        registry.register("second", MagicMock())

        lc1 = ServiceLifecycle()
        lc2 = ServiceLifecycle()
        order: list[str] = []
        lc1.on_startup(lambda: order.append("first"))
        lc2.on_startup(lambda: order.append("second"))
        registry.register_lifecycle("first", lc1)
        registry.register_lifecycle("second", lc2)

        registry.start_all()
        assert order == ["first", "second"]


class TestKernelModule:
    def test_import_kernel_module(self):
        from app.kernel import EventBus  # noqa: F811

        assert EventBus is not None

    def test_import_events(self):
        from app.kernel import AIEvents, KernelEvents, SystemEvents

        assert AIEvents.REQUEST == "ai.request"
        assert KernelEvents.BOOT_STARTED == "kernel.boot.started"
        assert SystemEvents.HEALTH_CHECK == "system.health.check"

    def test_import_registry(self):
        from app.kernel import ServiceLifecycle, ServiceRegistry

        assert ServiceLifecycle is not None
        assert ServiceRegistry is not None
