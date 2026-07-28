from __future__ import annotations

import pytest

from app.intelligence.justification import (
    JustificationGenerator,
    Justification,
    Evidence,
    CounterArgument,
)


class TestEvidence:
    def test_defaults(self):
        e = Evidence()
        assert e.relevance == 0.5

    def test_to_dict(self):
        e = Evidence(source="kg", description="test", relevance=0.8)
        d = e.to_dict()
        assert d["source"] == "kg"
        assert d["relevance"] == 0.8


class TestCounterArgument:
    def test_defaults(self):
        c = CounterArgument()
        assert c.severity == "medium"

    def test_to_dict(self):
        c = CounterArgument(issue="risk", severity="high", mitigation="review")
        d = c.to_dict()
        assert d["issue"] == "risk"
        assert d["severity"] == "high"


class TestJustification:
    def test_defaults(self):
        j = Justification()
        assert j.confidence == 0.5

    def test_to_dict(self):
        j = Justification(
            decision="use_agent_a",
            reasoning="fastest option",
            confidence=0.85,
            evidence=[Evidence(source="kg", description="data")],
            counter_arguments=[CounterArgument(issue="risk")],
            alternatives_considered=["agent_b", "agent_c"],
        )
        d = j.to_dict()
        assert d["decision"] == "use_agent_a"
        assert d["confidence"] == 0.85
        assert len(d["evidence"]) == 1
        assert len(d["counter_arguments"]) == 1


class TestJustificationGenerator:
    def test_generate_basic(self):
        jg = JustificationGenerator()
        j = jg.generate(decision="use_approach_a", reasoning="it is faster")
        assert j.decision == "use_approach_a"
        assert 0.0 <= j.confidence <= 1.0

    def test_generate_with_alternatives(self):
        jg = JustificationGenerator()
        j = jg.generate("pick_a", "best option", alternatives=["b", "c"])
        assert "b" in j.alternatives_considered

    def test_generate_with_sources(self):
        jg = JustificationGenerator()
        j = jg.generate("pick_a", "best", evidence_sources=["src1", "src2"])
        assert len(j.evidence) == 2

    def test_generate_with_graph(self, graph_store):
        graph_store.create_entity(type="tool", name="fast-tool")
        jg = JustificationGenerator(graph_store=graph_store)
        j = jg.generate(decision="fast-tool", reasoning="it is fast")
        assert len(j.evidence) >= 1

    def test_confidence_no_evidence(self):
        jg = JustificationGenerator()
        j = jg.generate("x", "reason")
        assert j.confidence == 0.3

    def test_counter_arguments_fast_decision(self):
        jg = JustificationGenerator()
        j = jg.generate("pick the quick solution", "fast approach")
        issues = [c.issue for c in j.counter_arguments]
        assert any("quality" in i.lower() for i in issues)

    def test_counter_arguments_complex_reasoning(self):
        jg = JustificationGenerator()
        j = jg.generate("x", "complex solution with many components")
        issues = [c.issue for c in j.counter_arguments]
        assert any("Complex" in i for i in issues)

    def test_health(self):
        jg = JustificationGenerator()
        h = jg.health()
        assert h["alive"]
        assert not h["graph_available"]

    def test_health_with_graph(self, graph_store):
        jg = JustificationGenerator(graph_store=graph_store)
        h = jg.health()
        assert h["graph_available"]
