from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class IncidentSeverity(Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class IncidentStatus(Enum):
    OPEN = "open"
    INVESTIGATING = "investigating"
    RESOLVING = "resolving"
    RESOLVED = "resolved"
    CLOSED = "closed"


@dataclass
class Incident:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    component_id: str = ""
    severity: IncidentSeverity = IncidentSeverity.ERROR
    status: IncidentStatus = IncidentStatus.OPEN
    title: str = ""
    description: str = ""
    evidence: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    resolved_at: float | None = None
    resolved_by: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "component_id": self.component_id,
            "severity": self.severity.value,
            "status": self.status.value,
            "title": self.title,
            "description": self.description,
            "evidence": list(self.evidence),
            "created_at": self.created_at,
            "resolved_at": self.resolved_at,
            "resolved_by": self.resolved_by,
        }


class IncidentStore:
    """Thread-safe in-memory store for incidents.

    Future: persist to Knowledge Graph for long-term storage.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._incidents: dict[str, Incident] = {}
        self._component_index: dict[str, list[str]] = {}

    def record(self, incident: Incident) -> str:
        with self._lock:
            self._incidents[incident.id] = incident
            if incident.component_id not in self._component_index:
                self._component_index[incident.component_id] = []
            self._component_index[incident.component_id].append(incident.id)
            return incident.id

    def get(self, incident_id: str) -> Incident | None:
        with self._lock:
            return self._incidents.get(incident_id)

    def get_by_component(self, component_id: str) -> list[Incident]:
        with self._lock:
            ids = self._component_index.get(component_id, [])
            return [self._incidents[iid] for iid in ids if iid in self._incidents]

    def update_status(self, incident_id: str, status: IncidentStatus, resolved_by: str = "") -> bool:
        with self._lock:
            inc = self._incidents.get(incident_id)
            if inc is None:
                return False
            inc.status = status
            if status in (IncidentStatus.RESOLVED, IncidentStatus.CLOSED):
                inc.resolved_at = time.time()
                inc.resolved_by = resolved_by
            return True

    def get_all(self) -> list[Incident]:
        with self._lock:
            return list(self._incidents.values())

    def get_open(self) -> list[Incident]:
        with self._lock:
            return [i for i in self._incidents.values() if i.status == IncidentStatus.OPEN]

    def count(self) -> int:
        with self._lock:
            return len(self._incidents)

    def clear(self) -> None:
        with self._lock:
            self._incidents.clear()
            self._component_index.clear()
