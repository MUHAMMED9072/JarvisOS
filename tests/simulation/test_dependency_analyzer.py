from __future__ import annotations

import pytest

from app.simulation.dependency_analyzer import (
    DependencyAnalyzer,
    DependencyNode,
    ConflictReport,
    ConflictSeverity,
)


class TestDependencyNode:
    def test_defaults(self):
        n = DependencyNode()
        assert n.entity_id == ""
        assert n.depth == 0
        assert n.dependencies == []

    def test_to_dict(self):
        child = DependencyNode(entity_id="c1", entity_type="tool", entity_name="tool1", depth=1)
        parent = DependencyNode(
            entity_id="p1", entity_type="agent", entity_name="agent1", depth=0,
            dependencies=[child],
        )
        d = parent.to_dict()
        assert d["entity_id"] == "p1"
        assert len(d["dependencies"]) == 1
        assert d["dependencies"][0]["entity_id"] == "c1"


class TestConflictReport:
    def test_default_no_conflicts(self):
        r = ConflictReport()
        assert not r.has_conflicts
        assert r.severity == ConflictSeverity.NONE

    def test_cycles_set_conflicts(self):
        r = ConflictReport(cycles=[["a", "b"]])
        assert r.has_conflicts

    def test_to_dict(self):
        r = ConflictReport(
            artifact_id="art1",
            cycles=[["a", "b"]],
            missing_dependencies=["c"],
            severity=ConflictSeverity.CRITICAL,
        )
        d = r.to_dict()
        assert d["artifact_id"] == "art1"
        assert d["has_conflicts"]


class TestDependencyAnalyzer:
    def test_analyze_returns_node(self, graph_store):
        dao = graph_store  # fixture provides the store
        e = dao.create_entity(type="agent", name="test-agent", properties={"version": "1.0"})
        analyzer = DependencyAnalyzer(dao)
        node = analyzer.analyze(e.id)
        assert node.entity_id == e.id
        assert node.entity_name == "test-agent"

    def test_analyze_no_dependencies(self, graph_store):
        e = graph_store.create_entity(type="tool", name="standalone-tool")
        analyzer = DependencyAnalyzer(graph_store)
        node = analyzer.analyze(e.id)
        assert node.dependencies == []

    def test_analyze_with_dependency(self, graph_store):
        parent = graph_store.create_entity(type="agent", name="parent")
        child = graph_store.create_entity(type="tool", name="child")
        graph_store.create_relationship(type="depends_on", source_id=parent.id, target_id=child.id)
        analyzer = DependencyAnalyzer(graph_store)
        node = analyzer.analyze(parent.id)
        assert len(node.dependencies) == 1
        assert node.dependencies[0].entity_id == child.id

    def test_analyze_max_depth(self, graph_store):
        a = graph_store.create_entity(type="agent", name="a")
        b = graph_store.create_entity(type="tool", name="b")
        c = graph_store.create_entity(type="tool", name="c")
        graph_store.create_relationship(type="depends_on", source_id=a.id, target_id=b.id)
        graph_store.create_relationship(type="depends_on", source_id=b.id, target_id=c.id)
        analyzer = DependencyAnalyzer(graph_store)
        node = analyzer.analyze(a.id, max_depth=1)
        # Should only get b at depth 1, not c
        assert len(node.dependencies) == 1
        assert node.dependencies[0].entity_id == b.id
        assert node.dependencies[0].dependencies == []

    def test_analyze_missing_entity(self, graph_store):
        analyzer = DependencyAnalyzer(graph_store)
        node = analyzer.analyze("nonexistent")
        assert node.entity_id == "nonexistent"
        assert node.entity_type == ""

    def test_detect_cycles_no_cycles(self, graph_store):
        a = graph_store.create_entity(type="agent", name="a")
        b = graph_store.create_entity(type="tool", name="b")
        graph_store.create_relationship(type="depends_on", source_id=a.id, target_id=b.id)
        analyzer = DependencyAnalyzer(graph_store)
        cycles = analyzer.detect_cycles(a.id)
        assert cycles == []

    def test_detect_cycles_direct_cycle(self, graph_store):
        a = graph_store.create_entity(type="agent", name="a")
        b = graph_store.create_entity(type="tool", name="b")
        graph_store.create_relationship(type="depends_on", source_id=a.id, target_id=b.id)
        graph_store.create_relationship(type="depends_on", source_id=b.id, target_id=a.id)
        analyzer = DependencyAnalyzer(graph_store)
        cycles = analyzer.detect_cycles(a.id)
        assert len(cycles) >= 1

    def test_detect_cycles_self_loop(self, graph_store):
        a = graph_store.create_entity(type="agent", name="a")
        graph_store.create_relationship(type="depends_on", source_id=a.id, target_id=a.id)
        analyzer = DependencyAnalyzer(graph_store)
        cycles = analyzer.detect_cycles(a.id)
        assert len(cycles) == 1
        assert cycles[0] == [a.id]

    def test_find_missing_dependencies(self, graph_store):
        a = graph_store.create_entity(type="agent", name="a")
        # Directly inject a relationship to a non-existent entity (bypass validation)
        from app.knowledge_graph.relationship import Relationship
        rel = Relationship.create(type="depends_on", source_id=a.id, target_id="missing-id")
        graph_store._relationship_index.add(rel.id, rel.type, rel.source_id, rel.target_id, rel.to_dict())
        analyzer = DependencyAnalyzer(graph_store)
        missing = analyzer.find_missing_dependencies(a.id)
        assert "missing-id" in missing

    def test_find_missing_no_missing(self, graph_store):
        a = graph_store.create_entity(type="agent", name="a")
        b = graph_store.create_entity(type="tool", name="b")
        graph_store.create_relationship(type="depends_on", source_id=a.id, target_id=b.id)
        analyzer = DependencyAnalyzer(graph_store)
        missing = analyzer.find_missing_dependencies(a.id)
        assert missing == []

    def test_generate_report_no_conflicts(self, graph_store):
        a = graph_store.create_entity(type="agent", name="a")
        analyzer = DependencyAnalyzer(graph_store)
        report = analyzer.generate_report(a.id)
        assert not report.has_conflicts
        assert report.severity == ConflictSeverity.NONE

    def test_generate_report_with_cycle(self, graph_store):
        a = graph_store.create_entity(type="agent", name="a")
        b = graph_store.create_entity(type="tool", name="b")
        graph_store.create_relationship(type="depends_on", source_id=a.id, target_id=b.id)
        graph_store.create_relationship(type="depends_on", source_id=b.id, target_id=a.id)
        analyzer = DependencyAnalyzer(graph_store)
        report = analyzer.generate_report(a.id)
        assert report.has_conflicts
        assert report.severity == ConflictSeverity.CRITICAL
        assert len(report.cycles) >= 1

    def test_generate_report_with_missing(self, graph_store):
        a = graph_store.create_entity(type="agent", name="a")
        from app.knowledge_graph.relationship import Relationship
        rel = Relationship.create(type="depends_on", source_id=a.id, target_id="missing-id")
        graph_store._relationship_index.add(rel.id, rel.type, rel.source_id, rel.target_id, rel.to_dict())
        analyzer = DependencyAnalyzer(graph_store)
        report = analyzer.generate_report(a.id)
        assert report.has_conflicts
        assert report.severity == ConflictSeverity.HIGH
        assert "missing-id" in report.missing_dependencies

    def test_health(self, graph_store):
        analyzer = DependencyAnalyzer(graph_store)
        h = analyzer.health()
        assert h["alive"]

    def test_thread_safe(self, graph_store):
        import threading
        analyzer = DependencyAnalyzer(graph_store)
        a = graph_store.create_entity(type="agent", name="a")
        b = graph_store.create_entity(type="tool", name="b")
        graph_store.create_relationship(type="depends_on", source_id=a.id, target_id=b.id)
        errors = []

        def analyze():
            try:
                for _ in range(20):
                    analyzer.analyze(a.id)
                    analyzer.detect_cycles(a.id)
                    analyzer.generate_report(a.id)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=analyze) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
