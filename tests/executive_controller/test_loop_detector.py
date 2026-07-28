from __future__ import annotations

import threading
import time

from app.executive_controller.loop_detector import LoopDetector, LoopSeverity


class TestLoopDetector:
    def test_record_execution(self) -> None:
        ld = LoopDetector()
        ld.record_execution("comp-a", 0.5, True)
        report = ld.check("comp-a")
        assert report.execution_count == 1
        assert report.severity == LoopSeverity.NONE

    def test_no_records_returns_empty(self) -> None:
        ld = LoopDetector()
        report = ld.check("unknown")
        assert report.execution_count == 0
        assert report.severity == LoopSeverity.NONE

    def test_high_frequency_detected(self) -> None:
        ld = LoopDetector(max_executions_per_minute=5)
        for _ in range(10):
            ld.record_execution("comp-a", 0.1, True)
            time.sleep(0.001)
        report = ld.check("comp-a")
        assert report.severity in (LoopSeverity.CONFIRMED, LoopSeverity.TERMINATED)

    def test_consecutive_failures_detected(self) -> None:
        ld = LoopDetector(max_consecutive_failures=3)
        for _ in range(5):
            ld.record_execution("comp-a", 0.1, False, error="fail")
        report = ld.check("comp-a")
        assert report.severity == LoopSeverity.CONFIRMED

    def test_same_output_detected(self) -> None:
        ld = LoopDetector(max_same_output=3)
        for _ in range(5):
            ld.record_execution("comp-a", 0.1, True, output_hash="abc123")
        report = ld.check("comp-a")
        assert report.severity == LoopSeverity.CONFIRMED

    def test_long_running_detected(self) -> None:
        ld = LoopDetector(max_duration_seconds=1.0)
        ld.record_execution("comp-a", 5.0, True)
        report = ld.check("comp-a")
        assert report.severity == LoopSeverity.CONFIRMED

    def test_terminated_severity(self) -> None:
        ld = LoopDetector(max_executions_per_minute=3)
        for _ in range(10):
            ld.record_execution("comp-a", 0.01, True)
        report = ld.check("comp-a")
        assert report.severity == LoopSeverity.TERMINATED

    def test_is_terminated(self) -> None:
        ld = LoopDetector()
        assert ld.is_terminated("comp-a") is False
        ld.mark_terminated("comp-a")
        assert ld.is_terminated("comp-a") is True

    def test_clear(self) -> None:
        ld = LoopDetector()
        ld.record_execution("comp-a", 0.1, True)
        ld.clear("comp-a")
        report = ld.check("comp-a")
        assert report.execution_count == 0

    def test_get_stats(self) -> None:
        ld = LoopDetector()
        ld.record_execution("a", 0.1)
        ld.record_execution("b", 0.2)
        stats = ld.get_stats()
        assert stats["components_tracked"] == 2
        assert stats["total_executions_recorded"] == 2

    def test_loop_report_to_dict(self) -> None:
        ld = LoopDetector(max_same_output=2)
        for _ in range(3):
            ld.record_execution("comp-a", 0.1, True, output_hash="fixed")
        report = ld.check("comp-a")
        d = report.to_dict()
        assert d["severity"] != LoopSeverity.NONE.value
        assert d["execution_count"] >= 3

    def test_thread_safety(self) -> None:
        ld = LoopDetector()
        errors: list[Exception] = []

        def worker() -> None:
            for i in range(100):
                try:
                    ld.record_execution(f"comp-{i % 5}", 0.1, True)
                    ld.check(f"comp-{i % 5}")
                    ld.get_stats()
                except Exception as e:
                    errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(errors) == 0
