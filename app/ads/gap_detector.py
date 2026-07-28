from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.ads.capability_analysis import CapabilityAnalysisResult
from app.ads.requirements import RequirementsDocument
from app.knowledge_graph.store import GraphStore


@dataclass
class GapReport:
    """Report of gaps between required and existing capabilities."""

    missing_capabilities: list[str] = field(default_factory=list)
    partial_matches: list[dict[str, Any]] = field(default_factory=list)
    combination_opportunities: list[dict[str, Any]] = field(default_factory=list)
    fully_covered: list[str] = field(default_factory=list)

    def has_gaps(self) -> bool:
        return len(self.missing_capabilities) > 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "missing_capabilities": list(self.missing_capabilities),
            "partial_matches": list(self.partial_matches),
            "combination_opportunities": list(self.combination_opportunities),
            "fully_covered": list(self.fully_covered),
            "has_gaps": self.has_gaps(),
        }


class GapDetector:
    """Compare required capabilities against existing capabilities
    and identify gaps.  Also suggests combination strategies."""

    def __init__(self, graph_store: GraphStore | None = None) -> None:
        self._graph_store = graph_store

    def detect(
        self,
        requirements: RequirementsDocument,
        capability_result: CapabilityAnalysisResult,
    ) -> GapReport:
        missing = list(capability_result.missing_capabilities)
        partial = list(capability_result.partially_matched)
        fully = list(capability_result.fully_matched)

        # Suggest combination opportunities for missing capabilities
        combos = self._find_combinations(missing)

        return GapReport(
            missing_capabilities=missing,
            partial_matches=partial,
            combination_opportunities=combos,
            fully_covered=fully,
        )

    def _find_combinations(self, missing: list[str]) -> list[dict[str, Any]]:
        """Suggest how to combine existing capabilities to cover gaps."""
        combos: list[dict[str, Any]] = []
        if not self._graph_store:
            return combos

        existing = self._graph_store.get_entities_by_type("capability")
        existing_names = [e.name for e in existing]

        for cap in missing:
            parts = cap.split("_")
            candidates = [e for e in existing_names if any(p in e for p in parts if len(p) > 3)]
            if len(candidates) >= 2:
                combos.append({
                    "target_capability": cap,
                    "suggestion": f"Combine: {', '.join(candidates)}",
                    "candidates": candidates,
                })

        return combos

    def health(self) -> dict[str, Any]:
        return {"alive": True, "has_graph_store": self._graph_store is not None}
