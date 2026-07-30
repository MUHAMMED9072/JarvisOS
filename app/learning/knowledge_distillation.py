from __future__ import annotations

import collections
import hashlib
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from app.knowledge_graph.store import GraphStore
from app.learning.pattern_recognition import ExecutionRecord, PatternRecognizer


@dataclass
class DistilledKnowledge:
    knowledge_id: str = ""
    title: str = ""
    summary: str = ""
    domain: str = ""
    source_count: int = 0
    confidence: float = 0.0
    quality_score: float = 0.5
    use_count: int = 0
    tags: list[str] = field(default_factory=list)
    created_at: float = 0.0
    updated_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "knowledge_id": self.knowledge_id,
            "title": self.title,
            "summary": self.summary,
            "domain": self.domain,
            "source_count": self.source_count,
            "confidence": round(self.confidence, 4),
            "quality_score": round(self.quality_score, 4),
            "use_count": self.use_count,
            "tags": list(self.tags),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class KnowledgeValidationResult:
    valid: bool = False
    knowledge_id: str = ""
    consistency_score: float = 0.0
    contradiction_count: int = 0
    evidence_count: int = 0
    issues: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "knowledge_id": self.knowledge_id,
            "consistency_score": round(self.consistency_score, 4),
            "contradiction_count": self.contradiction_count,
            "evidence_count": self.evidence_count,
            "issues": list(self.issues),
        }


class KnowledgeDistiller:
    """Extracts general knowledge from specific agent experiences.

    Analyzes execution records to identify reusable knowledge,
    generalizes specific experiences, validates correctness,
    and publishes to the Knowledge Graph.
    """

    def __init__(
        self,
        graph_store: GraphStore | None = None,
        pattern_recognizer: PatternRecognizer | None = None,
    ) -> None:
        self._graph = graph_store
        self._recognizer = pattern_recognizer
        self._lock = threading.RLock()
        self._knowledge_base: dict[str, DistilledKnowledge] = {}

    def distill_from_records(
        self,
        records: list[ExecutionRecord],
    ) -> list[DistilledKnowledge]:
        if len(records) < 3:
            return []

        task_groups: dict[str, list[ExecutionRecord]] = {}
        for rec in records:
            tt = rec.task_type or "unknown"
            if tt not in task_groups:
                task_groups[tt] = []
            task_groups[tt].append(rec)

        knowledge_pieces: list[DistilledKnowledge] = []

        for task_type, group in task_groups.items():
            if len(group) < 3:
                continue

            total = len(group)
            successes = sum(1 for r in group if r.success)
            success_rate = successes / total
            avg_lat = sum(r.latency for r in group) / total

            tag_counter: collections.Counter = collections.Counter()
            agent_counter: collections.Counter = collections.Counter()
            for rec in group:
                for t in rec.task_tags:
                    tag_counter[t] += 1
                agent_counter[rec.agent_id] += 1

            common_tags = [t for t, _ in tag_counter.most_common(3)]

            if success_rate >= 0.7 and successes >= 3:
                knowledge = DistilledKnowledge(
                    knowledge_id=uuid.uuid4().hex[:16],
                    title=f"Optimal approach for {task_type}",
                    summary=f"Based on {total} executions across {len(agent_counter)} agents, "
                            f"achieving {success_rate:.0%} success rate with {avg_lat:.2f}s avg latency.",
                    domain=task_type,
                    source_count=total,
                    confidence=success_rate,
                    quality_score=success_rate * 0.8 + 0.2,
                    tags=common_tags + [task_type],
                    created_at=time.time(),
                    updated_at=time.time(),
                )
                knowledge_pieces.append(knowledge)

            if successes > 0 and total - successes > 0:
                failure_rate = 1.0 - success_rate
                if failure_rate >= 0.2 and total - successes >= 3:
                    knowledge = DistilledKnowledge(
                        knowledge_id=uuid.uuid4().hex[:16],
                        title=f"Common pitfalls in {task_type}",
                        summary=f"Failure rate of {failure_rate:.0%} observed across {total} executions. "
                                f"Review agent configurations for {', '.join(common_tags[:3])} scenarios.",
                        domain=task_type,
                        source_count=total,
                        confidence=failure_rate,
                        quality_score=failure_rate * 0.6,
                        tags=common_tags + [task_type, "pitfall"],
                        created_at=time.time(),
                        updated_at=time.time(),
                    )
                    knowledge_pieces.append(knowledge)

        with self._lock:
            for k in knowledge_pieces:
                self._knowledge_base[k.knowledge_id] = k
                self._publish_to_graph(k)

        return knowledge_pieces

    def validate_knowledge(self, knowledge_id: str) -> KnowledgeValidationResult:
        with self._lock:
            k = self._knowledge_base.get(knowledge_id)
            if k is None:
                return KnowledgeValidationResult(
                    valid=False,
                    issues=["Knowledge not found"],
                )

        total = len(self._knowledge_base)
        contradictions = 0
        for other in self._knowledge_base.values():
            if other.knowledge_id != knowledge_id and other.domain == k.domain:
                if other.confidence > 0.7 and k.confidence < 0.3:
                    contradictions += 1

        consistency = max(0.0, 1.0 - contradictions / max(total, 1))
        valid = consistency >= 0.5 and k.source_count >= 3

        return KnowledgeValidationResult(
            valid=valid,
            knowledge_id=knowledge_id,
            consistency_score=consistency,
            contradiction_count=contradictions,
            evidence_count=k.source_count,
            issues=[] if valid else ["Low consistency or insufficient evidence"],
        )

    def record_knowledge_use(self, knowledge_id: str) -> None:
        with self._lock:
            k = self._knowledge_base.get(knowledge_id)
            if k:
                k.use_count += 1
                k.updated_at = time.time()

    def search_knowledge(
        self,
        query: str = "",
        domain: str = "",
        min_confidence: float = 0.0,
    ) -> list[DistilledKnowledge]:
        q = query.lower()
        with self._lock:
            results = list(self._knowledge_base.values())
            if q:
                results = [
                    k for k in results
                    if q in k.title.lower() or q in k.summary.lower() or q in k.domain.lower()
                ]
            if domain:
                results = [k for k in results if k.domain == domain]
            if min_confidence > 0:
                results = [k for k in results if k.confidence >= min_confidence]
            results.sort(key=lambda k: k.confidence, reverse=True)
            return results

    def _publish_to_graph(self, knowledge: DistilledKnowledge) -> None:
        if self._graph is None:
            return
        try:
            existing = self._graph.get_entity_by_name(knowledge.title)
            if not existing:
                self._graph.create_entity(
                    type="distilled_knowledge",
                    name=knowledge.title,
                    properties=knowledge.to_dict(),
                )
        except Exception:
            pass

    def get_statistics(self) -> dict[str, Any]:
        with self._lock:
            total = len(self._knowledge_base)
            avg_conf = sum(k.confidence for k in self._knowledge_base.values()) / max(total, 1)
            domains = len(set(k.domain for k in self._knowledge_base.values()))
        return {
            "total_knowledge_pieces": total,
            "avg_confidence": round(avg_conf, 4),
            "domains_covered": domains,
            "total_uses": sum(k.use_count for k in self._knowledge_base.values()),
        }

    def health(self) -> dict[str, Any]:
        stats = self.get_statistics()
        return {
            "alive": True,
            "knowledge_pieces": stats["total_knowledge_pieces"],
            "domains_covered": stats["domains_covered"],
        }
