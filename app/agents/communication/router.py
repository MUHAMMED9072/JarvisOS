from __future__ import annotations

import time
from collections import defaultdict
from typing import Any

from app.agents.communication.message import DeliveryGuarantee, Message, MessageType


class MessageRouter:
    """Routes messages to specific agents, groups, or broadcasts."""

    def __init__(self) -> None:
        self._routes: dict[str, str] = {}  # agent_id -> topic
        self._groups: dict[str, list[str]] = defaultdict(list)  # group_name -> agent_ids

    def register_agent(self, agent_id: str, topic: str = "") -> None:
        self._routes[agent_id] = topic

    def unregister_agent(self, agent_id: str) -> None:
        self._routes.pop(agent_id, None)
        for group in self._groups.values():
            if agent_id in group:
                group.remove(agent_id)

    def join_group(self, agent_id: str, group: str) -> None:
        if agent_id not in self._groups[group]:
            self._groups[group].append(agent_id)

    def leave_group(self, agent_id: str, group: str) -> None:
        if agent_id in self._groups.get(group, []):
            self._groups[group].remove(agent_id)

    def group_members(self, group: str) -> list[str]:
        return list(self._groups.get(group, []))

    def route(
        self, message: Message,
    ) -> list[str]:
        """Determine target agent IDs for a message."""
        target = message.target
        if target is None:
            return []
        if isinstance(target, str):
            if target in self._routes:
                return [target]
            # check if target is a group name
            if target in self._groups:
                return list(self._groups[target])
            return []
        if isinstance(target, list):
            return [t for t in target if t in self._routes]
        return []

    def topic_for(self, agent_id: str) -> str:
        return self._routes.get(agent_id, "")

    def health(self) -> dict[str, Any]:
        return {
            "alive": True,
            "registered_agents": len(self._routes),
            "groups": {k: len(v) for k, v in self._groups.items()},
        }
