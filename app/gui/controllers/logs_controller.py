from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import IO


_LINE_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \| (\w+) \| (.*)$"
)

_LEVEL_ORDER = {"DEBUG": 0, "INFO": 1, "WARNING": 2, "ERROR": 3, "CRITICAL": 4}
_ALL_LEVELS = frozenset(_LEVEL_ORDER.keys())


@dataclass
class LogEntry:
    timestamp: str
    level: str
    message: str
    raw: str


class LogsController:
    """Orchestrates the Logs Viewer page."""

    def __init__(self, registry) -> None:
        self.registry = registry
        self._entries: list[LogEntry] = []
        self._paused = False
        self._filepath = self._resolve_log_path()

    # ------------------------------------------------------------------
    # Path resolution
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_log_path() -> str:
        from app.core.config import Config
        resolved = os.path.join(str(Config.LOG_DIR), "jarvis.log")
        return resolved

    # ------------------------------------------------------------------
    # File reading
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        """Re-read the log file and parse all entries."""
        self._entries = self._parse_file(self._filepath)

    @staticmethod
    def _parse_file(filepath: str) -> list[LogEntry]:
        try:
            with open(filepath, "r", encoding="utf-8") as fh:
                return LogsController._parse_lines(fh)
        except (FileNotFoundError, OSError):
            return []

    @staticmethod
    def _parse_lines(fh: IO[str]) -> list[LogEntry]:
        entries: list[LogEntry] = []
        for line in fh:
            line = line.rstrip("\n\r")
            m = _LINE_RE.match(line)
            if m:
                entries.append(
                    LogEntry(
                        timestamp=m.group(1),
                        level=m.group(2),
                        message=m.group(3),
                        raw=line,
                    )
                )
        return entries

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def get_entries(
        self,
        *,
        level_filter: str | None = None,
        search: str | None = None,
        max_lines: int = 2000,
    ) -> list[LogEntry]:
        """Return filtered entries, most recent first."""
        entries = self._entries

        if level_filter and level_filter.upper() in _LEVEL_ORDER:
            min_order = _LEVEL_ORDER[level_filter.upper()]
            entries = [e for e in entries if _LEVEL_ORDER.get(e.level, 0) >= min_order]

        if search:
            q = search.lower()
            entries = [
                e for e in entries
                if q in e.message.lower() or q in e.raw.lower()
            ]

        # Most recent first, limited
        result = list(reversed(entries))
        if len(result) > max_lines:
            result = result[:max_lines]
        return result

    def get_levels_in_use(self) -> list[str]:
        """Return distinct log levels present in the current data."""
        seen: set[str] = set()
        for e in self._entries:
            if e.level in _ALL_LEVELS:
                seen.add(e.level)
        return sorted(seen, key=lambda lvl: _LEVEL_ORDER.get(lvl, 99))

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    @property
    def paused(self) -> bool:
        return self._paused

    @paused.setter
    def paused(self, value: bool) -> None:
        self._paused = bool(value)

    @property
    def filepath(self) -> str:
        return self._filepath

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def export_entries(
        self,
        entries: list[LogEntry],
        output_path: str,
    ) -> None:
        """Write entries to a text file."""
        with open(output_path, "w", encoding="utf-8") as fh:
            for e in entries:
                fh.write(e.raw + "\n")
