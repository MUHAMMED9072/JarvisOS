from __future__ import annotations

import json
import tempfile

from app.agents.archival import ArchiveManager, ArchiveEntry
from app.agents.base import Agent, AgentCapability, AgentMetadata, AgentStatus
from app.agents.registry import AgentRegistry
from app.agents.retirement import AgentRetirement, RetirementResult
from app.knowledge_graph.store import GraphStore


class _RetireTestAgent(Agent):
    def __init__(self) -> None:
        meta = AgentMetadata(
            agent_id="retire_test_001", name="retire_test", version="1.0.0",
            agent_type="domain", status=AgentStatus.ACTIVE,
            capabilities=[AgentCapability(name="test", description="test")],
            tags=["test"],
        )
        super().__init__(meta)
        self._stopped = False

    def execute(self, context: dict) -> dict:
        return {"status": "ok"}

    def on_stop(self) -> None:
        self._stopped = True


def _make_store() -> GraphStore:
    return GraphStore(filename=tempfile.mktemp(suffix=".json"))


class TestAgentRetirement:
    def test_retire_agent(self) -> None:
        store = _make_store()
        reg = AgentRegistry(store)
        agent = _RetireTestAgent()
        reg.register(agent)

        retirement = AgentRetirement(reg, state_dir=tempfile.mktemp())
        result = retirement.retire_agent(agent)
        assert result.success
        assert result.agent_name == "retire_test"

    def test_retired_agent_state_saved(self) -> None:
        store = _make_store()
        reg = AgentRegistry(store)
        agent = _RetireTestAgent()
        reg.register(agent)

        state_dir = tempfile.mktemp()
        retirement = AgentRetirement(reg, state_dir=state_dir)
        result = retirement.retire_agent(agent)
        assert result.state_preserved

    def test_list_retired(self) -> None:
        store = _make_store()
        reg = AgentRegistry(store)
        agent = _RetireTestAgent()
        reg.register(agent)

        state_dir = tempfile.mktemp()
        retirement = AgentRetirement(reg, state_dir=state_dir)
        retirement.retire_agent(agent)

        retired = retirement.list_retired()
        assert len(retired) >= 1

    def test_on_stop_called(self) -> None:
        store = _make_store()
        reg = AgentRegistry(store)
        agent = _RetireTestAgent()
        reg.register(agent)

        retirement = AgentRetirement(reg, state_dir=tempfile.mktemp())
        retirement.retire_agent(agent)
        assert agent._stopped

    def test_health(self) -> None:
        store = _make_store()
        reg = AgentRegistry(store)
        retirement = AgentRetirement(reg, state_dir=tempfile.mktemp())
        h = retirement.health()
        assert h["alive"]


class TestArchiveManager:
    def test_archive_agent(self) -> None:
        store = _make_store()
        reg = AgentRegistry(store)
        agent = _RetireTestAgent()
        reg.register(agent)

        archive = ArchiveManager(archive_dir=tempfile.mktemp(), registry=reg)
        name = archive.archive_agent(agent)
        assert name.endswith(".tar.gz")

    def test_list_archives(self) -> None:
        archive = ArchiveManager(archive_dir=tempfile.mktemp())
        agent = _RetireTestAgent()
        name = archive.archive_agent(agent)
        entries = archive.list_archives()
        assert len(entries) >= 1
        assert entries[0].name == "retire_test"

    def test_search_archives(self) -> None:
        archive = ArchiveManager(archive_dir=tempfile.mktemp())
        agent = _RetireTestAgent()
        archive.archive_agent(agent)
        results = archive.search_archives(query="retire_test")
        assert len(results) >= 1

    def test_search_by_type(self) -> None:
        archive = ArchiveManager(archive_dir=tempfile.mktemp())
        agent = _RetireTestAgent()
        archive.archive_agent(agent)
        entries = archive.list_archives(agent_type="domain")
        assert len(entries) >= 1

    def test_delete_archive(self) -> None:
        archive = ArchiveManager(archive_dir=tempfile.mktemp())
        agent = _RetireTestAgent()
        name = archive.archive_agent(agent)
        assert archive.delete_archive(name)
        assert len(archive.list_archives()) == 0

    def test_apply_retention_policy(self) -> None:
        archive = ArchiveManager(archive_dir=tempfile.mktemp(), default_retention_days=0)
        agent = _RetireTestAgent()
        archive.archive_agent(agent)
        count = archive.apply_retention_policy()
        assert count >= 0

    def test_get_archive_path(self) -> None:
        archive = ArchiveManager(archive_dir=tempfile.mktemp())
        agent = _RetireTestAgent()
        name = archive.archive_agent(agent)
        p = archive.get_archive_path(name)
        assert p is not None
        assert p.exists()

    def test_health(self) -> None:
        archive = ArchiveManager(archive_dir=tempfile.mktemp())
        h = archive.health()
        assert h["alive"]

    def test_entry_to_dict(self) -> None:
        e = ArchiveEntry(agent_id="id1", name="test", version="1.0", agent_type="system")
        d = e.to_dict()
        assert d["name"] == "test"
