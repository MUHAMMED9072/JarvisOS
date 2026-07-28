from __future__ import annotations

import json
import re
import threading
import time
from pathlib import Path

import pytest

from app.kernel.logger import (
    LogEntry,
    LogLevel,
    StructuredLogger,
    get_correlation_id,
    reset_correlation_id,
    set_correlation_id,
)
from app.core.event_bus import EventBus


# ======================================================================
# LogLevel tests
# ======================================================================

class TestLogLevel:
    def test_is_enabled_debug_allows_all(self):
        assert LogLevel.is_enabled("DEBUG", "DEBUG") is True
        assert LogLevel.is_enabled("DEBUG", "INFO") is True
        assert LogLevel.is_enabled("DEBUG", "ERROR") is True

    def test_is_enabled_info_blocks_debug(self):
        assert LogLevel.is_enabled("INFO", "DEBUG") is False
        assert LogLevel.is_enabled("INFO", "INFO") is True
        assert LogLevel.is_enabled("INFO", "ERROR") is True

    def test_is_enabled_critical_blocks_all_but_critical(self):
        assert LogLevel.is_enabled("CRITICAL", "INFO") is False
        assert LogLevel.is_enabled("CRITICAL", "WARNING") is False
        assert LogLevel.is_enabled("CRITICAL", "CRITICAL") is True

    def test_parse_valid(self):
        assert LogLevel.parse("info") == "INFO"
        assert LogLevel.parse("ERROR") == "ERROR"
        assert LogLevel.parse("Debug") == "DEBUG"

    def test_parse_invalid_defaults_to_info(self):
        assert LogLevel.parse("UNKNOWN") == "INFO"

    def test_all_returns_all_levels(self):
        all_levels = LogLevel.all()
        assert "DEBUG" in all_levels
        assert "INFO" in all_levels
        assert "WARNING" in all_levels
        assert "ERROR" in all_levels
        assert "CRITICAL" in all_levels


# ======================================================================
# Correlation ID tests
# ======================================================================

class TestCorrelationId:
    def test_default_is_none(self):
        reset_correlation_id()
        assert get_correlation_id() is None

    def test_set_and_get(self):
        reset_correlation_id()
        set_correlation_id("test-123")
        assert get_correlation_id() == "test-123"

    def test_reset(self):
        set_correlation_id("abc")
        reset_correlation_id()
        assert get_correlation_id() is None

    def test_thread_isolation(self):
        reset_correlation_id()
        set_correlation_id("main")
        results: list[str | None] = []

        def worker() -> None:
            reset_correlation_id()
            set_correlation_id("thread")
            results.append(get_correlation_id())

        t = threading.Thread(target=worker)
        t.start()
        t.join()

        assert get_correlation_id() == "main"
        assert results == ["thread"]


# ======================================================================
# LogEntry tests
# ======================================================================

class TestLogEntry:
    def test_to_dict_contains_required_keys(self):
        entry = LogEntry(
            timestamp="2026-01-01T00:00:00",
            level="INFO",
            message="hello",
        )
        d = entry.to_dict()
        assert d["timestamp"] == "2026-01-01T00:00:00"
        assert d["level"] == "INFO"
        assert d["message"] == "hello"

    def test_to_dict_omits_empty_fields(self):
        entry = LogEntry(timestamp="t", level="INFO", message="m")
        d = entry.to_dict()
        assert "logger" not in d
        assert "correlation_id" not in d
        assert "context" not in d
        assert "source" not in d

    def test_to_dict_includes_optional_fields(self):
        entry = LogEntry(
            timestamp="t", level="INFO", message="m",
            logger="test", correlation_id="cid",
            context={"k": "v"}, source="mod.py",
        )
        d = entry.to_dict()
        assert d["logger"] == "test"
        assert d["correlation_id"] == "cid"
        assert d["context"] == {"k": "v"}
        assert d["source"] == "mod.py"

    def test_from_dict_round_trip(self):
        original = LogEntry(
            timestamp="2026-06-01T12:00:00",
            level="WARNING",
            message="disk full",
            logger="sys",
            correlation_id="abc",
            context={"usage": 95},
            source="monitor.py",
        )
        d = original.to_dict()
        restored = LogEntry.from_dict(d)
        assert restored.timestamp == original.timestamp
        assert restored.level == original.level
        assert restored.message == original.message
        assert restored.correlation_id == original.correlation_id
        assert restored.context == original.context


# ======================================================================
# StructuredLogger tests
# ======================================================================

@pytest.fixture
def logger(tmp_path: Path) -> StructuredLogger:
    return StructuredLogger(
        name="test",
        level="DEBUG",
        log_dir=tmp_path,
        max_bytes=1024 * 1024,
        backup_count=2,
    )


class TestStructuredLoggerCore:
    def test_default_properties(self, tmp_path: Path):
        log = StructuredLogger(name="test", log_dir=tmp_path)
        assert log._name == "test"
        assert log._level == "INFO"

    def test_debug_writes_entry(self, logger: StructuredLogger):
        logger.debug("debug msg")
        entries = logger.query(level="DEBUG")
        assert len(entries) == 1
        assert entries[0].message == "debug msg"

    def test_info_writes_entry(self, logger: StructuredLogger):
        logger.info("info msg", extra="data")
        entries = logger.query(level="INFO")
        assert len(entries) == 1
        assert entries[0].message == "info msg"
        assert entries[0].context.get("extra") == "data"

    def test_warning_writes_entry(self, logger: StructuredLogger):
        logger.warning("warn msg")
        entries = logger.query(level="WARNING")
        assert len(entries) == 1

    def test_error_writes_entry(self, logger: StructuredLogger):
        logger.error("err msg")
        entries = logger.query(level="ERROR")
        assert len(entries) == 1

    def test_critical_writes_entry(self, logger: StructuredLogger):
        logger.critical("crit msg")
        entries = logger.query(level="CRITICAL")
        assert len(entries) == 1

    def test_level_filter_blocks_debug_when_info(self, tmp_path: Path):
        log = StructuredLogger(name="test", level="INFO", log_dir=tmp_path)
        log.debug("should be hidden")
        log.info("should appear")
        entries = log.query()
        assert len(entries) == 1
        assert entries[0].level == "INFO"

    def test_entry_has_timestamp(self, logger: StructuredLogger):
        logger.info("timed")
        entry = logger.query()[0]
        assert entry.timestamp
        assert "T" in entry.timestamp  # ISO format

    def test_entry_has_logger_name(self, logger: StructuredLogger):
        logger.info("named")
        entry = logger.query()[0]
        assert entry.logger == "test"

    def test_entry_has_source(self, logger: StructuredLogger):
        logger.info("source check")
        entry = logger.query()[0]
        assert entry.source

    def test_context_includes_extra_kwargs(self, logger: StructuredLogger):
        logger.info("ctx", user="alice", count=42)
        entry = logger.query()[0]
        assert entry.context["user"] == "alice"
        assert entry.context["count"] == 42

    def test_multiple_entries(self, logger: StructuredLogger):
        for i in range(10):
            logger.info(f"msg {i}")
        entries = logger.query(limit=100)
        assert len(entries) == 10


class TestStructuredLoggerCorrelationId:
    def test_log_includes_correlation_id(self, logger: StructuredLogger):
        set_correlation_id("req-001")
        try:
            logger.info("logged with cid")
            entry = logger.query()[0]
            assert entry.correlation_id == "req-001"
        finally:
            reset_correlation_id()

    def test_log_without_correlation_id(self, logger: StructuredLogger):
        reset_correlation_id()
        logger.info("no cid")
        entry = logger.query()[0]
        assert entry.correlation_id is None


class TestStructuredLoggerBind:
    def test_bind_adds_permanent_context(self, logger: StructuredLogger):
        child = logger.bind(request_id="abc", user="bob")
        child.info("bound log")
        entry = child.query()[0]
        assert entry.context["request_id"] == "abc"
        assert entry.context["user"] == "bob"

    def test_bind_does_not_affect_parent(self, logger: StructuredLogger):
        parent = logger
        child = parent.bind(request_id="child-only")
        parent.info("parent log")
        child.info("child log")
        parent_entries = parent.query()
        child_entries = child.query()
        parent_ctx = parent_entries[0].context or {}
        assert "request_id" not in parent_ctx

    def test_bind_chain(self, logger: StructuredLogger):
        l1 = logger.bind(a=1)
        l2 = l1.bind(b=2)
        l2.info("chained")
        entry = l2.query()[0]
        assert entry.context["a"] == 1
        assert entry.context["b"] == 2


class TestStructuredLoggerQuery:
    def test_query_by_level(self, logger: StructuredLogger):
        logger.debug("d1")
        logger.info("i1")
        logger.info("i2")
        logger.warning("w1")
        infos = logger.query(level="INFO")
        assert len(infos) == 2
        assert all(e.level == "INFO" for e in infos)

    def test_query_by_limit(self, logger: StructuredLogger):
        for i in range(50):
            logger.info(f"msg {i}")
        entries = logger.query(limit=10)
        assert len(entries) == 10

    def test_query_by_offset(self, logger: StructuredLogger):
        for i in range(10):
            logger.info(f"msg {i}")
        entries = logger.query(limit=5, offset=5)
        assert len(entries) == 5
        assert "msg 5" in entries[0].message

    def test_query_by_source(self, logger: StructuredLogger):
        logger.info("src test")
        entries = logger.query(source="test_logger")
        assert len(entries) >= 1

    def test_query_by_message_pattern(self, logger: StructuredLogger):
        logger.info("user login: alice")
        logger.info("user logout: bob")
        logger.info("system check")
        entries = logger.query(message_pattern=r"user\s+login")
        assert len(entries) == 1
        assert "alice" in entries[0].message

    def test_query_empty(self, logger: StructuredLogger):
        entries = logger.query()
        assert entries == []


class TestStructuredLoggerEventBus:
    def test_publishes_log_events(self, tmp_path: Path):
        bus = EventBus()
        log = StructuredLogger(name="test", log_dir=tmp_path, event_bus=bus)
        received: list = []
        bus.subscribe("log.entry", received.append)
        log.info("event test")
        assert len(received) == 1
        assert received[0]["message"] == "event test"


class TestStructuredLoggerHealth:
    def test_health_returns_dict(self, logger: StructuredLogger):
        h = logger.health()
        assert h["alive"] is True
        assert h["logger"] == "test"
        assert h["level"] == "DEBUG"
        assert h["entry_count"] == 0
        assert h["error_count"] == 0
        assert h["uptime_seconds"] >= 0

    def test_health_reflects_activity(self, logger: StructuredLogger):
        logger.info("ok")
        logger.error("fail")
        h = logger.health()
        assert h["entry_count"] == 2
        assert h["error_count"] == 1


class TestStructuredLoggerRotation:
    def test_log_file_created(self, logger: StructuredLogger):
        logger.info("first entry")
        assert logger._log_path.exists()
        content = logger._log_path.read_text(encoding="utf-8")
        assert "first entry" in content

    def test_rotation_creates_backup(self, tmp_path: Path):
        log = StructuredLogger(
            name="rotate-test",
            level="DEBUG",
            log_dir=tmp_path,
            max_bytes=100,  # tiny threshold
            backup_count=2,
        )
        for i in range(50):
            log.info(f"msg {i} with padding data to fill up space quickly")
        # Check that at least one backup file exists
        backups = list(tmp_path.glob("rotate-test.*.jsonl"))
        assert len(backups) >= 1


class TestStructuredLoggerThreadSafety:
    def test_concurrent_writes(self, tmp_path: Path):
        log = StructuredLogger(name="test", level="DEBUG", log_dir=tmp_path)
        errors: list[Exception] = []

        def writer(prefix: str) -> None:
            try:
                for i in range(50):
                    log.info(f"{prefix}-{i}")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=("A",)),
                   threading.Thread(target=writer, args=("B",))]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        entries = log.query(limit=200)
        assert len(entries) == 100


class TestStructuredLoggerException:
    def test_exception_includes_traceback(self, logger: StructuredLogger):
        try:
            raise ValueError("test error")
        except ValueError:
            logger.exception("something broke")

        entries = logger.query(level="ERROR")
        assert len(entries) >= 1
        ctx = entries[0].context or {}
        assert "traceback" in ctx
        assert "ValueError" in ctx["traceback"]


class TestStructuredLoggerEdgeCases:
    def test_log_file_is_json_lines(self, logger: StructuredLogger):
        logger.info("line1")
        logger.info("line2")
        lines = logger._log_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2
        for line in lines:
            data = json.loads(line)
            assert "timestamp" in data
            assert "level" in data

    def test_close_cleans_up(self, logger: StructuredLogger):
        logger.info("before close")
        logger.close()
        assert logger._file is None or logger._file.closed
