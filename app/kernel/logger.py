from __future__ import annotations

import contextvars
import json
import os
import re
import threading
import time
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from app.core.event_bus import EventBus

# ---------------------------------------------------------------------------
# Correlation ID — propagated across async/thread boundaries via contextvars
# ---------------------------------------------------------------------------

_CORRELATION_ID: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "correlation_id", default=None
)
_CORRELATION_ID_THREAD = threading.local()


def get_correlation_id() -> Optional[str]:
    cid = _CORRELATION_ID.get(None)
    if cid is not None:
        return cid
    return getattr(_CORRELATION_ID_THREAD, "value", None)


def set_correlation_id(cid: str) -> None:
    _CORRELATION_ID.set(cid)
    _CORRELATION_ID_THREAD.value = cid


def reset_correlation_id() -> None:
    _CORRELATION_ID.set(None)
    if hasattr(_CORRELATION_ID_THREAD, "value"):
        del _CORRELATION_ID_THREAD.value


# ---------------------------------------------------------------------------
# Log levels
# ---------------------------------------------------------------------------

class LogLevel:
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

    _ORDER = {DEBUG: 0, INFO: 1, WARNING: 2, ERROR: 3, CRITICAL: 4}
    _ALL = (DEBUG, INFO, WARNING, ERROR, CRITICAL)

    @classmethod
    def is_enabled(cls, configured: str, target: str) -> bool:
        return cls._ORDER.get(target, 0) >= cls._ORDER.get(configured, 1)

    @classmethod
    def parse(cls, level: str) -> str:
        upper = level.upper()
        if upper in cls._ORDER:
            return upper
        return cls.INFO

    @classmethod
    def all(cls) -> tuple[str, ...]:
        return cls._ALL


# ---------------------------------------------------------------------------
# Structured logger
# ---------------------------------------------------------------------------

class LogEntry:
    """A single structured log entry, immutable after creation."""

    __slots__ = ("timestamp", "level", "message", "logger", "correlation_id",
                 "context", "source", "line")

    def __init__(
        self,
        timestamp: str,
        level: str,
        message: str,
        logger: str = "",
        correlation_id: str | None = None,
        context: dict[str, Any] | None = None,
        source: str = "",
        line: int = 0,
    ) -> None:
        self.timestamp = timestamp
        self.level = level
        self.message = message
        self.logger = logger
        self.correlation_id = correlation_id
        self.context = dict(context or {})
        self.source = source
        self.line = line

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "timestamp": self.timestamp,
            "level": self.level,
            "message": self.message,
        }
        if self.logger:
            d["logger"] = self.logger
        if self.correlation_id:
            d["correlation_id"] = self.correlation_id
        if self.context:
            d["context"] = self.context
        if self.source:
            d["source"] = self.source
        if self.line:
            d["line"] = self.line
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LogEntry:
        ctx = data.get("context")
        return cls(
            timestamp=data.get("timestamp", ""),
            level=data.get("level", "INFO"),
            message=data.get("message", ""),
            logger=data.get("logger", ""),
            correlation_id=data.get("correlation_id"),
            context=ctx if isinstance(ctx, dict) else {},
            source=data.get("source", ""),
            line=data.get("line", 0),
        )


class StructuredLogger:
    """Structured JSON logger with context and correlation ID support.

    Writes one JSON object per line to a log file, supports contextual
    logging via ``bind()``, correlation ID propagation, log rotation,
    and EventBus publishing.

    Thread-safe.
    """

    def __init__(
        self,
        name: str = "jarvis",
        level: str = "INFO",
        log_dir: str | Path | None = None,
        max_bytes: int = 10 * 1024 * 1024,
        backup_count: int = 5,
        event_bus: EventBus | None = None,
    ) -> None:
        self._name = name
        self._level = LogLevel.parse(level)
        self._max_bytes = max_bytes
        self._backup_count = backup_count
        self._event_bus = event_bus
        self._lock = threading.RLock()
        self._context: dict[str, Any] = {}
        self._entry_count: int = 0
        self._error_count: int = 0
        self._start_time: float = time.time()

        log_dir = Path(log_dir or "logs")
        log_dir.mkdir(parents=True, exist_ok=True)
        self._log_path: Path = log_dir / f"{name}.log.jsonl"
        self._file: Optional[Any] = None

    # ------------------------------------------------------------------
    # Core logging
    # ------------------------------------------------------------------

    def debug(self, message: str, **context: Any) -> None:
        self._log(LogLevel.DEBUG, message, context)

    def info(self, message: str, **context: Any) -> None:
        self._log(LogLevel.INFO, message, context)

    def warning(self, message: str, **context: Any) -> None:
        self._log(LogLevel.WARNING, message, context)

    def error(self, message: str, **context: Any) -> None:
        self._log(LogLevel.ERROR, message, context)

    def exception(self, message: str, **context: Any) -> None:
        import traceback
        tb = traceback.format_exc()
        ctx = dict(context)
        if tb and tb != "NoneType: None\n":
            ctx["traceback"] = tb.strip()
        self._log(LogLevel.ERROR, message, ctx)

    def critical(self, message: str, **context: Any) -> None:
        self._log(LogLevel.CRITICAL, message, context)

    def _log(self, level: str, message: str, extra_context: dict[str, Any]) -> None:
        if not LogLevel.is_enabled(self._level, level):
            return

        merged = dict(self._context)
        merged.update(extra_context)

        entry = LogEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            level=level,
            message=message,
            logger=self._name,
            correlation_id=get_correlation_id(),
            context=merged or None,
            source=self._get_source(),
            line=0,
        )

        with self._lock:
            self._entry_count += 1
            if level in (LogLevel.ERROR, LogLevel.CRITICAL):
                self._error_count += 1
            self._write_entry(entry)

        if self._event_bus:
            try:
                self._event_bus.publish("log.entry", entry.to_dict())
            except Exception:
                pass

    def _write_entry(self, entry: LogEntry) -> None:
        self._ensure_file_open()
        line = json.dumps(entry.to_dict(), ensure_ascii=False, default=str) + "\n"
        self._file.write(line)
        self._file.flush()
        if self._log_path.stat().st_size >= self._max_bytes:
            self._rotate()

    def _ensure_file_open(self) -> None:
        if self._file is None or self._file.closed:
            self._file = open(self._log_path, "a", encoding="utf-8")

    def _get_source(self) -> str:
        import traceback
        try:
            frames = traceback.extract_stack()
            for frame in reversed(frames):
                filename = Path(frame.filename).name
                if filename not in ("logger.py", "__init__.py", "threading.py",
                                    "traceback.py"):
                    return f"{filename}:{frame.lineno}"
        except Exception:
            pass
        return ""

    # ------------------------------------------------------------------
    # Context management
    # ------------------------------------------------------------------

    def bind(self, **kwargs: Any) -> StructuredLogger:
        """Return a child logger with additional permanent context.

        Usage::

            logger = root_logger.bind(request_id="abc", user="alice")
            logger.info("processing")  # includes request_id and user
        """
        child = StructuredLogger(
            name=self._name,
            level=self._level,
            log_dir=self._log_path.parent,
            max_bytes=self._max_bytes,
            backup_count=self._backup_count,
            event_bus=self._event_bus,
        )
        child._context = dict(self._context)
        child._context.update(kwargs)
        child._file = self._file
        return child

    # ------------------------------------------------------------------
    # Query / aggregation
    # ------------------------------------------------------------------

    def query(
        self,
        *,
        level: str | None = None,
        time_range: tuple[str, str] | None = None,
        source: str | None = None,
        correlation_id: str | None = None,
        message_pattern: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[LogEntry]:
        """Query log entries with optional filters.

        Args:
            level: Filter by log level (e.g. ``"ERROR"``).
            time_range: ``(start_iso, end_iso)`` inclusive.
            source: Filter by source filename (substring match).
            correlation_id: Exact match on correlation ID.
            message_pattern: Regex pattern to match against message.
            limit: Max entries to return (default 100).
            offset: Number of entries to skip.

        Returns:
            List of ``LogEntry`` objects matching the query.
        """
        result: list[LogEntry] = []
        pattern = re.compile(message_pattern) if message_pattern else None
        start_iso, end_iso = time_range if time_range else (None, None)

        for entry in self._iter_entries():
            if len(result) >= offset + limit:
                break
            if level and entry.level != level:
                continue
            if start_iso and entry.timestamp < start_iso:
                continue
            if end_iso and entry.timestamp > end_iso:
                continue
            if source and source not in entry.source:
                continue
            if correlation_id and entry.correlation_id != correlation_id:
                continue
            if pattern and not pattern.search(entry.message):
                continue
            result.append(entry)

        return result[offset:]

    def _iter_entries(self) -> Iterator[LogEntry]:
        path = self._log_path
        if not path.exists():
            return

        # Walk backup files too (numerical suffix order)
        files: list[Path] = []
        for p in path.parent.glob(f"{path.stem}.*.jsonl"):
            files.append(p)
        files.sort()
        files.append(path)

        for p in files:
            try:
                with open(p, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                            yield LogEntry.from_dict(data)
                        except json.JSONDecodeError:
                            continue
            except OSError:
                continue

    # ------------------------------------------------------------------
    # Rotation
    # ------------------------------------------------------------------

    def _rotate(self) -> None:
        try:
            self._close_file()
            path = self._log_path
            # Shift backups: .3→.4, .2→.3, .1→.2, .0→.1
            for i in range(self._backup_count - 1, -1, -1):
                src = path.parent / f"{path.stem}.{i}.jsonl"
                if src.exists():
                    dst = path.parent / f"{path.stem}.{i + 1}.jsonl"
                    src.rename(dst)
            # Rename current to .0
            path.rename(path.parent / f"{path.stem}.0.jsonl")
        except Exception:
            pass

    def _close_file(self) -> None:
        if self._file and not self._file.closed:
            self._file.close()
        self._file = None

    # ------------------------------------------------------------------
    # Health self-probe (following HealthMonitor pattern)
    # ------------------------------------------------------------------

    def health(self) -> dict[str, Any]:
        uptime = time.time() - self._start_time
        size = self._log_path.stat().st_size if self._log_path.exists() else 0
        return {
            "alive": True,
            "logger": self._name,
            "level": self._level,
            "entry_count": self._entry_count,
            "error_count": self._error_count,
            "uptime_seconds": uptime,
            "log_file": str(self._log_path),
            "file_size_bytes": size,
        }

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def close(self) -> None:
        with self._lock:
            self._close_file()
