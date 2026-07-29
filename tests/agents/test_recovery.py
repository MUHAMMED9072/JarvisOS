from __future__ import annotations

import json
import tempfile

from app.agents.archival import ArchiveManager
from app.agents.base import Agent, AgentCapability, AgentMetadata, AgentStatus
from app.agents.recovery import AgentRecovery, CompatibilityCheck
from app.agents.registry import AgentRegistry
from app.knowledge_graph.store import GraphStore


class _SampleAgent(Agent):
    def __init__(self) -> None:
        meta = AgentMetadata(
            agent_id="recovery_test_001", name="recovery_test", version="1.0.0",
            agent_type="domain", status=AgentStatus.ACTIVE,
            capabilities=[AgentCapability(name="test", description="test")],
            tags=["test"],
        )
        super().__init__(meta)

    def execute(self, context: dict) -> dict:
        return {"status": "ok"}


def _make_store() -> GraphStore:
    return GraphStore(filename=tempfile.mktemp(suffix=".json"))


class TestAgentRecovery:
    def test_recover_from_state(self) -> None:
        store = _make_store()
        reg = AgentRegistry(store)
        state_dir = tempfile.mktemp()

        state = {
            "agent_id": "recovery_001",
            "name": "recovered_agent",
            "version": "1.0.0",
            "agent_type": "domain",
            "description": "Recovered test",
            "capabilities": [{"name": "greet", "description": "greets"}],
            "dependencies": [],
            "owner": "system",
            "tags": ["test"],
        }
        state_file = __import__("pathlib").Path(state_dir) / "recovered_agent.json"
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text(json.dumps(state), encoding="utf-8")

        recovery = AgentRecovery(reg, state_dir=state_dir)
        result = recovery.recover_from_state("recovered_agent")
        assert result.success
        assert result.agent_name == "recovered_agent"

    def test_recover_from_state_not_found(self) -> None:
        store = _make_store()
        reg = AgentRegistry(store)
        recovery = AgentRecovery(reg, state_dir=tempfile.mktemp())
        result = recovery.recover_from_state("nonexistent")
        assert not result.success

    def test_recover_from_archive(self) -> None:
        store = _make_store()
        reg = AgentRegistry(store)
        archive_dir = tempfile.mktemp()
        archive = ArchiveManager(archive_dir=archive_dir, registry=reg)

        agent = _SampleAgent()
        name = archive.archive_agent(agent)

        recovery = AgentRecovery(reg, archive_manager=archive)
        result = recovery.recover_from_archive(name)
        assert result.success

    def test_recover_from_archive_not_found(self) -> None:
        store = _make_store()
        reg = AgentRegistry(store)
        recovery = AgentRecovery(reg)
        result = recovery.recover_from_archive("nonexistent.tar.gz")
        assert not result.success

    def test_compatibility_check(self) -> None:
        recovery = AgentRecovery(None, system_version="2.0.0")
        compat = recovery._check_compatibility("2.0.0")
        assert compat.compatible

    def test_compatibility_mismatch(self) -> None:
        recovery = AgentRecovery(None, system_version="2.0.0")
        compat = recovery._check_compatibility("1.0.0")
        assert not compat.compatible
        assert len(compat.issues) > 0

    def test_verify_dependencies_empty(self) -> None:
        recovery = AgentRecovery(None)
        assert recovery._verify_dependencies([])

    def test_result_to_dict(self) -> None:
        from app.agents.recovery import RecoveryResult
        r = RecoveryResult(success=True, agent_name="test", version="1.0", state_restored=True)
        d = r.to_dict()
        assert d["success"]
        assert d["agent_name"] == "test"

    def test_compat_to_dict(self) -> None:
        c = CompatibilityCheck(compatible=True, system_version="1.0", agent_version="1.0")
        d = c.to_dict()
        assert d["compatible"]

    def test_health(self) -> None:
        recovery = AgentRecovery(None)
        h = recovery.health()
        assert h["alive"]
