from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class CommandType(Enum):
    CHAT = "chat"
    AUTOMATION = "automation"
    DEVELOPER = "developer"
    UNKNOWN = "unknown"


@dataclass(slots=True)
class RouteResult:
    command_type: CommandType
    command: str


class CommandRouter:

    def __init__(self):
        self.automation = [
            "open",
            "close",
            "start",
            "shutdown",
            "restart",
            "launch",
        ]

        self.developer = [
            "build",
            "compile",
            "test",
            "commit",
            "push",
            "pull",
            "debug",
            "continue",
        ]

    def route(self, text: str) -> RouteResult:

        text = text.lower()

        for word in self.automation:
            if text.startswith(word):
                return RouteResult(CommandType.AUTOMATION, text)

        for word in self.developer:
            if text.startswith(word):
                return RouteResult(CommandType.DEVELOPER, text)

        return RouteResult(CommandType.CHAT, text)