from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from app.knowledge_graph.store import GraphStore

_DATA_DIR = Path("data") / "knowledge_graph"


@pytest.fixture
def store():
    name = f"test_kg_{uuid.uuid4().hex}.json"
    gs = GraphStore(filename=name)
    yield gs
    path = _DATA_DIR / name
    if path.exists():
        path.unlink()


@pytest.fixture
def populated_store(store):
    a = store.create_entity(type="agent", name="agent-a")
    b = store.create_entity(type="agent", name="agent-b")
    t = store.create_entity(type="tool", name="tool-1")
    rel1 = store.create_relationship(type="uses", source_id=a.id, target_id=t.id)
    rel2 = store.create_relationship(type="depends_on", source_id=b.id, target_id=a.id)
    return store, a, b, t, rel1, rel2


class TestGraphStore:
    def test_create_entity(self, store):
        e = store.create_entity(type="concept", name="test-entity")
        assert e.name == "test-entity"
        assert e.type == "concept"

    def test_create_entity_invalid_type(self, store):
        with pytest.raises(ValueError, match="Invalid entity type"):
            store.create_entity(type="nonexistent", name="test")

    def test_get_entity(self, store):
        e = store.create_entity(type="concept", name="test")
        retrieved = store.get_entity(e.id)
        assert retrieved is not None
        assert retrieved.id == e.id

    def test_get_entity_missing(self, store):
        assert store.get_entity("nonexistent") is None

    def test_get_entity_by_name(self, store):
        e1 = store.create_entity(type="concept", name="shared")
        e2 = store.create_entity(type="concept", name="shared")
        results = store.get_entity_by_name("shared")
        assert len(results) == 2

    def test_get_entities_by_type(self, store):
        store.create_entity(type="agent", name="a1")
        store.create_entity(type="agent", name="a2")
        store.create_entity(type="tool", name="t1")
        agents = store.get_entities_by_type("agent")
        assert len(agents) == 2
        tools = store.get_entities_by_type("tool")
        assert len(tools) == 1

    def test_list_entities(self, store):
        store.create_entity(type="concept", name="a")
        store.create_entity(type="concept", name="b")
        assert len(store.list_entities()) == 2

    def test_update_entity(self, store):
        e = store.create_entity(type="concept", name="old")
        updated = store.update_entity(e.id, name="new", properties={"key": "val"})
        assert updated is not None
        assert updated.name == "new"
        assert "key" in updated.properties
        assert updated.properties["key"] == "val"

    def test_update_entity_missing(self, store):
        assert store.update_entity("nonexistent", name="new") is None

    def test_delete_entity(self, store):
        e = store.create_entity(type="concept", name="test")
        assert store.delete_entity(e.id) is True
        assert store.get_entity(e.id) is None

    def test_delete_entity_missing(self, store):
        assert store.delete_entity("nonexistent") is False

    def test_delete_entity_cascades_relationships(self, store):
        a = store.create_entity(type="agent", name="a")
        b = store.create_entity(type="agent", name="b")
        store.create_relationship(type="depends_on", source_id=a.id, target_id=b.id)
        store.delete_entity(a.id)
        assert store.relationship_count() == 0

    def test_entity_count(self, store):
        assert store.entity_count() == 0
        store.create_entity(type="concept", name="a")
        assert store.entity_count() == 1

    def test_create_relationship(self, store):
        a = store.create_entity(type="agent", name="a")
        b = store.create_entity(type="agent", name="b")
        rel = store.create_relationship(type="depends_on", source_id=a.id, target_id=b.id)
        assert rel.type == "depends_on"
        assert rel.source_id == a.id
        assert rel.target_id == b.id

    def test_create_relationship_invalid_type(self, store):
        a = store.create_entity(type="agent", name="a")
        b = store.create_entity(type="agent", name="b")
        with pytest.raises(ValueError, match="Invalid relationship type"):
            store.create_relationship(type="nonexistent", source_id=a.id, target_id=b.id)

    def test_create_relationship_missing_source(self, store):
        b = store.create_entity(type="agent", name="b")
        with pytest.raises(ValueError, match="Source entity"):
            store.create_relationship(type="depends_on", source_id="missing", target_id=b.id)

    def test_create_relationship_missing_target(self, store):
        a = store.create_entity(type="agent", name="a")
        with pytest.raises(ValueError, match="Target entity"):
            store.create_relationship(type="depends_on", source_id=a.id, target_id="missing")

    def test_get_relationship(self, store):
        a = store.create_entity(type="agent", name="a")
        b = store.create_entity(type="agent", name="b")
        rel = store.create_relationship(type="depends_on", source_id=a.id, target_id=b.id)
        entry = store.get_relationship(rel.id)
        assert entry is not None
        assert entry["type"] == "depends_on"

    def test_get_outgoing_relationships(self, store):
        a = store.create_entity(type="agent", name="a")
        b = store.create_entity(type="agent", name="b")
        store.create_relationship(type="depends_on", source_id=a.id, target_id=b.id)
        outgoing = store.get_outgoing_relationships(a.id)
        assert len(outgoing) == 1
        assert outgoing[0]["target_id"] == b.id

    def test_get_incoming_relationships(self, store):
        a = store.create_entity(type="agent", name="a")
        b = store.create_entity(type="agent", name="b")
        store.create_relationship(type="depends_on", source_id=a.id, target_id=b.id)
        incoming = store.get_incoming_relationships(b.id)
        assert len(incoming) == 1
        assert incoming[0]["source_id"] == a.id

    def test_get_relationships_by_type(self, populated_store):
        store, a, b, t, rel1, rel2 = populated_store
        results = store.get_relationships_by_type("uses")
        assert len(results) == 1
        results = store.get_relationships_by_type("depends_on")
        assert len(results) == 1

    def test_update_relationship(self, store):
        a = store.create_entity(type="agent", name="a")
        b = store.create_entity(type="agent", name="b")
        rel = store.create_relationship(type="depends_on", source_id=a.id, target_id=b.id)
        updated = store.update_relationship(rel.id, properties={"weight": 2.0})
        assert updated is not None
        assert updated["properties"]["weight"] == 2.0

    def test_update_relationship_missing(self, store):
        assert store.update_relationship("nonexistent", properties={}) is None

    def test_delete_relationship(self, populated_store):
        store, a, b, t, rel1, rel2 = populated_store
        assert store.relationship_count() == 2
        assert store.delete_relationship(rel1.id) is True
        assert store.relationship_count() == 1

    def test_delete_relationship_missing(self, store):
        assert store.delete_relationship("nonexistent") is False

    def test_relationship_count(self, store):
        assert store.relationship_count() == 0
        a = store.create_entity(type="agent", name="a")
        b = store.create_entity(type="agent", name="b")
        store.create_relationship(type="depends_on", source_id=a.id, target_id=b.id)
        assert store.relationship_count() == 1

    def test_bfs_traversal(self, populated_store):
        store, a, b, t, rel1, rel2 = populated_store
        results = store.bfs(a.id, max_depth=5)
        assert len(results) >= 1

    def test_dfs_traversal(self, populated_store):
        store, a, b, t, rel1, rel2 = populated_store
        results = store.dfs(a.id, max_depth=5)
        assert len(results) >= 1

    def test_search(self, store):
        store.create_entity(type="agent", name="test-agent", properties={"version": "1.0"})
        store.create_entity(type="tool", name="other-tool")
        results = store.search("agent")
        assert len(results) == 1
        assert results[0].name == "test-agent"

    def test_search_finds_by_property(self, store):
        store.create_entity(type="concept", name="thing", properties={"description": "special value"})
        results = store.search("special")
        assert len(results) == 1

    def test_health(self, store):
        store.create_entity(type="agent", name="a")
        health = store.health()
        assert health["alive"] is True
        assert health["entity_count"] == 1

    def test_clear(self, store):
        store.create_entity(type="agent", name="a")
        store.create_entity(type="agent", name="b")
        a = store.get_entity_by_name("a")[0]
        b = store.get_entity_by_name("b")[0]
        store.create_relationship(type="depends_on", source_id=a.id, target_id=b.id)
        store.clear()
        assert store.entity_count() == 0
        assert store.relationship_count() == 0

    def test_persistence(self, store):
        store.create_entity(type="agent", name="persist-test")
        store.save()
        store2 = GraphStore(filename=store.path.name)
        assert store2.entity_count() == 1
        entities = store2.list_entities()
        assert entities[0].name == "persist-test"

    def test_transaction_commit(self, store):
        tx = store.begin_transaction()
        e = store.create_entity(type="agent", name="tx-test")
        # Transaction doesn't modify data directly, it's for multi-step atomicity
        # Here we just verify the API works
        store.commit_transaction(tx)
        assert store.get_entity(e.id) is not None

    def test_transaction_rollback(self, store):
        tx = store.begin_transaction()
        store.rollback_transaction(tx)
        assert tx.is_committed is False

    def test_event_publishing_on_create(self):
        from app.core.event_bus import EventBus

        bus = EventBus()
        events: list[str] = []
        bus.subscribe_wildcard("knowledge_graph.*", lambda evt, **kw: events.append(evt))
        gs = GraphStore(filename=f"test_evt_{uuid.uuid4().hex}.json", event_bus=bus)
        gs.create_entity(type="concept", name="event-test")
        assert any("knowledge_graph.entity.created" in e for e in events)
        path = _DATA_DIR / gs.path.name
        if path.exists():
            path.unlink()

    def test_event_publishing_on_delete(self):
        from app.core.event_bus import EventBus

        bus = EventBus()
        events: list[str] = []
        bus.subscribe_wildcard("knowledge_graph.*", lambda evt, **kw: events.append(evt))
        gs = GraphStore(filename=f"test_evt2_{uuid.uuid4().hex}.json", event_bus=bus)
        e = gs.create_entity(type="concept", name="to-delete")
        events.clear()
        gs.delete_entity(e.id)
        assert any("knowledge_graph.entity.deleted" in e for e in events)
        path = _DATA_DIR / gs.path.name
        if path.exists():
            path.unlink()

    def test_health_self_probe(self, store):
        health = store.health()
        assert "alive" in health
        assert "entity_count" in health
        assert "relationship_count" in health

    def test_search_returns_matching_entities(self, store):
        store.create_entity(type="agent", name="alpha")
        store.create_entity(type="tool", name="beta")
        results = store.search("alpha")
        assert len(results) == 1
        assert results[0].name == "alpha"
