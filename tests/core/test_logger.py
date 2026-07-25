from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

import pytest

from app.core.logger import JarvisLogger


@pytest.fixture(autouse=True)
def reset_logger():
    """Reset JarvisLogger state and python logging before each test,
    and restore both afterwards."""
    JarvisLogger._initialized = False
    root = logging.getLogger()
    saved_handlers = list(root.handlers)
    saved_level = root.level
    root.handlers.clear()

    yield

    JarvisLogger._initialized = False
    root.handlers.clear()
    for h in saved_handlers:
        root.addHandler(h)
    root.setLevel(saved_level)


class TestJarvisLogger:
    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    def test_setup_sets_initialized(self):
        assert JarvisLogger._initialized is False
        JarvisLogger.setup()
        assert JarvisLogger._initialized is True

    def test_setup_is_idempotent(self, reset_logger):
        JarvisLogger.setup()
        root = logging.getLogger()
        handler_count = len(root.handlers)
        JarvisLogger.setup()
        assert len(root.handlers) == handler_count

    def test_setup_creates_file_handler(self, reset_logger):
        JarvisLogger.setup()
        root = logging.getLogger()
        assert any(isinstance(h, logging.FileHandler) for h in root.handlers)

    def test_setup_creates_stream_handler(self, reset_logger):
        JarvisLogger.setup()
        root = logging.getLogger()
        assert any(isinstance(h, logging.StreamHandler) for h in root.handlers)

    # ------------------------------------------------------------------
    # Log level
    # ------------------------------------------------------------------

    def test_default_level(self, reset_logger):
        from app.core.config import Config
        expected = getattr(logging, Config.LOG_LEVEL)
        JarvisLogger.setup()
        root = logging.getLogger()
        assert root.level == expected

    # ------------------------------------------------------------------
    # Log methods
    # ------------------------------------------------------------------

    @pytest.fixture
    def log_capture(self, reset_logger):
        JarvisLogger.setup()
        logging.getLogger().setLevel(logging.DEBUG)
        stream = tempfile.TemporaryFile("w+", encoding="utf-8")
        handler = logging.StreamHandler(stream)
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(logging.Formatter(
            "%(asctime)s | %(levelname)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))
        logging.getLogger().addHandler(handler)
        yield stream
        handler.close()
        stream.close()

    def _read(self, stream):
        stream.seek(0)
        return stream.read()

    def test_debug(self, log_capture):
        JarvisLogger.debug("dbg msg")
        assert "DEBUG" in self._read(log_capture)

    def test_info(self, log_capture):
        JarvisLogger.info("info msg")
        assert self._read(log_capture).strip().endswith("| INFO | info msg")

    def test_warning(self, log_capture):
        JarvisLogger.warning("warn msg")
        assert "WARNING" in self._read(log_capture)

    def test_error(self, log_capture):
        JarvisLogger.error("err msg")
        assert "ERROR" in self._read(log_capture)

    def test_exception(self, log_capture):
        try:
            raise ValueError("test")
        except ValueError:
            JarvisLogger.exception("exc msg")
        output = self._read(log_capture)
        assert "ERROR" in output

    def test_log_format_output(self, log_capture):
        JarvisLogger.info("format test")
        output = self._read(log_capture).strip()
        parts = output.split(" | ")
        assert len(parts) == 3
        assert parts[1] == "INFO"
        assert parts[2] == "format test"

    # ------------------------------------------------------------------
    # File output
    # ------------------------------------------------------------------

    def test_writes_to_file(self, reset_logger):
        JarvisLogger.setup()
        log_file = Path("logs") / "jarvis.log"
        JarvisLogger.info("to file")
        content = log_file.read_text(encoding="utf-8")
        assert "to file" in content
