from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from app.learning.knowledge_distillation import (
    DistilledKnowledge,
    KnowledgeDistiller,
    KnowledgeValidationResult,
)
from app.learning.pattern_recognition import ExecutionRecord


class TestDistilledKnowledge:
    def test_to_dict(self):
        k = DistilledKnowledge(
            knowledge_id="k1", title="Best practice",
            summary="Optimal approach for X", domain="code",
            source_count=10, confidence=0.85, quality_score=0.88,
            use_count=5, tags=["python"], created_at=100.0, updated_at=200.0,
        )
        d = k.to_dict()
        assert d["knowledge_id"] == "k1"
        assert d["domain"] == "code"
        assert d["confidence"] == 0.85

    def test_to_dict_defaults(self):
        k = DistilledKnowledge()
        d = k.to_dict()
        assert d["knowledge_id"] == ""


class TestKnowledgeValidationResult:
    def test_to_dict(self):
        r = KnowledgeValidationResult(
            valid=True, knowledge_id="k1", consistency_score=0.9,
            contradiction_count=0, evidence_count=10,
            issues=[],
        )
        d = r.to_dict()
        assert d["valid"] is True
        assert d["consistency_score"] == 0.9

    def test_to_dict_defaults(self):
        r = KnowledgeValidationResult()
        d = r.to_dict()
        assert d["valid"] is False


class TestKnowledgeDistiller:
    @pytest.fixture
    def distiller(self):
        return KnowledgeDistiller()

    def make_record(self, agent_id="a1", task_type="code", success=True,
                    latency=1.0, tags=None, error=""):
        return ExecutionRecord(
            agent_id=agent_id, task_type=task_type, success=success,
            latency=latency, task_tags=tags or [],
            error_message=error, timestamp=time.time(),
        )

    def test_initial_state(self, distiller):
        stats = distiller.get_statistics()
        assert stats["total_knowledge_pieces"] == 0

    def test_distill_insufficient_records(self, distiller):
        records = [self.make_record()]
        result = distiller.distill_from_records(records)
        assert result == []

    def test_distill_high_success(self, distiller):
        import time
        records = [self.make_record(task_type="code") for _ in range(5)]
        result = distiller.distill_from_records(records)
        assert len(result) >= 1
        assert "Optimal" in result[0].title
        assert result[0].domain == "code"

    def test_distill_high_failure(self, distiller):
        records = (
            [self.make_record(task_type="bug", success=True) for _ in range(3)]
            + [self.make_record(task_type="bug", success=False) for _ in range(5)]
        )
        result = distiller.distill_from_records(records)
        pitfalls = [k for k in result if "pitfall" in k.title.lower()]
        assert len(pitfalls) >= 1

    def test_distill_both_success_and_failure(self, distiller):
        records = (
            [self.make_record(task_type="mixed", success=True) for _ in range(5)]
            + [self.make_record(task_type="mixed", success=False) for _ in range(3)]
        )
        result = distiller.distill_from_records(records)
        assert len(result) >= 1

    def test_distill_multiple_domains(self, distiller):
        records = (
            [self.make_record(task_type="code") for _ in range(5)]
            + [self.make_record(task_type="test") for _ in range(5)]
        )
        result = distiller.distill_from_records(records)
        domains = set(k.domain for k in result)
        assert len(domains) >= 2

    def test_distill_respects_min_samples_per_task(self, distiller):
        records = (
            [self.make_record(task_type="frequent") for _ in range(5)]
            + [self.make_record(task_type="rare") for _ in range(2)]
        )
        result = distiller.distill_from_records(records)
        domains = set(k.domain for k in result)
        assert "frequent" in domains
        assert "rare" not in domains

    def test_validate_knowledge_valid(self, distiller):
        records = [self.make_record(task_type="code") for _ in range(5)]
        distiller.distill_from_records(records)
        kid = list(distiller._knowledge_base.keys())[0]
        result = distiller.validate_knowledge(kid)
        assert result.valid is True
        assert result.consistency_score >= 0.5

    def test_validate_knowledge_not_found(self, distiller):
        result = distiller.validate_knowledge("nonexistent")
        assert result.valid is False
        assert "Knowledge not found" in result.issues

    def test_validate_knowledge_contradiction(self, distiller):
        records_high = [
            ExecutionRecord(agent_id="a1", task_type="same_domain", success=True,
                          latency=1.0, timestamp=100.0)
            for _ in range(5)
        ]
        distiller.distill_from_records(records_high)
        # Add a low confidence piece in same domain
        records_low = [
            ExecutionRecord(agent_id="a1", task_type="same_domain", success=False,
                          latency=1.0, error_message="fail", timestamp=200.0)
            for _ in range(5)
        ]
        distiller._recognizer = None
        distiller.distill_from_records(records_low)
        # Find the low-confidence knowledge
        for kid, k in distiller._knowledge_base.items():
            result = distiller.validate_knowledge(kid)
            break

    def test_record_knowledge_use(self, distiller):
        records = [self.make_record(task_type="code") for _ in range(5)]
        knowledge = distiller.distill_from_records(records)
        kid = knowledge[0].knowledge_id
        distiller.record_knowledge_use(kid)
        assert distiller._knowledge_base[kid].use_count == 1

    def test_record_knowledge_use_nonexistent(self, distiller):
        distiller.record_knowledge_use("no-such-id")
        stats = distiller.get_statistics()
        assert stats["total_uses"] == 0

    def test_search_knowledge_by_query(self, distiller):
        records = [self.make_record(task_type="deploy") for _ in range(5)]
        distiller.distill_from_records(records)
        results = distiller.search_knowledge(query="deploy")
        assert len(results) >= 1

    def test_search_knowledge_by_domain(self, distiller):
        records = [self.make_record(task_type="deploy") for _ in range(5)]
        distiller.distill_from_records(records)
        results = distiller.search_knowledge(domain="deploy")
        assert len(results) >= 1

    def test_search_knowledge_by_min_confidence(self, distiller):
        records = [self.make_record(task_type="deploy") for _ in range(5)]
        distiller.distill_from_records(records)
        results = distiller.search_knowledge(domain="deploy", min_confidence=0.9)
        assert isinstance(results, list)

    def test_search_knowledge_no_results(self, distiller):
        results = distiller.search_knowledge(query="nonexistent")
        assert results == []

    def test_search_knowledge_empty_query_returns_all(self, distiller):
        records = [self.make_record(task_type="code") for _ in range(5)]
        distiller.distill_from_records(records)
        results = distiller.search_knowledge()
        assert len(results) >= 1

    def test_health(self, distiller):
        h = distiller.health()
        assert h["alive"] is True
        assert h["knowledge_pieces"] == 0

    def test_health_with_knowledge(self, distiller):
        records = [self.make_record(task_type="code") for _ in range(5)]
        distiller.distill_from_records(records)
        h = distiller.health()
        assert h["knowledge_pieces"] >= 1

    def test_get_statistics(self, distiller):
        records = [self.make_record(task_type="code") for _ in range(5)]
        distiller.distill_from_records(records)
        stats = distiller.get_statistics()
        assert stats["total_knowledge_pieces"] >= 1
        assert stats["domains_covered"] >= 1
        assert stats["avg_confidence"] > 0

    def test_with_graph_store(self):
        mock_graph = MagicMock()
        mock_graph.get_entity_by_name.return_value = []
        distiller = KnowledgeDistiller(graph_store=mock_graph)
        records = [
            ExecutionRecord(agent_id="a1", task_type="code", success=True,
                          latency=1.0, timestamp=100.0)
            for _ in range(5)
        ]
        distiller.distill_from_records(records)
        mock_graph.get_entity_by_name.assert_called()
        mock_graph.create_entity.assert_called()

    def test_graph_store_error_does_not_crash(self):
        mock_graph = MagicMock()
        mock_graph.get_entity_by_name.return_value = []
        mock_graph.create_entity.side_effect = RuntimeError("KG error")
        distiller = KnowledgeDistiller(graph_store=mock_graph)
        records = [
            ExecutionRecord(agent_id="a1", task_type="code", success=True,
                          latency=1.0, timestamp=100.0)
            for _ in range(5)
        ]
        knowledge = distiller.distill_from_records(records)
        assert len(knowledge) >= 1

    def test_concurrent_distillation(self, distiller):
        import threading
        errors = []

        def distill():
            try:
                records = [
                    ExecutionRecord(agent_id="a1", task_type="conc", success=True,
                                  latency=1.0, timestamp=100.0)
                    for _ in range(5)
                ]
                distiller.distill_from_records(records)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=distill) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(errors) == 0
        stats = distiller.get_statistics()
        assert stats["total_knowledge_pieces"] >= 1
