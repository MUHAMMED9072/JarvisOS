from __future__ import annotations

import enum
from abc import ABC, abstractmethod
from typing import Any


class AgentStatus(enum.Enum):
    DESIGN = "design"
    BUILD = "build"
    SANDBOX = "sandbox"
    REVIEW = "review"
    APPROVED = "approved"
    INSTALLED = "installed"
    ACTIVE = "active"
    PAUSED = "paused"
    RETIRED = "retired"
    ARCHIVED = "archived"
    FAILED = "failed"


class AgentCapability:
    """Represents a capability that an agent provides."""

    def __init__(
        self,
        name: str,
        description: str = "",
        quality_score: float = 0.5,
    ) -> None:
        self.name = name
        self.description = description
        self.quality_score = quality_score

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "quality_score": self.quality_score,
        }


class AgentMetadata:
    """Structured metadata for an agent."""

    def __init__(
        self,
        agent_id: str = "",
        name: str = "",
        version: str = "1.0.0",
        description: str = "",
        agent_type: str = "system",
        status: AgentStatus = AgentStatus.DESIGN,
        capabilities: list[AgentCapability] | None = None,
        dependencies: list[str] | None = None,
        owner: str = "",
        tags: list[str] | None = None,
    ) -> None:
        self.agent_id = agent_id
        self.name = name
        self.version = version
        self.description = description
        self.agent_type = agent_type
        self.status = status
        self.capabilities = capabilities or []
        self.dependencies = dependencies or []
        self.owner = owner
        self.tags = tags or []

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "agent_type": self.agent_type,
            "status": self.status.value,
            "capabilities": [c.to_dict() for c in self.capabilities],
            "dependencies": list(self.dependencies),
            "owner": self.owner,
            "tags": list(self.tags),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentMetadata:
        caps = [AgentCapability(**c) if isinstance(c, dict) else c for c in data.get("capabilities", [])]
        status = AgentStatus(data["status"]) if "status" in data else AgentStatus.DESIGN
        return cls(
            agent_id=data.get("agent_id", ""),
            name=data.get("name", ""),
            version=data.get("version", "1.0.0"),
            description=data.get("description", ""),
            agent_type=data.get("agent_type", "system"),
            status=status,
            capabilities=caps,
            dependencies=list(data.get("dependencies", [])),
            owner=data.get("owner", ""),
            tags=list(data.get("tags", [])),
        )


class Agent(ABC):
    """Abstract base class for all agents in the JARVIS system.

    Lifecycle hooks are called in order:
      on_init → on_start → on_execute → on_complete → on_stop
    """

    def __init__(self, metadata: AgentMetadata) -> None:
        self.metadata = metadata
        self._event_bus: Any = None

    @abstractmethod
    def execute(self, context: dict[str, Any]) -> dict[str, Any]:
        ...

    @property
    def agent_id(self) -> str:
        return self.metadata.agent_id

    @property
    def agent_type(self) -> str:
        return self.metadata.agent_type

    @property
    def status(self) -> AgentStatus:
        return self.metadata.status

    @status.setter
    def status(self, value: AgentStatus) -> None:
        self.metadata.status = value

    def to_dict(self) -> dict[str, Any]:
        return self.metadata.to_dict()

    # ------------------------------------------------------------------
    # Lifecycle hooks
    # ------------------------------------------------------------------

    def on_init(self) -> None:
        """Called when the agent is first created."""

    def on_start(self) -> None:
        """Called when the agent is activated."""

    def on_complete(self, result: dict[str, Any]) -> None:
        """Called after execute succeeds."""

    def on_stop(self) -> None:
        """Called when the agent is stopped."""

    def on_error(self, error: Exception) -> None:
        """Called when execute raises an exception."""
