from __future__ import annotations

from abc import ABC, abstractmethod

from app.core.registry import ServiceRegistry
from app.cortex.models import CortexRequest
from app.skills.result import SkillResult


class BaseBrain(ABC):
    """Strategy for processing a CortexRequest."""

    def __init__(self, registry: ServiceRegistry) -> None:
        self.registry = registry

    @abstractmethod
    def process(self, request: CortexRequest) -> SkillResult:
        ...
