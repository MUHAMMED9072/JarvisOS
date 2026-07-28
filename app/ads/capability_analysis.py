from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.ads.requirements import RequirementsDocument
from app.knowledge_graph.store import GraphStore


@dataclass
class CapabilityAnalysisResult:
    """Result of capability analysis for a requirements document."""

    required_capabilities: list[str] = field(default_factory=list)
    existing_capabilities: list[str] = field(default_factory=list)
    missing_capabilities: list[str] = field(default_factory=list)
    partially_matched: list[dict[str, Any]] = field(default_factory=list)
    fully_matched: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "required_capabilities": list(self.required_capabilities),
            "existing_capabilities": list(self.existing_capabilities),
            "missing_capabilities": list(self.missing_capabilities),
            "partially_matched": list(self.partially_matched),
            "fully_matched": list(self.fully_matched),
        }


class CapabilityAnalyzer:
    """Determine what capabilities are needed for the requirements
    and query the Knowledge Graph for existing capabilities."""

    def __init__(self, graph_store: GraphStore | None = None) -> None:
        self._graph_store = graph_store

    def analyze(self, requirements: RequirementsDocument) -> CapabilityAnalysisResult:
        required = set(requirements.capabilities_needed)
        existing: list[str] = []
        partially_matched: list[dict[str, Any]] = []
        fully_matched: list[str] = []

        if self._graph_store:
            # Query KG for existing capabilities matching required
            for cap in required:
                matches = self._query_capability(cap)
                if matches:
                    existing.append(cap)
                    fully_matched.append(cap)
                else:
                    # Check for partial matches
                    partial = self._query_partial(cap)
                    if partial:
                        partially_matched.append({"capability": cap, "partial_matches": partial})
                    else:
                        pass  # truly missing
        else:
            existing = list(required)

        missing = [c for c in required if c not in existing]

        return CapabilityAnalysisResult(
            required_capabilities=list(required),
            existing_capabilities=existing,
            missing_capabilities=missing,
            partially_matched=partially_matched,
            fully_matched=fully_matched,
        )

    def _query_capability(self, cap: str) -> list[dict[str, Any]]:
        if not self._graph_store:
            return []
        entities = self._graph_store.get_entities_by_type("capability")
        return [
            e.properties for e in entities
            if cap in e.name.lower() or cap in str(e.properties).lower()
        ]

    def _query_partial(self, cap: str) -> list[str]:
        if not self._graph_store:
            return []
        entities = self._graph_store.get_entities_by_type("capability")
        words = cap.split("_")
        partials: list[str] = []
        for e in entities:
            for w in words:
                if len(w) > 3 and w in e.name.lower() and e.name not in partials:
                    partials.append(e.name)
        return partials

    def health(self) -> dict[str, Any]:
        return {"alive": True, "has_graph_store": self._graph_store is not None}
