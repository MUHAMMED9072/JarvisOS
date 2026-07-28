"""Tests for kernel event name constants."""

from __future__ import annotations

from app.kernel.events import AIEvents, KernelEvents, LifecycleEvents, SystemEvents


class TestKernelEvents:
    def test_boot_started(self):
        assert KernelEvents.BOOT_STARTED == "kernel.boot.started"

    def test_boot_complete(self):
        assert KernelEvents.BOOT_COMPLETE == "kernel.boot.complete"

    def test_boot_failed(self):
        assert KernelEvents.BOOT_FAILED == "kernel.boot.failed"

    def test_shutdown_started(self):
        assert KernelEvents.SHUTDOWN_STARTED == "kernel.shutdown.started"

    def test_shutdown_complete(self):
        assert KernelEvents.SHUTDOWN_COMPLETE == "kernel.shutdown.complete"

    def test_all_events_are_strings(self):
        for attr in dir(KernelEvents):
            if not attr.startswith("_"):
                assert isinstance(getattr(KernelEvents, attr), str)

    def test_no_duplicate_values(self):
        values = {
            getattr(KernelEvents, attr)
            for attr in dir(KernelEvents)
            if not attr.startswith("_")
        }
        assert len(values) == sum(
            1 for attr in dir(KernelEvents) if not attr.startswith("_")
        )


class TestSystemEvents:
    def test_health_check(self):
        assert SystemEvents.HEALTH_CHECK == "system.health.check"

    def test_health_ok(self):
        assert SystemEvents.HEALTH_OK == "system.health.ok"

    def test_health_degraded(self):
        assert SystemEvents.HEALTH_DEGRADED == "system.health.degraded"

    def test_health_failed(self):
        assert SystemEvents.HEALTH_FAILED == "system.health.failed"

    def test_config_changed(self):
        assert SystemEvents.CONFIG_CHANGED == "system.config.changed"

    def test_config_reloaded(self):
        assert SystemEvents.CONFIG_RELOADED == "system.config.reloaded"

    def test_all_events_are_strings(self):
        for attr in dir(SystemEvents):
            if not attr.startswith("_"):
                assert isinstance(getattr(SystemEvents, attr), str)

    def test_no_duplicate_values(self):
        values = {
            getattr(SystemEvents, attr)
            for attr in dir(SystemEvents)
            if not attr.startswith("_")
        }
        assert len(values) == sum(
            1 for attr in dir(SystemEvents) if not attr.startswith("_")
        )


class TestLifecycleEvents:
    def test_service_registered(self):
        assert LifecycleEvents.SERVICE_REGISTERED == "lifecycle.service.registered"

    def test_service_starting(self):
        assert LifecycleEvents.SERVICE_STARTING == "lifecycle.service.starting"

    def test_service_started(self):
        assert LifecycleEvents.SERVICE_STARTED == "lifecycle.service.started"

    def test_service_stopping(self):
        assert LifecycleEvents.SERVICE_STOPPING == "lifecycle.service.stopping"

    def test_service_stopped(self):
        assert LifecycleEvents.SERVICE_STOPPED == "lifecycle.service.stopped"

    def test_service_failed(self):
        assert LifecycleEvents.SERVICE_FAILED == "lifecycle.service.failed"

    def test_all_events_are_strings(self):
        for attr in dir(LifecycleEvents):
            if not attr.startswith("_"):
                assert isinstance(getattr(LifecycleEvents, attr), str)

    def test_no_duplicate_values(self):
        values = {
            getattr(LifecycleEvents, attr)
            for attr in dir(LifecycleEvents)
            if not attr.startswith("_")
        }
        assert len(values) == sum(
            1 for attr in dir(LifecycleEvents) if not attr.startswith("_")
        )
