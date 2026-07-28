from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from app.kernel.audit import AuditEvent, AuditLogger, AuditVerificationResult
from app.core.event_bus import EventBus


# ======================================================================
# AuditEvent tests
# ======================================================================

class TestAuditEvent:
    def test_to_dict_contains_required_keys(self):
        event = AuditEvent(
            event_id="e1",
            timestamp=1000.0,
            event_type="config.change",
            actor="system",
            action="set",
        )
        d = event.to_dict()
        assert d["event_id"] == "e1"
        assert d["timestamp"] == 1000.0
        assert d["event_type"] == "config.change"
        assert d["actor"] == "system"
        assert d["action"] == "set"
        assert d["outcome"] == "success"

    def test_to_dict_omits_empty_fields(self):
        event = AuditEvent(
            event_id="e1", timestamp=0.0,
            event_type="t", actor="a", action="x",
        )
        d = event.to_dict()
        assert "resource" not in d
        assert "correlation_id" not in d
        assert "metadata" not in d
        # prev_hash and signature are always included for chain integrity
        assert "prev_hash" in d
        assert "signature" in d

    def test_to_dict_includes_optional_fields(self):
        event = AuditEvent(
            event_id="e1", timestamp=0.0,
            event_type="t", actor="a", action="x",
            resource="cfg", outcome="denied",
            correlation_id="cid",
            metadata={"reason": "no permission"},
            prev_hash="abc", signature="sig123",
        )
        d = event.to_dict()
        assert d["resource"] == "cfg"
        assert d["outcome"] == "denied"
        assert d["correlation_id"] == "cid"
        assert d["metadata"] == {"reason": "no permission"}
        assert d["prev_hash"] == "abc"
        assert d["signature"] == "sig123"

    def test_from_dict_round_trip(self):
        original = AuditEvent(
            event_id="e1", timestamp=1234.0,
            event_type="perm.check", actor="admin",
            action="require", resource="config.write",
            outcome="allowed",
            correlation_id="req-1",
            metadata={"ip": "::1"},
            prev_hash="prev123", signature="sig456",
        )
        d = original.to_dict()
        restored = AuditEvent.from_dict(d)
        assert restored.event_id == original.event_id
        assert restored.timestamp == original.timestamp
        assert restored.event_type == original.event_type
        assert restored.actor == original.actor
        assert restored.action == original.action
        assert restored.resource == original.resource
        assert restored.outcome == original.outcome
        assert restored.correlation_id == original.correlation_id
        assert restored.metadata == original.metadata
        assert restored.prev_hash == original.prev_hash
        assert restored.signature == original.signature

    def test_to_json_line_is_valid_json(self):
        event = AuditEvent(
            event_id="e1", timestamp=0.0,
            event_type="t", actor="a", action="x",
        )
        line = event.to_json_line()
        data = json.loads(line)
        assert data["event_id"] == "e1"


# ======================================================================
# AuditLogger tests
# ======================================================================

@pytest.fixture
def audit_logger(tmp_path: Path) -> AuditLogger:
    return AuditLogger(log_dir=tmp_path)


class TestAuditLoggerCore:
    def test_record_returns_event_id(self, audit_logger: AuditLogger):
        eid = audit_logger.record("test.event", "admin", "do_something")
        assert isinstance(eid, str)
        assert len(eid) > 0

    def test_record_increments_count(self, audit_logger: AuditLogger):
        audit_logger.record("t1", "admin", "act1")
        assert audit_logger._entry_count == 1
        audit_logger.record("t2", "admin", "act2")
        assert audit_logger._entry_count == 2

    def test_record_persists_to_file(self, audit_logger: AuditLogger, tmp_path: Path):
        audit_logger.record("test.event", "admin", "create")
        files = list(tmp_path.glob("audit.*.jsonl"))
        assert len(files) == 1
        content = files[0].read_text(encoding="utf-8")
        assert "test.event" in content
        assert "admin" in content
        assert "create" in content

    def test_record_creates_valid_json(self, audit_logger: AuditLogger, tmp_path: Path):
        audit_logger.record("evt", "actor", "act")
        files = list(tmp_path.glob("audit.*.jsonl"))
        line = files[0].read_text(encoding="utf-8").strip()
        data = json.loads(line)
        assert data["event_type"] == "evt"
        assert data["actor"] == "actor"

    def test_record_stores_prev_hash_for_chaining(self, audit_logger: AuditLogger):
        audit_logger.record("e1", "a", "x")
        audit_logger.record("e2", "a", "y")
        events = audit_logger.query(limit=10)
        assert len(events) == 2
        # Second entry's prev_hash should be non-empty (chained to first)
        assert events[1].prev_hash != ""


class TestAuditLoggerHmacIntegrity:
    def test_entries_have_signature(self, audit_logger: AuditLogger):
        audit_logger.record("evt", "admin", "act")
        events = audit_logger.query(limit=10)
        assert len(events) == 1
        assert events[0].signature != ""

    def test_signature_differs_per_entry(self, audit_logger: AuditLogger):
        audit_logger.record("e1", "admin", "act")
        audit_logger.record("e2", "admin", "act")
        events = audit_logger.query(limit=10)
        assert events[0].signature != events[1].signature


class TestAuditLoggerVerify:
    def test_verify_passes_for_intact_log(self, audit_logger: AuditLogger):
        audit_logger.record("e1", "admin", "create")
        audit_logger.record("e2", "admin", "update")
        result = audit_logger.verify()
        assert result.valid is True
        assert result.total_entries == 2
        assert result.verified_entries == 2

    def test_verify_empty_log(self, audit_logger: AuditLogger):
        result = audit_logger.verify()
        assert result.valid is True
        assert result.total_entries == 0

    def test_verify_detects_tampered_entry(self, audit_logger: AuditLogger, tmp_path: Path):
        audit_logger.record("e1", "admin", "create")
        audit_logger.record("e2", "admin", "update")
        # Tamper with the file
        files = list(tmp_path.glob("audit.*.jsonl"))
        content = files[0].read_text(encoding="utf-8")
        tampered = content.replace("admin", "hacker", 1)
        files[0].write_text(tampered, encoding="utf-8")
        # Verify should fail
        result = audit_logger.verify()
        assert result.valid is False
        assert len(result.errors) >= 1

    def test_verify_reports_error_count(self, audit_logger: AuditLogger, tmp_path: Path):
        audit_logger.record("e1", "admin", "create")
        audit_logger.record("e2", "admin", "update")
        audit_logger.record("e3", "admin", "delete")
        # Corrupt the middle entry
        files = list(tmp_path.glob("audit.*.jsonl"))
        lines = files[0].read_text(encoding="utf-8").strip().split("\n")
        lines[1] = '{"event_id":"tampered"}'
        files[0].write_text("\n".join(lines) + "\n", encoding="utf-8")
        result = audit_logger.verify()
        assert result.valid is False
        assert result.first_error_offset >= 1


class TestAuditLoggerQuery:
    def test_query_all(self, audit_logger: AuditLogger):
        audit_logger.record("e1", "admin", "create")
        audit_logger.record("e2", "user", "read")
        entries = audit_logger.query()
        assert len(entries) == 2

    def test_query_by_event_type(self, audit_logger: AuditLogger):
        audit_logger.record("config.change", "admin", "set")
        audit_logger.record("perm.check", "admin", "require")
        audit_logger.record("config.change", "admin", "delete")
        entries = audit_logger.query(event_type="config.change")
        assert len(entries) == 2
        assert all(e.event_type == "config.change" for e in entries)

    def test_query_by_actor(self, audit_logger: AuditLogger):
        audit_logger.record("e1", "admin", "create")
        audit_logger.record("e2", "user", "read")
        audit_logger.record("e3", "admin", "update")
        entries = audit_logger.query(actor="admin")
        assert len(entries) == 2

    def test_query_by_outcome(self, audit_logger: AuditLogger):
        audit_logger.record("e1", "a", "x", outcome="allowed")
        audit_logger.record("e2", "a", "x", outcome="denied")
        audit_logger.record("e3", "a", "x", outcome="allowed")
        entries = audit_logger.query(outcome="denied")
        assert len(entries) == 1

    def test_query_by_action_substring(self, audit_logger: AuditLogger):
        audit_logger.record("e1", "a", "user.create")
        audit_logger.record("e2", "a", "user.delete")
        audit_logger.record("e3", "a", "config.set")
        entries = audit_logger.query(action="user")
        assert len(entries) == 2

    def test_query_limit(self, audit_logger: AuditLogger):
        for i in range(20):
            audit_logger.record(f"e{i}", "admin", "act")
        entries = audit_logger.query(limit=5)
        assert len(entries) == 5

    def test_query_offset(self, audit_logger: AuditLogger):
        for i in range(10):
            audit_logger.record(f"e{i}", "admin", f"act{i}")
        entries = audit_logger.query(limit=5, offset=5)
        assert len(entries) == 5
        assert entries[0].action == "act5"

    def test_query_empty(self, audit_logger: AuditLogger):
        assert audit_logger.query() == []


class TestAuditLoggerEventBus:
    def test_publishes_on_record(self, tmp_path: Path):
        bus = EventBus()
        logger = AuditLogger(log_dir=tmp_path, event_bus=bus)
        received: list = []
        bus.subscribe("audit.entry", received.append)
        logger.record("test.event", "admin", "create")
        assert len(received) == 1
        assert received[0]["event_type"] == "test.event"

    def test_no_event_bus_does_not_raise(self, tmp_path: Path):
        logger = AuditLogger(log_dir=tmp_path, event_bus=None)
        logger.record("t", "a", "x")  # Should not raise


class TestAuditLoggerHealth:
    def test_health_returns_dict(self, audit_logger: AuditLogger):
        h = audit_logger.health()
        assert h["alive"] is True
        assert h["entry_count"] == 0
        assert h["error_count"] == 0
        assert h["uptime_seconds"] >= 0
        assert h["log_dir"]

    def test_health_after_records(self, audit_logger: AuditLogger):
        audit_logger.record("e1", "a", "x")
        audit_logger.record("e2", "a", "x", outcome="denied")
        h = audit_logger.health()
        assert h["entry_count"] == 2
        assert h["error_count"] == 1


class TestAuditLoggerThreadSafety:
    def test_concurrent_records(self, tmp_path: Path):
        logger = AuditLogger(log_dir=tmp_path)
        errors: list[Exception] = []

        def worker(n: int) -> None:
            try:
                for i in range(30):
                    logger.record(f"evt", f"worker-{n}", f"act-{i}")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,))
                   for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        entries = logger.query(limit=200)
        assert len(entries) == 120


class TestAuditLoggerEdgeCases:
    def test_custom_hmac_key(self, tmp_path: Path):
        logger = AuditLogger(log_dir=tmp_path, hmac_key=b"custom-key")
        logger.record("e1", "admin", "create")
        entries = logger.query()
        assert len(entries) == 1
        assert entries[0].signature != ""

    def test_verify_with_different_key_fails(self, tmp_path: Path):
        logger = AuditLogger(log_dir=tmp_path, hmac_key=b"key-a")
        logger.record("e1", "admin", "create")
        logger.close()

        # Re-open with different key
        logger2 = AuditLogger(log_dir=tmp_path, hmac_key=b"key-b")
        result = logger2.verify()
        assert result.valid is False
        assert "signature mismatch" in result.errors[0]

    def test_close_and_reopen(self, tmp_path: Path):
        logger = AuditLogger(log_dir=tmp_path)
        logger.record("e1", "a", "x")
        logger.close()

        logger2 = AuditLogger(log_dir=tmp_path)
        logger2.record("e2", "b", "y")
        entries = logger2.query(limit=10)
        assert len(entries) == 2
        assert entries[0].event_id != entries[1].event_id


class TestAuditVerificationResult:
    def test_bool_true_when_valid(self):
        r = AuditVerificationResult(valid=True)
        assert bool(r) is True

    def test_bool_false_when_invalid(self):
        r = AuditVerificationResult(valid=False, errors=["bad"])
        assert bool(r) is False

    def test_repr(self):
        r = AuditVerificationResult(valid=True, total_entries=5, verified_entries=5)
        assert "valid=True" in repr(r)
        assert "total=5" in repr(r)
