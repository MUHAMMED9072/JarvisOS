from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any

from app.knowledge_graph.store import GraphStore


@dataclass
class ProviderInfo:
    entity_id: str = ""
    entity_name: str = ""
    entity_type: str = ""
    quality_score: float = 0.5
    relevance: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "entity_name": self.entity_name,
            "entity_type": self.entity_type,
            "quality_score": self.quality_score,
            "relevance": self.relevance,
        }


@dataclass
class GapAnalysis:
    required_capabilities: list[str] = field(default_factory=list)
    available: dict[str, list[ProviderInfo]] = field(default_factory=dict)
    partially_matched: dict[str, list[ProviderInfo]] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "required_capabilities": list(self.required_capabilities),
            "available": {
                cap: [p.to_dict() for p in providers]
                for cap, providers in self.available.items()
            },
            "partially_matched": {
                cap: [p.to_dict() for p in providers]
                for cap, providers in self.partially_matched.items()
            },
            "missing": list(self.missing),
        }


class CapabilityRegistry:
    """Queries the Knowledge Graph for capability information.

    Supports find_providers, find_gaps, capability search,
    quality score tracking, and duplicate detection.
    """

    def __init__(self, graph_store: GraphStore) -> None:
        self._store = graph_store
        self._lock = threading.RLock()
        self._quality_scores: dict[str, float] = {}

    def find_providers(
        self,
        capability_name: str,
        min_quality: float = 0.0,
    ) -> list[ProviderInfo]:
        """Return all entities that provide the given capability,
        sorted by quality score descending."""
        cap_entities = self._store.get_entity_by_name(capability_name)
        if not cap_entities:
            return []
        cap = cap_entities[0]
        providers: list[ProviderInfo] = []
        seen: set[str] = set()

        for rel in self._store.get_incoming_relationships(cap.id):
            if rel["type"] in ("uses", "has_capability"):
                entity = self._store.get_entity(rel["source_id"])
                if entity and entity.id not in seen:
                    seen.add(entity.id)
                    quality = self._quality_scores.get(entity.id, 0.5)
                    if quality >= min_quality:
                        providers.append(ProviderInfo(
                            entity_id=entity.id,
                            entity_name=entity.name,
                            entity_type=entity.type,
                            quality_score=quality,
                        ))

        providers.sort(key=lambda p: p.quality_score, reverse=True)
        return providers

    def find_gaps(self, required_capabilities: list[str]) -> GapAnalysis:
        """Analyze which required capabilities are available, partially
        matched, or missing entirely."""
        analysis = GapAnalysis(required_capabilities=list(required_capabilities))

        for cap_name in required_capabilities:
            providers = self.find_providers(cap_name)
            if providers:
                analysis.available[cap_name] = providers
            else:
                # Check for partial matches via search
                partials: list[ProviderInfo] = []
                for entity in self._store.search(cap_name):
                    if entity.type in ("agent", "tool", "skill"):
                        quality = self._quality_scores.get(entity.id, 0.5)
                        partials.append(ProviderInfo(
                            entity_id=entity.id,
                            entity_name=entity.name,
                            entity_type=entity.type,
                            quality_score=quality,
                            relevance=0.3,
                        ))
                if partials:
                    analysis.partially_matched[cap_name] = partials
                else:
                    analysis.missing.append(cap_name)

        return analysis

    def search_capabilities(self, query: str) -> list[dict[str, Any]]:
        """Natural-language-style search over capability names and
        descriptions in the KG."""
        results: list[dict[str, Any]] = []
        for entity in self._store.search(query):
            if entity.type == "capability":
                providers = self.find_providers(entity.name)
                results.append({
                    "capability_id": entity.id,
                    "capability_name": entity.name,
                    "provider_count": len(providers),
                    "top_providers": [p.to_dict() for p in providers[:3]],
                })
        return results

    def update_quality_score(self, entity_id: str, score: float) -> None:
        """Update the quality score for a provider entity."""
        with self._lock:
            self._quality_scores[entity_id] = max(0.0, min(1.0, score))

    def get_quality_score(self, entity_id: str) -> float:
        with self._lock:
            return self._quality_scores.get(entity_id, 0.5)

    def detect_duplicate(self, capability_name: str) -> list[dict[str, Any]]:
        """Detect potential duplicate capability registrations."""
        cap_entities = self._store.get_entity_by_name(capability_name)
        if len(cap_entities) <= 1:
            return []
        duplicates: list[dict[str, Any]] = []
        for entity in cap_entities:
            duplicates.append({
                "capability_id": entity.id,
                "capability_name": entity.name,
            })
        return duplicates

    def register_capability(self, name: str) -> str:
        """Register a new capability if it doesn't already exist."""
        existing = self._store.get_entity_by_name(name)
        if existing:
            return existing[0].id
        entity = self._store.create_entity(type="capability", name=name)
        return entity.id

    def health(self) -> dict[str, Any]:
        return {
            "alive": True,
            "capability_count": len(self._store.get_entities_by_type("capability")),
            "quality_scores_tracked": len(self._quality_scores),
        }
