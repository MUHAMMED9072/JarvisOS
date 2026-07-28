"""Tests for AsyncWorker."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from app.client.ui.worker import AsyncWorker


class TestAsyncWorkerInit:
    def test_default_construction(self):
        worker = AsyncWorker()
        assert worker.running is False
        assert worker.loop is None

    def test_initial_attributes(self):
        worker = AsyncWorker()
        assert hasattr(worker, "_loop")
        assert hasattr(worker, "_thread")
        assert hasattr(worker, "_running")


class TestAsyncWorkerLifecycle:
    def test_start_starts_thread_and_creates_loop(self):
        worker = AsyncWorker()
        worker.start()
        assert worker.running is True
        assert worker._thread is not None
        assert worker._thread.is_alive()
        assert worker.loop is not None
        assert not worker.loop.is_closed()
        worker.stop()

    def test_start_is_idempotent(self):
        worker = AsyncWorker()
        worker.start()
        thread = worker._thread
        worker.start()
        assert worker._thread is thread
        worker.stop()

    def test_stop_stops_loop(self):
        worker = AsyncWorker()
        worker.start()
        loop = worker.loop
        worker.stop()
        assert worker.running is False

    def test_stop_without_start_is_safe(self):
        worker = AsyncWorker()
        worker.stop()


class TestAsyncWorkerRun:
    def test_run_schedules_coroutine(self):
        worker = AsyncWorker()
        worker.start()

        results = []
        import time

        async def dummy():
            results.append("ran")
            return "ok"

        worker.run(dummy())
        time.sleep(0.2)
        assert "ran" in results
        worker.stop()

    def test_run_calls_callback(self):
        worker = AsyncWorker()
        worker.start()

        results = []

        async def dummy():
            return 42

        def callback(result):
            results.append(("done", result))

        worker.run(dummy(), callback)
        import time
        time.sleep(0.2)
        assert len(results) == 1
        assert results[0][0] == "done"
        assert results[0][1] == 42
        worker.stop()

    def test_run_without_start_logs_warning(self):
        worker = AsyncWorker()

        async def dummy():
            return 1

        with patch("app.client.ui.worker.logger.warning") as mock_warn:
            worker.run(dummy())
            mock_warn.assert_called_once()

    def test_run_error_triggers_callback_with_error(self):
        worker = AsyncWorker()
        worker.start()

        results = []

        async def failing():
            raise ValueError("test error")

        def callback(result, error=""):
            results.append(("error", result, error))

        worker.run(failing(), callback)
        import time
        time.sleep(0.2)
        assert len(results) == 1
        assert results[0][0] == "error"
        assert "test error" in results[0][2]
        worker.stop()

    def test_run_returns_future(self):
        worker = AsyncWorker()
        worker.start()

        async def dummy():
            return "ok"

        future = worker.run(dummy())
        assert future is not None
        worker.stop()


class TestAsyncWorkerMultipleTasks:
    def test_multiple_tasks_execute(self):
        worker = AsyncWorker()
        worker.start()

        results = []

        async def task(n):
            results.append(n)
            return n

        for i in range(5):
            worker.run(task(i))

        import time
        time.sleep(0.3)
        assert len(results) == 5
        for i in range(5):
            assert i in results
        worker.stop()
