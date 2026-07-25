from __future__ import annotations

import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from app.gui.controllers.logs_controller import LogEntry, LogsController


@pytest.fixture
def log_content():
    return (
        "2026-07-24 10:00:00 | INFO | Kernel boot complete\n"
        "2026-07-24 10:00:01 | WARNING | Speaker not available\n"
        "2026-07-24 10:00:02 | ERROR | AI router timeout\n"
        "2026-07-24 10:00:03 | DEBUG | Sandbox cleanup ok\n"
        "2026-07-24 10:00:04 | INFO | Voice manager started\n"
    )


@pytest.fixture
def log_file(log_content):
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", suffix=".log", delete=False
    ) as f:
        f.write(log_content)
        path = f.name
    yield path
    try:
        os.unlink(path)
    except OSError:
        pass


@pytest.fixture
def controller(log_file):
    ctrl = LogsController(MagicMock())
    ctrl._filepath = log_file
    ctrl.refresh()
    return ctrl


class TestLogsController:
    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    def test_refresh_parses_entries(self, controller):
        assert len(controller._entries) == 5

    def test_parse_returns_empty_for_missing_file(self):
        entries = LogsController._parse_file("/nonexistent/path.log")
        assert entries == []

    def test_entry_fields(self, controller):
        entry = controller._entries[0]
        assert isinstance(entry, LogEntry)
        assert entry.timestamp == "2026-07-24 10:00:00"
        assert entry.level == "INFO"
        assert "Kernel boot" in entry.message
        assert "Kernel boot" in entry.raw

    def test_parse_ignores_malformed_lines(self, log_file):
        with open(log_file, "a", encoding="utf-8") as f:
            f.write("this is not a valid log line\n")
        controller = LogsController(MagicMock())
        controller._filepath = log_file
        controller.refresh()
        assert len(controller._entries) == 5

    def test_parse_handles_empty_file(self):
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", suffix=".log", delete=False
        ) as f:
            path = f.name
        entries = LogsController._parse_file(path)
        assert entries == []
        os.unlink(path)

    # ------------------------------------------------------------------
    # get_entries — no filters
    # ------------------------------------------------------------------

    def test_get_entries_returns_all_reversed(self, controller):
        entries = controller.get_entries()
        assert len(entries) == 5
        assert entries[0].timestamp == "2026-07-24 10:00:04"
        assert entries[-1].timestamp == "2026-07-24 10:00:00"

    def test_get_entries_max_lines(self, controller):
        entries = controller.get_entries(max_lines=2)
        assert len(entries) == 2

    # ------------------------------------------------------------------
    # get_entries — level filter
    # ------------------------------------------------------------------

    def test_get_entries_filter_warning(self, controller):
        entries = controller.get_entries(level_filter="WARNING")
        for e in entries:
            assert e.level in ("WARNING", "ERROR")

    def test_get_entries_filter_error(self, controller):
        entries = controller.get_entries(level_filter="ERROR")
        for e in entries:
            assert e.level == "ERROR"

    def test_get_entries_filter_debug(self, controller):
        entries = controller.get_entries(level_filter="DEBUG")
        for e in entries:
            assert e.level in ("DEBUG", "INFO", "WARNING", "ERROR")

    def test_get_entries_filter_nonexistent(self, controller):
        entries = controller.get_entries(level_filter="UNKNOWN")
        assert len(entries) == 5

    # ------------------------------------------------------------------
    # get_entries — search
    # ------------------------------------------------------------------

    def test_get_entries_search(self, controller):
        entries = controller.get_entries(search="Kernel")
        assert len(entries) == 1
        assert "Kernel" in entries[0].message

    def test_get_entries_search_case_insensitive(self, controller):
        entries = controller.get_entries(search="kernel")
        assert len(entries) == 1

    def test_get_entries_search_no_match(self, controller):
        assert controller.get_entries(search="zzzzz") == []

    def test_get_entries_search_and_filter(self, controller):
        entries = controller.get_entries(level_filter="INFO", search="Voice")
        assert len(entries) == 1
        assert entries[0].level == "INFO"

    # ------------------------------------------------------------------
    # get_levels_in_use
    # ------------------------------------------------------------------

    def test_get_levels_in_use(self, controller):
        levels = controller.get_levels_in_use()
        assert "INFO" in levels
        assert "WARNING" in levels
        assert "ERROR" in levels
        assert "DEBUG" in levels

    def test_get_levels_in_use_order(self, controller):
        levels = controller.get_levels_in_use()
        assert levels == ["DEBUG", "INFO", "WARNING", "ERROR"]

    # ------------------------------------------------------------------
    # Pause / Resume
    # ------------------------------------------------------------------

    def test_pause_default(self, controller):
        assert controller.paused is False

    def test_pause_setter(self, controller):
        controller.paused = True
        assert controller.paused is True
        controller.paused = False
        assert controller.paused is False

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def test_export_entries(self, controller):
        entries = controller.get_entries(level_filter="ERROR")
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", suffix=".log", delete=False
        ) as f:
            out_path = f.name
        try:
            controller.export_entries(entries, out_path)
            with open(out_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            assert len(lines) == 1
            assert "AI router timeout" in lines[0]
        finally:
            os.unlink(out_path)

    def test_export_empty(self, controller):
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", suffix=".log", delete=False
        ) as f:
            out_path = f.name
        try:
            controller.export_entries([], out_path)
            with open(out_path, "r", encoding="utf-8") as f:
                assert f.read() == ""
        finally:
            os.unlink(out_path)
