from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any

from app.knowledge_graph.store import GraphStore


@dataclass
class Evidence:
    source: str = ""
    description: str = ""
    relevance: float = 0.5

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "description": self.description,
            "relevance": self.relevance,
        }


@dataclass
class CounterArgument:
    issue: str = ""
    severity: str = "medium"
    mitigation: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "issue": self.issue,
            "severity": self.severity,
            "mitigation": self.mitigation,
        }


@dataclass
class Justification:
    decision: str = ""
    reasoning: str = ""
    confidence: float = 0.5
    evidence: list[Evidence] = field(default_factory=list)
    counter_arguments: list[CounterArgument] = field(default_factory=list)
    alternatives_considered: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "reasoning": self.reasoning,
            "confidence": self.confidence,
            "evidence": [e.to_dict() for e in self.evidence],
            "counter_arguments": [c.to_dict() for c in self.counter_arguments],
            "alternatives_considered": list(self.alternatives_considered),
            "created_at": self.created_at,
        }


class JustificationGenerator:
    """Generates human-readable justifications with evidence from the
    Knowledge Graph, confidence scoring, and counter-argument identification.

    Thread-safe.
    """

    def __init__(self, graph_store: GraphStore | None = None) -> None:
        self._graph = graph_store
        self._lock = threading.RLock()

    def generate(
        self,
        decision: str,
        reasoning: str,
        alternatives: list[str] | None = None,
        evidence_sources: list[str] | None = None,
    ) -> Justification:
        """Generate a complete justification with evidence and counter-arguments."""
        with self._lock:
            evidence = self._gather_evidence(decision, evidence_sources)
            confidence = self._compute_confidence(evidence)
            counter_args = self._generate_counter_arguments(decision, reasoning, evidence)

            return Justification(
                decision=decision,
                reasoning=reasoning,
                confidence=confidence,
                evidence=evidence,
                counter_arguments=counter_args,
                alternatives_considered=list(alternatives or []),
            )

    def _gather_evidence(
        self,
        decision: str,
        sources: list[str] | None,
    ) -> list[Evidence]:
        evidence: list[Evidence] = []
        seen: set[str] = set()
        if sources:
            for src in sources:
                if src not in seen:
                    seen.add(src)
                    evidence.append(Evidence(
                        source=src,
                        description=f"Referenced source: {src}",
                        relevance=0.7,
                    ))

        if self._graph is not None:
            entities = self._graph.search(decision)
            for entity in entities:
                if entity.id not in seen:
                    seen.add(entity.id)
                    evidence.append(Evidence(
                        source=entity.name or entity.id,
                        description=f"Entity '{entity.name}' of type '{entity.type}'",
                        relevance=0.5,
                    ))

        return evidence

    def _compute_confidence(self, evidence: list[Evidence]) -> float:
        if not evidence:
            return 0.3
        avg_relevance = sum(e.relevance for e in evidence) / len(evidence)
        count_factor = min(1.0, len(evidence) / 5.0)
        return min(1.0, avg_relevance * 0.6 + count_factor * 0.4)

    def _generate_counter_arguments(
        self,
        decision: str,
        reasoning: str,
        evidence: list[Evidence] | None = None,
    ) -> list[CounterArgument]:
        counter_args: list[CounterArgument] = []

        decision_lower = decision.lower()
        if "fast" in decision_lower or "quick" in decision_lower:
            counter_args.append(CounterArgument(
                issue="Speed-focused approaches may sacrifice quality or accuracy",
                severity="medium",
                mitigation="Consider quality benchmarks alongside performance targets",
            ))

        if "complex" in reasoning.lower():
            counter_args.append(CounterArgument(
                issue="Complex approaches may be harder to maintain and debug",
                severity="medium",
                mitigation="Document the complexity and consider breaking into simpler steps",
            ))

        if evidence is None or len(evidence) < 2:
            counter_args.append(CounterArgument(
                issue="Limited evidence from Knowledge Graph to support this decision",
                severity="low",
                mitigation="Seek additional data or consult domain experts",
            ))

        return counter_args

    def health(self) -> dict[str, Any]:
        return {"alive": True, "graph_available": self._graph is not None}
