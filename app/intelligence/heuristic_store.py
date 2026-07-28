from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Heuristic:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    name: str = ""
    domain: str = ""
    weight: float = 1.0
    success_count: int = 0
    failure_count: int = 0
    last_used: float = field(default_factory=time.time)
    created_at: float = field(default_factory=time.time)

    @property
    def reliability(self) -> float:
        total = self.success_count + self.failure_count
        if total == 0:
            return 0.5
        return self.success_count / total

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "domain": self.domain,
            "weight": self.weight,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "reliability": self.reliability,
            "last_used": self.last_used,
            "created_at": self.created_at,
        }


class HeuristicStore:
    """Thread-safe storage for heuristics with CRUD and relevance-based
    retrieval.

    Heuristics track success/failure rates and can be updated based on
    outcome analysis feedback.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._heuristics: dict[str, Heuristic] = {}

    def register(self, heuristic: Heuristic) -> str:
        with self._lock:
            self._heuristics[heuristic.id] = heuristic
            return heuristic.id

    def get(self, heuristic_id: str) -> Heuristic | None:
        with self._lock:
            return self._heuristics.get(heuristic_id)

    def get_by_name(self, name: str) -> Heuristic | None:
        with self._lock:
            for h in self._heuristics.values():
                if h.name == name:
                    return h
            return None

    def update(self, heuristic: Heuristic) -> bool:
        with self._lock:
            if heuristic.id not in self._heuristics:
                return False
            heuristic.last_used = time.time()
            self._heuristics[heuristic.id] = heuristic
            return True

    def delete(self, heuristic_id: str) -> bool:
        with self._lock:
            if heuristic_id in self._heuristics:
                del self._heuristics[heuristic_id]
                return True
            return False

    def list_heuristics(self, domain: str | None = None) -> list[Heuristic]:
        with self._lock:
            result = list(self._heuristics.values())
            if domain:
                result = [h for h in result if h.domain == domain]
            return sorted(result, key=lambda h: h.reliability, reverse=True)

    def find_by_domain(self, domain: str) -> list[Heuristic]:
        return self.list_heuristics(domain=domain)

    def record_success(self, heuristic_id: str) -> bool:
        with self._lock:
            h = self._heuristics.get(heuristic_id)
            if h is None:
                return False
            h.success_count += 1
            h.last_used = time.time()
            return True

    def record_failure(self, heuristic_id: str) -> bool:
        with self._lock:
            h = self._heuristics.get(heuristic_id)
            if h is None:
                return False
            h.failure_count += 1
            h.last_used = time.time()
            return True

    def count(self) -> int:
        with self._lock:
            return len(self._heuristics)

    def clear(self) -> None:
        with self._lock:
            self._heuristics.clear()

    def health(self) -> dict[str, Any]:
        return {"alive": True, "heuristic_count": self.count()}
