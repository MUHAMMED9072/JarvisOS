from __future__ import annotations

import pytest

from app.knowledge_graph.capability_registry import CapabilityRegistry, ProviderInfo, GapAnalysis
from app.knowledge_graph.store import GraphStore


@pytest.fixture
def registry():
    g = GraphStore()
    g.clear()
    return CapabilityRegistry(g)


@pytest.fixture
def populated(registry):
    g = registry._store
    # Create capability entities
    g.create_entity(type="capability", name="python", id="c_py")
    g.create_entity(type="capability", name="docker", id="c_docker")
    g.create_entity(type="capability", name="networking", id="c_net")
    g.create_entity(type="capability", name="ml", id="c_ml")
    # Create providers
    a1 = g.create_entity(type="agent", name="Agent1", id="a1")
    a2 = g.create_entity(type="agent", name="Agent2", id="a2")
    t1 = g.create_entity(type="tool", name="Tool1", id="t1")
    # Link providers to capabilities
    g.create_relationship(type="uses", source_id="a1", target_id="c_py")
    g.create_relationship(type="uses", source_id="a1", target_id="c_docker")
    g.create_relationship(type="uses", source_id="a2", target_id="c_py")
    g.create_relationship(type="uses", source_id="t1", target_id="c_docker")
    g.create_relationship(type="uses", source_id="t1", target_id="c_net")
    registry.update_quality_score("a1", 0.9)
    registry.update_quality_score("a2", 0.7)
    registry.update_quality_score("t1", 0.8)
    return registry


class TestCapabilityRegistry:
    def test_find_providers(self, populated):
        providers = populated.find_providers("python")
        assert len(providers) == 2
        # Sorted by quality score
        assert providers[0].entity_name == "Agent1"

    def test_find_providers_with_min_quality(self, populated):
        providers = populated.find_providers("python", min_quality=0.8)
        assert len(providers) == 1
        assert providers[0].entity_name == "Agent1"

    def test_find_providers_nonexistent(self, registry):
        assert registry.find_providers("nonexistent") == []

    def test_find_gaps_all_available(self, populated):
        gap = populated.find_gaps(["python", "docker"])
        assert "python" in gap.available
        assert "docker" in gap.available
        assert gap.missing == []

    def test_find_gaps_partially_matched(self, populated):
        gap = populated.find_gaps(["python", "k8s"])
        assert "python" in gap.available
        assert gap.missing == ["k8s"]

    def test_find_gaps_empty(self, registry):
        gap = registry.find_gaps([])
        assert gap.available == {}
        assert gap.missing == []

    def test_search_capabilities(self, populated):
        results = populated.search_capabilities("python")
        assert len(results) >= 1
        assert results[0]["capability_name"] == "python"
        assert results[0]["provider_count"] >= 1

    def test_search_capabilities_no_match(self, registry):
        assert registry.search_capabilities("zzznotfound") == []

    def test_update_quality_score(self, registry):
        registry.update_quality_score("e1", 0.85)
        assert registry.get_quality_score("e1") == 0.85

    def test_quality_score_clamped(self, registry):
        registry.update_quality_score("e1", 1.5)
        assert registry.get_quality_score("e1") == 1.0
        registry.update_quality_score("e2", -0.5)
        assert registry.get_quality_score("e2") == 0.0

    def test_default_quality_score(self, registry):
        assert registry.get_quality_score("unknown") == 0.5

    def test_detect_duplicate(self, registry):
        # Create duplicate capabilities directly (bypass dedup)
        g = registry._store
        g.create_entity(type="capability", name="dup_cap", id="dup1")
        g.create_entity(type="capability", name="dup_cap", id="dup2")
        dups = registry.detect_duplicate("dup_cap")
        assert len(dups) >= 1

    def test_no_duplicate(self, registry):
        registry.register_capability("unique")
        assert registry.detect_duplicate("unique") == []

    def test_register_capability(self, registry):
        cid = registry.register_capability("new_cap")
        assert cid is not None
        # Second call returns existing
        cid2 = registry.register_capability("new_cap")
        assert cid2 == cid

    def test_health(self, registry):
        h = registry.health()
        assert h["alive"] is True

    def test_provider_info_to_dict(self):
        p = ProviderInfo(entity_id="e1", entity_name="test", entity_type="agent", quality_score=0.8, relevance=0.5)
        d = p.to_dict()
        assert d["entity_id"] == "e1"
        assert d["quality_score"] == 0.8

    def test_gap_analysis_to_dict(self):
        g = GapAnalysis(
            required_capabilities=["a"],
            available={"a": [ProviderInfo(entity_id="e1", entity_name="p1", entity_type="agent")]},
            missing=["b"],
        )
        d = g.to_dict()
        assert "a" in d["available"]
        assert d["missing"] == ["b"]
