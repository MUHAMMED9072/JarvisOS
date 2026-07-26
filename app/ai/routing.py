from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class RoutingStrategy(Enum):
    PREFERRED = auto()
    OFFLINE_FIRST = auto()
    ONLINE_FIRST = auto()
    FAILOVER = auto()


class ProviderStatus(Enum):
    AVAILABLE = auto()
    UNAVAILABLE = auto()
    DISABLED = auto()
    NO_CREDENTIALS = auto()


@dataclass(frozen=True)
class RoutingConfig:
    strategy: RoutingStrategy = RoutingStrategy.PREFERRED
    providers: tuple[str, ...] = (
        "ollama", "openai", "claude", "gemini", "deepseek",
    )
    offline_provider: str = "ollama"
    max_retries_per_provider: int = 3
    enabled_providers: tuple[str, ...] | None = None
    disabled_providers: tuple[str, ...] = ()
