from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class BrainType(Enum):
    FAST = "fast"
    SMART = "smart"
    DEEP = "deep"


@dataclass(slots=True)
class CortexRequest:
    text: str
    source: str = "voice"

    normalized: str = ""
    intent: str = ""
    confidence: float = 0.0
    entities: dict = field(default_factory=dict)
    brain: str = ""


@dataclass(slots=True)
class CortexResponse:
    success: bool
    response: str
    provider: str = ""
    model: str = ""
    routing_strategy: str = ""
    conversation_id: str = ""
    template_name: str = ""
    metadata: dict = field(default_factory=dict)