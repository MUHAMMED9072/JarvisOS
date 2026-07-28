from __future__ import annotations

import threading
import time

import pytest

from app.executive_controller.failure_recovery import (
    ComponentStatus,
    FailureRecovery,
    FailureSeverity,
    RecoveryPolicy,
    RecoveryStrategy,
)


class TestComponentStatus:
    def test_defaults(self) -> None:
        s = ComponentStatus(component_id="test")
        assert s.healthy is True
        assert s.consecutive_failures == 0
        assert s.recovery_attempts == 0
        assert s.degraded is False
        assert s.escalated is False

    def test_to_dict(self) -> None:
        s = ComponentStatus(component_id="a", healthy=False, error="boom")
        d = s.to_dict()
        assert d["healthy"] is False
        assert d["error"] == "boom"


class TestFailureRecovery:
    def test_register_adds_component(self) -> None:
        fr = FailureRecovery()
        fr.register("comp-a")
        status = fr.get_status("comp-a")
        assert status is not None
        assert status.component_id == "comp-a"

    def test_unregister_removes_component(self) -> None:
        fr = FailureRecovery()
        fr.register("comp-a")
        assert fr.unregister("comp-a") is True
        assert fr.get_status("comp-a") is None

    def test_report_failure_creates_component(self) -> None:
        fr = FailureRecovery()
        result = fr.report_failure("auto-created", "error msg", FailureSeverity.MINOR)
        status = fr.get_status("auto-created")
        assert status is not None
        assert status.healthy is False

    def test_report_success(self) -> None:
        fr = FailureRecovery()
        fr.register("comp-a")
        fr.report_failure("comp-a", "fail")
        fr.report_success("comp-a")
        status = fr.get_status("comp-a")
        assert status is not None
        assert status.healthy is True
        assert status.consecutive_failures == 0

    def test_recovery_restart(self) -> None:
        fr = FailureRecovery(default_policy=RecoveryPolicy(
            strategy=RecoveryStrategy.RESTART,
            failure_threshold=1,
            max_retries=1,
            retry_delay_seconds=0.01,
        ))
        restart_called: list[bool] = [False]

        def restart() -> None:
            restart_called[0] = True

        fr.register("comp-a", restart_hook=restart)
        fr.report_failure("comp-a", "fail")
        assert restart_called[0] is True

    def test_recovery_degrade(self) -> None:
        fr = FailureRecovery(default_policy=RecoveryPolicy(
            strategy=RecoveryStrategy.DEGRADE,
            failure_threshold=1,
        ))
        fr.register("comp-a")
        result = fr.report_failure("comp-a", "fail")
        assert result == "degraded"
        status = fr.get_status("comp-a")
        assert status is not None
        assert status.degraded is True

    def test_recovery_escalate(self) -> None:
        fr = FailureRecovery(default_policy=RecoveryPolicy(
            strategy=RecoveryStrategy.ESCALATE,
            failure_threshold=1,
        ))
        escalated: list[tuple[str, str]] = []
        fr.register_escalation_hook(lambda cid, reason: escalated.append((cid, reason)))
        fr.register("comp-a")
        result = fr.report_failure("comp-a", "critical fail")
        assert result == "escalated"
        assert len(escalated) == 1
        assert escalated[0][0] == "comp-a"

    def test_recovery_ignore(self) -> None:
        fr = FailureRecovery(default_policy=RecoveryPolicy(
            strategy=RecoveryStrategy.IGNORE,
            failure_threshold=1,
        ))
        fr.register("comp-a")
        result = fr.report_failure("comp-a", "fail")
        assert result is None

    def test_max_retries_exceeded_escalates(self) -> None:
        fr = FailureRecovery(default_policy=RecoveryPolicy(
            strategy=RecoveryStrategy.RESTART,
            failure_threshold=1,
            max_retries=2,
            retry_delay_seconds=0.01,
            backoff_multiplier=1.0,
        ))
        restart_count: list[int] = [0]

        def restart() -> None:
            restart_count[0] += 1
            raise RuntimeError("restart failed")

        escalated: list[tuple[str, str]] = []
        fr.register_escalation_hook(lambda cid, reason: escalated.append((cid, reason)))
        fr.register("comp-a", restart_hook=restart)
        result = fr.report_failure("comp-a", "fail")
        assert result == "escalated"
        assert len(escalated) == 1

    def test_get_all_statuses(self) -> None:
        fr = FailureRecovery()
        fr.register("a")
        fr.register("b")
        assert len(fr.get_all_statuses()) == 2

    def test_get_stats(self) -> None:
        fr = FailureRecovery()
        fr.register("a")
        fr.report_failure("a", "fail")
        stats = fr.get_stats()
        assert stats["components_tracked"] == 1
        assert stats["unhealthy"] == 1
        assert stats["failures_recorded"] == 1

    def test_health(self) -> None:
        fr = FailureRecovery()
        h = fr.health()
        assert h["alive"] is True
        assert "tracked_components" in h

    def test_report_failure_below_threshold(self) -> None:
        fr = FailureRecovery(default_policy=RecoveryPolicy(
            strategy=RecoveryStrategy.RESTART,
            failure_threshold=3,
        ))
        fr.register("comp-a")
        result = fr.report_failure("comp-a", "first")
        assert result is None
        result = fr.report_failure("comp-a", "second")
        assert result is None

    def test_no_restart_hook_escalates(self) -> None:
        fr = FailureRecovery(default_policy=RecoveryPolicy(
            strategy=RecoveryStrategy.RESTART,
            failure_threshold=1,
            max_retries=1,
        ))
        escalated: list[tuple[str, str]] = []
        fr.register_escalation_hook(lambda cid, reason: escalated.append((cid, reason)))
        fr.register("comp-a")  # no restart hook
        result = fr.report_failure("comp-a", "fail")
        assert result == "escalated"

    def test_thread_safety(self) -> None:
        fr = FailureRecovery()
        errors: list[Exception] = []

        def worker() -> None:
            for i in range(100):
                try:
                    cid = f"comp-{i % 10}"
                    fr.register(cid)
                    fr.report_failure(cid, "err")
                    fr.report_success(cid)
                    fr.get_status(cid)
                    fr.get_stats()
                except Exception as e:
                    errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(errors) == 0
