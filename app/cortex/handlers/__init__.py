from __future__ import annotations

from abc import ABC

from app.core.registry import ServiceRegistry


class BaseHandler(ABC):
    """Thin wrapper around an existing JARVIS service."""

    def __init__(self, registry: ServiceRegistry) -> None:
        self.registry = registry
