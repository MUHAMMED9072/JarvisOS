from __future__ import annotations

import hashlib
import hmac
import json
import threading
import time
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from app.core.event_bus import EventBus
from app.kernel.logger import get_correlation_id


# ---------------------------------------------------------------------------
# Audit event schema
# ---------------------------------------------------------------------------

class AuditEvent:
    """An audit trail entry, immutable after creation.

    Fields follow the standard audit event schema used across the system.
    """

    __slots__ = (
        "event_id", "timestamp", "event_type", "actor", "action",
        "resource", "outcome", "correlation_id", "metadata",
        "prev_hash", "signature",
    )

    def __init__(
        self,
        event_id: str,
        timestamp: float,
        event_type: str,
        actor: str,
        action: str,
        resource: str = "",
        outcome: str = "success",
        correlation_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        prev_hash: str = "",
        signature: str = "",
    ) -> None:
        self.event_id = event_id
        self.timestamp = timestamp
        self.event_type = event_type
        self.actor = actor
        self.action = action
        self.resource = resource
        self.outcome = outcome
        self.correlation_id = correlation_id
        self.metadata = dict(metadata or {})
        self.prev_hash = prev_hash
        self.signature = signature

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "actor": self.actor,
            "action": self.action,
        }
        if self.resource:
            d["resource"] = self.resource
        d["outcome"] = self.outcome
        if self.correlation_id:
            d["correlation_id"] = self.correlation_id
        if self.metadata:
            d["metadata"] = self.metadata
        d["prev_hash"] = self.prev_hash
        d["signature"] = self.signature
        return d

    def to_json_line(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, default=str,
                          sort_keys=True)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AuditEvent:
        meta = data.get("metadata")
        return cls(
            event_id=data.get("event_id", ""),
            timestamp=data.get("timestamp", 0.0),
            event_type=data.get("event_type", ""),
            actor=data.get("actor", ""),
            action=data.get("action", ""),
            resource=data.get("resource", ""),
            outcome=data.get("outcome", "success"),
            correlation_id=data.get("correlation_id"),
            metadata=meta if isinstance(meta, dict) else {},
            prev_hash=data.get("prev_hash", ""),
            signature=data.get("signature", ""),
        )


# ---------------------------------------------------------------------------
# Verification result
# ---------------------------------------------------------------------------

class AuditVerificationResult:
    """Result of an audit log integrity verification."""

    def __init__(
        self,
        valid: bool,
        total_entries: int = 0,
        verified_entries: int = 0,
        errors: list[str] | None = None,
        first_error_offset: int = -1,
    ) -> None:
        self.valid = valid
        self.total_entries = total_entries
        self.verified_entries = verified_entries
        self.errors = errors or []
        self.first_error_offset = first_error_offset

    def __bool__(self) -> bool:
        return self.valid

    def __repr__(self) -> str:
        return (
            f"AuditVerificationResult(valid={self.valid}, "
            f"total={self.total_entries}, "
            f"verified={self.verified_entries}, "
            f"errors={len(self.errors)})"
        )


# ---------------------------------------------------------------------------
# Audit logger
# ---------------------------------------------------------------------------

def _default_hmac_key() -> bytes:
    return b"jarvis-audit-hmac-key-change-in-production"


class AuditLogger:
    """Append-only audit log with cryptographic integrity verification.

    Every entry is chained to the previous entry via SHA-256 hash and
    signed with HMAC-SHA256.  Tampering with any entry breaks the chain
    and is detectable via ``verify()``.

    Thread-safe.
    """

    def __init__(
        self,
        log_dir: str | Path = "data/audit",
        hmac_key: bytes | None = None,
        event_bus: EventBus | None = None,
    ) -> None:
        self._log_dir = Path(log_dir)
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._hmac_key = hmac_key if hmac_key is not None else _default_hmac_key()
        self._event_bus = event_bus
        self._lock = threading.RLock()
        self._entry_count: int = 0
        self._error_count: int = 0
        self._start_time: float = time.time()

        self._file: Any = None
        self._current_path: Path = self._daily_path()
        self._prev_hash: str = self._load_last_hash()

    def _daily_path(self) -> Path:
        date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
        return self._log_dir / f"audit.{date_str}.jsonl"

    def _load_last_hash(self) -> str:
        """Read the last entry from the current audit file and compute its
        hash for chaining the next entry."""
        path = self._daily_path()
        if not path.exists():
            return ""
        last_line = ""
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        last_line = line
            if last_line:
                return self._compute_line_hash(last_line)
        except Exception:
            pass
        return ""

    # Actually, let me reconsider. The `prev_hash` field in each entry
    # stores the hash of the *previous* line. To find the hash to use
    # for the next entry, I need to compute the hash of the *last* line.

    def _compute_line_hash(self, line: str) -> str:
        return hashlib.sha256(line.encode("utf-8")).hexdigest()

    def _compute_signature(self, line_without_sig: str) -> str:
        return hmac.new(
            self._hmac_key,
            line_without_sig.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record(
        self,
        event_type: str,
        actor: str,
        action: str,
        resource: str = "",
        outcome: str = "success",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Record an audit event.

        Returns the event ID (UUID-style string).
        """
        event_id = f"{int(time.time() * 1_000_000):x}-{self._entry_count:x}"

        entry = AuditEvent(
            event_id=event_id,
            timestamp=time.time(),
            event_type=event_type,
            actor=actor,
            action=action,
            resource=resource,
            outcome=outcome,
            correlation_id=get_correlation_id(),
            metadata=metadata,
        )

        with self._lock:
            self._ensure_file_open()
            entry.prev_hash = self._prev_hash
            # Build dict for signing: all fields including prev_hash, excluding signature
            signing_dict = {k: v for k, v in entry.to_dict().items() if k != "signature"}
            entry.signature = self._compute_signature(
                json.dumps(signing_dict, ensure_ascii=False, default=str, sort_keys=True)
            )
            signed_line = entry.to_json_line()

            self._file.write(signed_line + "\n")
            self._file.flush()

            self._prev_hash = self._compute_line_hash(signed_line)
            self._entry_count += 1
            if outcome in ("denied", "failure", "error"):
                self._error_count += 1

        if self._event_bus:
            try:
                self._event_bus.publish("audit.entry", entry.to_dict())
            except Exception:
                pass

        return event_id

    def _ensure_file_open(self) -> None:
        path = self._daily_path()
        if self._file is None or self._file.closed or path != self._current_path:
            if self._file and not self._file.closed:
                self._file.close()
            self._current_path = path
            self._file = open(path, "a", encoding="utf-8")

    # ------------------------------------------------------------------
    # Integrity verification
    # ------------------------------------------------------------------

    def verify(self) -> AuditVerificationResult:
        """Verify the integrity of the entire audit log.

        Iterates all audit files, checks the HMAC chain and prev_hash
        linkage.  Returns an ``AuditVerificationResult``.
        """
        errors: list[str] = []
        total = 0
        verified = 0
        prev_hash = ""
        first_error_offset = -1

        for offset, entry_dict in enumerate(self._iter_all_entries()):
            total += 1
            stored_signature = entry_dict.pop("signature", "")
            stored_prev_hash = entry_dict.get("prev_hash", "")

            # Check prev_hash chain
            if stored_prev_hash != prev_hash:
                msg = (
                    f"Entry {total}: prev_hash mismatch "
                    f"(expected {prev_hash[:16]}..., got {stored_prev_hash[:16]}...)"
                )
                errors.append(msg)
                if first_error_offset < 0:
                    first_error_offset = offset

            # Check HMAC (includes prev_hash in entry_dict)
            expected_sig = self._compute_signature(
                json.dumps(entry_dict, ensure_ascii=False, default=str, sort_keys=True)
            )
            if stored_signature != expected_sig:
                msg = f"Entry {total}: signature mismatch (tampered)"
                errors.append(msg)
                if first_error_offset < 0:
                    first_error_offset = offset

            # Compute the hash of this entry for the next chain check
            entry_dict["signature"] = stored_signature
            line = json.dumps(entry_dict, ensure_ascii=False, default=str, sort_keys=True)
            prev_hash = self._compute_line_hash(line)
            verified += 1

        return AuditVerificationResult(
            valid=len(errors) == 0,
            total_entries=total,
            verified_entries=verified,
            errors=errors,
            first_error_offset=first_error_offset,
        )

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def query(
        self,
        *,
        event_type: str | None = None,
        actor: str | None = None,
        time_range: tuple[float, float] | None = None,
        outcome: str | None = None,
        action: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditEvent]:
        """Query audit events with optional filters.

        Args:
            event_type: Filter by event type (exact match).
            actor: Filter by actor (exact match).
            time_range: ``(start_timestamp, end_timestamp)`` inclusive.
            outcome: Filter by outcome (exact match).
            action: Filter by action (substring match).
            limit: Max entries to return (default 100).
            offset: Number of entries to skip.

        Returns:
            List of matching ``AuditEvent`` objects.
        """
        result: list[AuditEvent] = []
        start_ts, end_ts = time_range if time_range else (None, None)

        for entry in self._iter_entries():
            if len(result) >= offset + limit:
                break
            if event_type and entry.event_type != event_type:
                continue
            if actor and entry.actor != actor:
                continue
            if start_ts is not None and entry.timestamp < start_ts:
                continue
            if end_ts is not None and entry.timestamp > end_ts:
                continue
            if outcome and entry.outcome != outcome:
                continue
            if action and action not in entry.action:
                continue
            result.append(entry)

        return result[offset:]

    def _iter_entries(self) -> Iterator[AuditEvent]:
        for data in self._iter_all_entries():
            yield AuditEvent.from_dict(data)

    def _iter_all_entries(self) -> Iterator[dict[str, Any]]:
        files = sorted(self._log_dir.glob("audit.*.jsonl"))
        for p in files:
            try:
                with open(p, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            yield json.loads(line)
                        except json.JSONDecodeError:
                            continue
            except OSError:
                continue

    # ------------------------------------------------------------------
    # Health self-probe
    # ------------------------------------------------------------------

    def health(self) -> dict[str, Any]:
        uptime = time.time() - self._start_time
        return {
            "alive": True,
            "entry_count": self._entry_count,
            "error_count": self._error_count,
            "uptime_seconds": uptime,
            "log_dir": str(self._log_dir),
            "current_file": str(self._current_path),
        }

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def close(self) -> None:
        with self._lock:
            if self._file and not self._file.closed:
                self._file.close()
            self._file = None
