from __future__ import annotations

import threading

from app.executive_controller.incident import (
    Incident,
    IncidentSeverity,
    IncidentStatus,
    IncidentStore,
)


class TestIncident:
    def test_create(self) -> None:
        inc = Incident(component_id="test", severity=IncidentSeverity.ERROR, title="boom")
        assert inc.component_id == "test"
        assert inc.severity == IncidentSeverity.ERROR
        assert inc.title == "boom"
        assert inc.id != ""

    def test_to_dict(self) -> None:
        inc = Incident(component_id="a", title="x")
        d = inc.to_dict()
        assert d["component_id"] == "a"
        assert d["status"] == "open"

    def test_default_severity(self) -> None:
        inc = Incident()
        assert inc.severity == IncidentSeverity.ERROR
        assert inc.status == IncidentStatus.OPEN


class TestIncidentStore:
    def test_record_and_get(self) -> None:
        store = IncidentStore()
        inc = Incident(component_id="comp", title="test")
        iid = store.record(inc)
        retrieved = store.get(iid)
        assert retrieved is not None
        assert retrieved.id == iid
        assert retrieved.component_id == "comp"

    def test_get_missing(self) -> None:
        store = IncidentStore()
        assert store.get("nonexistent") is None

    def test_get_by_component(self) -> None:
        store = IncidentStore()
        store.record(Incident(component_id="a", title="1"))
        store.record(Incident(component_id="a", title="2"))
        store.record(Incident(component_id="b", title="3"))
        assert len(store.get_by_component("a")) == 2
        assert len(store.get_by_component("b")) == 1

    def test_update_status(self) -> None:
        store = IncidentStore()
        inc = Incident(component_id="a")
        iid = store.record(inc)
        assert store.update_status(iid, IncidentStatus.RESOLVED, resolved_by="admin") is True
        retrieved = store.get(iid)
        assert retrieved is not None
        assert retrieved.status == IncidentStatus.RESOLVED
        assert retrieved.resolved_at is not None
        assert retrieved.resolved_by == "admin"

    def test_update_status_missing(self) -> None:
        store = IncidentStore()
        assert store.update_status("missing", IncidentStatus.RESOLVED) is False

    def test_get_all(self) -> None:
        store = IncidentStore()
        store.record(Incident(component_id="a"))
        store.record(Incident(component_id="b"))
        assert len(store.get_all()) == 2

    def test_get_open(self) -> None:
        store = IncidentStore()
        inc1 = Incident(component_id="a")
        inc2 = Incident(component_id="b", status=IncidentStatus.RESOLVED)
        iid1 = store.record(inc1)
        store.record(inc2)
        open_incidents = store.get_open()
        assert len(open_incidents) == 1
        assert open_incidents[0].id == iid1

    def test_count(self) -> None:
        store = IncidentStore()
        assert store.count() == 0
        store.record(Incident())
        assert store.count() == 1

    def test_clear(self) -> None:
        store = IncidentStore()
        store.record(Incident(component_id="a"))
        store.record(Incident(component_id="b"))
        store.clear()
        assert store.count() == 0

    def test_thread_safety(self) -> None:
        store = IncidentStore()
        errors: list[Exception] = []

        def worker() -> None:
            for i in range(100):
                try:
                    inc = Incident(component_id=f"comp-{i}")
                    iid = store.record(inc)
                    store.get(iid)
                    store.get_by_component(f"comp-{i}")
                    store.count()
                except Exception as e:
                    errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(errors) == 0
