from __future__ import annotations

import tempfile

from app.agents.base import Agent, AgentCapability, AgentMetadata, AgentStatus
from app.agents.merging import AgentMerging, CapabilityConflict, MergeAnalysis, MergeResult
from app.agents.registry import AgentRegistry
from app.knowledge_graph.store import GraphStore


class _AgentA(Agent):
    def __init__(self) -> None:
        meta = AgentMetadata(
            agent_id="agent_a_001", name="agent_a", version="1.0.0",
            agent_type="domain", status=AgentStatus.ACTIVE,
            capabilities=[
                AgentCapability(name="speak", description="Can speak"),
                AgentCapability(name="listen", description="Can listen"),
            ],
            tags=["voice"],
        )
        super().__init__(meta)

    def execute(self, context: dict) -> dict:
        return {"from": "agent_a"}


class _AgentB(Agent):
    def __init__(self) -> None:
        meta = AgentMetadata(
            agent_id="agent_b_001", name="agent_b", version="1.0.0",
            agent_type="domain", status=AgentStatus.ACTIVE,
            capabilities=[
                AgentCapability(name="listen", description="Can listen"),
                AgentCapability(name="write", description="Can write"),
            ],
            tags=["text"],
        )
        super().__init__(meta)

    def execute(self, context: dict) -> dict:
        return {"from": "agent_b"}


class _AgentConflicting(Agent):
    def __init__(self) -> None:
        meta = AgentMetadata(
            agent_id="agent_c_001", name="agent_c", version="1.0.0",
            agent_type="domain", status=AgentStatus.ACTIVE,
            capabilities=[
                AgentCapability(name="speak", description="Different description"),
            ],
        )
        super().__init__(meta)

    def execute(self, context: dict) -> dict:
        return {"from": "agent_c"}


def _make_store() -> GraphStore:
    return GraphStore(filename=tempfile.mktemp(suffix=".json"))


class TestAgentMerging:
    def test_analyze_no_conflicts(self) -> None:
        a = _AgentA()
        b = _AgentB()
        merger = AgentMerging(None)
        analysis = merger.analyze(a, b)
        assert analysis.mergeable
        assert "speak" in analysis.capabilities_a
        assert "write" in analysis.capabilities_b
        assert "listen" in analysis.common_capabilities

    def test_analyze_detects_conflict(self) -> None:
        a = _AgentA()
        c = _AgentConflicting()
        merger = AgentMerging(None)
        analysis = merger.analyze(a, c)
        assert len(analysis.conflicts) > 0

    def test_merge_agents(self) -> None:
        store = _make_store()
        reg = AgentRegistry(store)
        a = _AgentA()
        b = _AgentB()
        reg.register(a)
        reg.register(b)

        merger = AgentMerging(reg, graph_store=store)
        result = merger.merge(a, b, merged_name="merged_ab")
        assert result.success
        assert result.merged_agent_name == "merged_ab"

    def test_merge_creates_union_capabilities(self) -> None:
        store = _make_store()
        reg = AgentRegistry(store)
        a = _AgentA()
        b = _AgentB()
        reg.register(a)
        reg.register(b)

        merger = AgentMerging(reg, graph_store=store)
        result = merger.merge(a, b)
        assert result.success
        assert result.analysis is not None
        assert len(result.analysis.union_capabilities) == 3

    def test_merge_generates_default_name(self) -> None:
        store = _make_store()
        reg = AgentRegistry(store)
        a = _AgentA()
        b = _AgentB()
        reg.register(a)
        reg.register(b)

        merger = AgentMerging(reg)
        result = merger.merge(a, b)
        assert result.success
        assert "_merged" in result.merged_agent_name

    def test_rollback_merge(self) -> None:
        store = _make_store()
        reg = AgentRegistry(store)
        a = _AgentA()
        b = _AgentB()
        reg.register(a)
        reg.register(b)

        merger = AgentMerging(reg, graph_store=store)
        result = merger.merge(a, b)
        assert result.success

        rolled_back = merger.rollback(result.merged_agent_id)
        assert rolled_back

    def test_rollback_nonexistent(self) -> None:
        merger = AgentMerging(None)
        assert not merger.rollback("nonexistent")

    def test_merge_history(self) -> None:
        store = _make_store()
        reg = AgentRegistry(store)
        a = _AgentA()
        b = _AgentB()
        reg.register(a)
        reg.register(b)

        merger = AgentMerging(reg)
        result = merger.merge(a, b)
        history = merger.get_merge_history(result.merged_agent_id)
        assert len(history) == 1

    def test_analysis_to_dict(self) -> None:
        analysis = MergeAnalysis(
            agent_a_name="a", agent_b_name="b",
            capabilities_a=["x"], capabilities_b=["y"],
            common_capabilities=[], union_capabilities=["x", "y"],
        )
        d = analysis.to_dict()
        assert d["agent_a"] == "a"

    def test_conflict_to_dict(self) -> None:
        c = CapabilityConflict(capability_name="speak", source_a_value="v1", source_b_value="v2")
        d = c.to_dict()
        assert d["capability_name"] == "speak"

    def test_result_to_dict(self) -> None:
        r = MergeResult(success=True, merged_agent_id="mid", merged_agent_name="merged")
        d = r.to_dict()
        assert d["success"]

    def test_health(self) -> None:
        merger = AgentMerging(None)
        h = merger.health()
        assert h["alive"]
