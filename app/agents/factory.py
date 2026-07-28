from __future__ import annotations

import uuid
from typing import Any

from app.agents.base import Agent, AgentMetadata
from app.agents.types import (
    SystemAgent,
    ToolAgent,
    DevelopmentAgent,
    DomainAgent,
    CompositeAgent,
)


class AgentFactory:
    """Creates agent instances from registered types."""

    _registry: dict[str, type[Agent]] = {
        "system": SystemAgent,
        "tool": ToolAgent,
        "development": DevelopmentAgent,
        "domain": DomainAgent,
        "composite": CompositeAgent,
    }

    @classmethod
    def register_type(cls, type_name: str, agent_class: type[Agent]) -> None:
        cls._registry[type_name] = agent_class

    @classmethod
    def create(
        cls,
        agent_type: str,
        name: str = "",
        version: str = "1.0.0",
        description: str = "",
        capabilities: list[dict[str, Any]] | None = None,
        dependencies: list[str] | None = None,
        **kwargs: Any,
    ) -> Agent:
        agent_class = cls._registry.get(agent_type)
        if agent_class is None:
            raise ValueError(f"Unknown agent type '{agent_type}'")

        metadata = AgentMetadata(
            agent_id=kwargs.pop("agent_id", uuid.uuid4().hex[:16]),
            name=name or f"{agent_type}_agent",
            version=version,
            description=description,
            agent_type=agent_type,
            capabilities=[],  # capabilities parsed separately
            dependencies=dependencies or [],
        )

        if agent_type == "tool":
            return ToolAgent(tool_name=kwargs.get("tool_name", ""), metadata=metadata)
        if agent_type == "development":
            return DevelopmentAgent(language=kwargs.get("language", "python"), metadata=metadata)
        if agent_type == "domain":
            return DomainAgent(domain=kwargs.get("domain", "general"), metadata=metadata)
        if agent_type == "composite":
            return CompositeAgent(metadata=metadata)
        return agent_class(metadata=metadata)

    @classmethod
    def list_types(cls) -> list[str]:
        return list(cls._registry.keys())

    @classmethod
    def can_create(cls, agent_type: str) -> bool:
        return agent_type in cls._registry
