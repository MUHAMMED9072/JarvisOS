from __future__ import annotations

import time

import pytest

from app.agents.memory import AgentMemory, MemoryEntry, MemoryType


@pytest.fixture
def mem():
    return AgentMemory("agent-1")


class TestMemoryEntry:
    def test_expired_no_ttl(self):
        e = MemoryEntry(agent_id="a", memory_type=MemoryType.WORKING, key="k")
        assert e.is_expired() is False

    def test_expired_with_ttl(self):
        e = MemoryEntry(agent_id="a", memory_type=MemoryType.WORKING, key="k",
                        ttl_seconds=0.1, created_at=time.time() - 1)
        assert e.is_expired() is True

    def test_not_expired(self):
        e = MemoryEntry(agent_id="a", memory_type=MemoryType.WORKING, key="k",
                        ttl_seconds=3600)
        assert e.is_expired() is False

    def test_to_dict(self):
        e = MemoryEntry(agent_id="a1", memory_type=MemoryType.EPISODIC, key="k1",
                        content="hello", tags=["x"], permissions=["p1"])
        d = e.to_dict()
        assert d["agent_id"] == "a1"
        assert d["memory_type"] == "episodic"
        assert d["key"] == "k1"
        assert d["content"] == "hello"
        assert d["tags"] == ["x"]
        assert d["permissions"] == ["p1"]


class TestAgentMemoryBasicCRUD:
    def test_store_and_retrieve(self, mem):
        entry = mem.store(MemoryType.WORKING, "task_1", {"cmd": "analyze"})
        assert entry.key == "task_1"
        assert entry.agent_id == "agent-1"

        retrieved = mem.retrieve(MemoryType.WORKING, "task_1")
        assert retrieved is not None
        assert retrieved.content == {"cmd": "analyze"}

    def test_retrieve_missing(self, mem):
        assert mem.retrieve(MemoryType.WORKING, "nope") is None

    def test_retrieve_expired(self, mem):
        mem.store(MemoryType.WORKING, "exp_1", "data", ttl_seconds=0.01)
        time.sleep(0.02)
        assert mem.retrieve(MemoryType.WORKING, "exp_1") is None

    def test_update(self, mem):
        mem.store(MemoryType.SEMANTIC, "fact_1", "old_value")
        assert mem.update(MemoryType.SEMANTIC, "fact_1", "new_value") is True
        entry = mem.retrieve(MemoryType.SEMANTIC, "fact_1")
        assert entry is not None
        assert entry.content == "new_value"

    def test_update_missing(self, mem):
        assert mem.update(MemoryType.SEMANTIC, "nope", "x") is False

    def test_delete(self, mem):
        mem.store(MemoryType.EPISODIC, "outcome_1", "success")
        assert mem.delete(MemoryType.EPISODIC, "outcome_1") is True
        assert mem.retrieve(MemoryType.EPISODIC, "outcome_1") is None

    def test_delete_missing(self, mem):
        assert mem.delete(MemoryType.EPISODIC, "nope") is False

    def test_list(self, mem):
        mem.store(MemoryType.WORKING, "a", 1)
        mem.store(MemoryType.WORKING, "b", 2)
        assert len(mem.list(MemoryType.WORKING)) == 2


class TestAgentMemorySearch:
    def test_search_by_key(self, mem):
        mem.store(MemoryType.SEMANTIC, "python_version", "3.12")
        mem.store(MemoryType.SEMANTIC, "node_version", "v20")
        results = mem.search("python")
        assert len(results) == 1
        assert results[0].key == "python_version"

    def test_search_by_content(self, mem):
        mem.store(MemoryType.SEMANTIC, "note", "important data point")
        results = mem.search("important")
        assert len(results) == 1

    def test_search_by_tag(self, mem):
        mem.store(MemoryType.PROCEDURAL, "build", "steps", tags=["ci", "deploy"])
        mem.store(MemoryType.PROCEDURAL, "test", "steps", tags=["qa"])
        results = mem.search("deploy")
        assert len(results) == 1

    def test_search_across_types(self, mem):
        mem.store(MemoryType.WORKING, "temp", "abc")
        mem.store(MemoryType.EPISODIC, "past", "abc")
        results = mem.search("abc")
        assert len(results) == 2

    def test_search_filtered_by_type(self, mem):
        mem.store(MemoryType.WORKING, "temp", "abc")
        mem.store(MemoryType.EPISODIC, "past", "abc")
        results = mem.search("abc", memory_type=MemoryType.WORKING)
        assert len(results) == 1


class TestAgentMemoryWorking:
    def test_clear_working(self, mem):
        mem.store(MemoryType.WORKING, "t1", "x")
        mem.store(MemoryType.WORKING, "t2", "y")
        mem.store(MemoryType.EPISODIC, "e1", "keep")
        count = mem.clear_working()
        assert count == 2
        assert mem.count(MemoryType.WORKING) == 0
        assert mem.count(MemoryType.EPISODIC) == 1

    def test_count(self, mem):
        assert mem.count() == 0
        mem.store(MemoryType.WORKING, "a", 1)
        assert mem.count() == 1
        assert mem.count(MemoryType.WORKING) == 1
        assert mem.count(MemoryType.EPISODIC) == 0


class TestAgentMemoryShared:
    def test_shared_grants_access(self, mem):
        mem.store(MemoryType.SHARED, "public_info", "accessible", permissions=["agent-2"])
        assert mem.grant_access("public_info", "agent-3") is True
        entry = mem.retrieve(MemoryType.SHARED, "public_info")
        assert entry is not None
        assert "agent-3" in entry.permissions

    def test_shared_grant_missing(self, mem):
        assert mem.grant_access("nope", "agent-2") is False

    def test_read_shared_own(self, mem):
        mem.store(MemoryType.SHARED, "mydata", "secret")
        entry = mem.read_shared("agent-1", "mydata")
        assert entry is not None
        assert entry.content == "secret"

    def test_read_shared_other(self, mem):
        mem.store(MemoryType.SHARED, "shared_data", "from_agent2")
        entry = mem.read_shared("agent-2", "shared_data")
        assert entry is None  # cross-agent not supported in basic impl


class TestAgentMemoryTypes:
    def test_six_memory_types(self):
        assert len(MemoryType) == 6

    def test_all_types_storable(self, mem):
        for mt in MemoryType:
            entry = mem.store(mt, f"key_{mt.value}", mt.value)
            assert entry.memory_type == mt
            retrieved = mem.retrieve(mt, f"key_{mt.value}")
            assert retrieved is not None

    def test_type_isolation(self, mem):
        mem.store(MemoryType.WORKING, "k", "working_val")
        mem.store(MemoryType.EPISODIC, "k", "episodic_val")
        w = mem.retrieve(MemoryType.WORKING, "k")
        e = mem.retrieve(MemoryType.EPISODIC, "k")
        assert w is not None and e is not None
        assert w.content == "working_val"
        assert e.content == "episodic_val"


class TestAgentMemoryTTL:
    def test_ttl_expiration_on_retrieve(self, mem):
        mem.store(MemoryType.WORKING, "quick", "data", ttl_seconds=0.01)
        time.sleep(0.02)
        assert mem.retrieve(MemoryType.WORKING, "quick") is None

    def test_ttl_expiration_on_list(self, mem):
        mem.store(MemoryType.WORKING, "quick", "data", ttl_seconds=0.01)
        time.sleep(0.02)
        assert len(mem.list(MemoryType.WORKING)) == 0

    def test_ttl_expiration_on_count(self, mem):
        mem.store(MemoryType.WORKING, "quick", "data", ttl_seconds=0.01)
        time.sleep(0.02)
        assert mem.count(MemoryType.WORKING) == 0

    def test_no_expiration_when_ttl_zero(self, mem):
        mem.store(MemoryType.WORKING, "persistent", "data", ttl_seconds=0)
        assert mem.retrieve(MemoryType.WORKING, "persistent") is not None


class TestAgentMemoryHealth:
    def test_health(self, mem):
        mem.store(MemoryType.WORKING, "a", 1)
        mem.store(MemoryType.EPISODIC, "b", 2)
        h = mem.health()
        assert h["alive"] is True
        assert h["agent_id"] == "agent-1"
        assert h["total_entries"] == 2
        assert h["memory_types"]["working"] == 1
        assert h["memory_types"]["episodic"] == 1


class TestAgentMemoryThreadSafety:
    def test_concurrent_store(self, mem):
        """Ensure the RLock allows concurrent (simulated) access."""
        import threading
        barrier = threading.Barrier(5)
        results: list[bool] = [False] * 5

        def write(idx: int) -> None:
            barrier.wait()
            mem.store(MemoryType.WORKING, f"t{idx}", idx)
            results[idx] = True

        threads = [threading.Thread(target=write, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert all(results)
        assert mem.count(MemoryType.WORKING) == 5


class TestAgentMemoryAgentID:
    def test_agent_id_property(self):
        mem = AgentMemory("custom-agent")
        assert mem.agent_id == "custom-agent"
