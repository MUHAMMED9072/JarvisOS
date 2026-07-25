from __future__ import annotations

import signal
from unittest.mock import MagicMock, patch

import pytest

from app.core.kernel import JarvisKernel


class TestJarvisKernel:
    @pytest.fixture
    def kernel(self):
        k = JarvisKernel()
        k.voice_manager = MagicMock()
        k.memory = MagicMock()
        k.running = True
        yield k
        k.running = False

    # ------------------------------------------------------------------
    # Shutdown basics
    # ------------------------------------------------------------------

    def test_shutdown_stops_voice(self, kernel):
        kernel.shutdown()
        kernel.voice_manager.stop.assert_called_once()

    def test_shutdown_flushes_memory(self, kernel):
        kernel.shutdown()
        kernel.memory.storage.save.assert_called_once()

    def test_shutdown_sets_running_false(self, kernel):
        assert kernel.running is True
        kernel.shutdown()
        assert kernel.running is False

    def test_shutdown_is_idempotent(self, kernel):
        kernel.shutdown()
        kernel.shutdown()
        assert kernel.voice_manager.stop.call_count == 1

    def test_shutdown_memory_flush_failure_is_caught(self, kernel):
        kernel.memory.storage.save.side_effect = RuntimeError("disk full")
        kernel.shutdown()

    # ------------------------------------------------------------------
    # Pre-boot shutdown (no-op)
    # ------------------------------------------------------------------

    def test_shutdown_before_boot_is_noop(self):
        k = JarvisKernel()
        k.voice_manager = MagicMock()
        assert k.running is False
        k.shutdown()
        k.voice_manager.stop.assert_not_called()

    # ------------------------------------------------------------------
    # Signal handler registration
    # ------------------------------------------------------------------

    def test_constructor_registers_atexit(self):
        with patch("atexit.register") as mock_atexit:
            k = JarvisKernel()
            mock_atexit.assert_called_once_with(k.shutdown)

    @pytest.mark.parametrize("sig", [signal.SIGINT, signal.SIGTERM])
    def test_constructor_registers_signal_handlers(self, sig):
        with patch("signal.signal") as mock_signal:
            k = JarvisKernel()
            calls = [c.args for c in mock_signal.call_args_list]
            assert any(c[0] == sig for c in calls)

    def test_signal_handler_invokes_shutdown(self, kernel):
        with patch.object(kernel, "shutdown") as mock_shutdown:
            kernel._signal_handler(signal.SIGINT, None)
            mock_shutdown.assert_called_once()
