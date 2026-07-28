from __future__ import annotations

import json
import os
import tempfile
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class Fact:
    id: str
    subject: str
    predicate: str
    obj: str
    confidence: float = 1.0
    source: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    created: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "subject": self.subject,
            "predicate": self.predicate,
            "object": self.obj,
            "confidence": self.confidence,
            "source": self.source,
            "metadata": self.metadata,
            "created": self.created,
            "updated": self.updated,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Fact:
        return cls(
            id=data["id"],
            subject=data["subject"],
            predicate=data["predicate"],
            obj=data["object"],
            confidence=data.get("confidence", 1.0),
            source=data.get("source", ""),
            metadata=data.get("metadata", {}),
            created=data.get("created", ""),
            updated=data.get("updated", ""),
        )


class KnowledgeBase:
    """Stores factual knowledge as subject-predicate-object triples."""

    def __init__(self, filename: str = "knowledge.json") -> None:
        self.path = Path("data") / "memory" / filename
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._facts: dict[str, Fact] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for item in data.get("facts", []):
                fact = Fact.from_dict(item)
                self._facts[fact.id] = fact
        except Exception:
            self._facts = {}

    def save(self) -> None:
        data = {
            "facts": [f.to_dict() for f in self._facts.values()],
        }
        fd, tmp = tempfile.mkstemp(
            dir=str(self.path.parent), prefix=".tmp_", suffix=".json"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(tmp, str(self.path))
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def add_fact(
        self,
        subject: str,
        predicate: str,
        obj: str,
        confidence: float = 1.0,
        source: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> Fact:
        fact = Fact(
            id=uuid.uuid4().hex,
            subject=subject,
            predicate=predicate,
            obj=obj,
            confidence=confidence,
            source=source,
            metadata=metadata or {},
        )
        self._facts[fact.id] = fact
        self.save()
        return fact

    def get_fact(self, fact_id: str) -> Fact | None:
        return self._facts.get(fact_id)

    def query(
        self,
        subject: str | None = None,
        predicate: str | None = None,
        obj: str | None = None,
    ) -> list[Fact]:
        results = list(self._facts.values())
        if subject:
            results = [f for f in results if f.subject == subject]
        if predicate:
            results = [f for f in results if f.predicate == predicate]
        if obj:
            results = [f for f in results if f.obj == obj]
        return results

    def delete_fact(self, fact_id: str) -> bool:
        if fact_id in self._facts:
            del self._facts[fact_id]
            self.save()
            return True
        return False

    def update_fact(
        self,
        fact_id: str,
        confidence: float | None = None,
        source: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Fact | None:
        fact = self._facts.get(fact_id)
        if fact is None:
            return None
        if confidence is not None:
            fact.confidence = confidence
        if source is not None:
            fact.source = source
        if metadata is not None:
            fact.metadata.update(metadata)
        fact.updated = datetime.now(timezone.utc).isoformat()
        self.save()
        return fact

    def count(self) -> int:
        return len(self._facts)

    def clear(self) -> None:
        self._facts.clear()
        self.save()

    def search(self, query: str) -> list[Fact]:
        q = query.lower()
        return [
            f
            for f in self._facts.values()
            if q in f.subject.lower()
            or q in f.predicate.lower()
            or q in f.obj.lower()
        ]
