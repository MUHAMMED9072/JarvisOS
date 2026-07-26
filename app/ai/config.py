from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProviderConfig:
    base_url: str = ""
    model: str = ""
    timeout: float = 30.0
    max_retries: int = 3
    enabled: bool = True
    api_key_env: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class RetryConfig:
    max_retries: int = 3
    base_delay: float = 0.5
    retryable_errors: tuple[str, ...] = (
        "timeout", "connection",
    )


@dataclass
class StreamingConfig:
    enabled: bool = True
    chunk_timeout: float = 30.0


@dataclass
class ConversationConfig:
    max_messages: int = 50
    default_provider: str = "deepseek"
    conversation_id_length: int = 12


@dataclass
class MemoryConfig:
    include_session_messages: bool = True
    include_memory_search: bool = True
    max_session_messages: int = 6
    max_search_results: int = 3


@dataclass
class ToolConfig:
    max_calls_per_request: int = 10


@dataclass
class EventConfig:
    publish_enabled: bool = True


@dataclass
class RoutingConfig:
    strategy: str = "preferred"
    provider_order: tuple[str, ...] = (
        "ollama", "openai", "claude", "gemini", "deepseek",
    )
    offline_provider: str = "ollama"
    max_retries_per_provider: int = 3
    disabled_providers: tuple[str, ...] = ()


@dataclass
class FeatureFlags:
    streaming: bool = True
    function_calling: bool = True
    embeddings: bool = True
    image_input: bool = True
    json_output: bool = True
    conversation: bool = True
    system_prompt: bool = True
    reasoning: bool = True
    planning: bool = True
    memory_integration: bool = True
    event_publishing: bool = True


@dataclass
class AIConfig:
    providers: dict[str, ProviderConfig] = field(
        default_factory=lambda: {
            "openai": ProviderConfig(
                base_url="https://api.openai.com/v1",
                model="gpt-4o-mini",
                timeout=30.0,
                max_retries=3,
                enabled=True,
                api_key_env="OPENAI_API_KEY",
            ),
            "ollama": ProviderConfig(
                base_url="http://localhost:11434",
                model="qwen2.5-coder",
                timeout=30.0,
                max_retries=3,
                enabled=True,
                api_key_env="",
            ),
            "gemini": ProviderConfig(
                base_url="https://generativelanguage.googleapis.com",
                model="gemini-2.0-flash-exp",
                timeout=30.0,
                max_retries=3,
                enabled=True,
                api_key_env="GEMINI_API_KEY",
            ),
            "deepseek": ProviderConfig(
                base_url="https://api.deepseek.com",
                model="deepseek-chat",
                timeout=30.0,
                max_retries=3,
                enabled=True,
                api_key_env="DEEPSEEK_API_KEY",
            ),
            "claude": ProviderConfig(
                base_url="https://api.anthropic.com",
                model="claude-3-5-sonnet-latest",
                timeout=30.0,
                max_retries=3,
                enabled=True,
                api_key_env="ANTHROPIC_API_KEY",
                extra={"max_tokens": 1024},
            ),
        },
    )
    routing: RoutingConfig = field(default_factory=RoutingConfig)
    retry: RetryConfig = field(default_factory=RetryConfig)
    streaming: StreamingConfig = field(default_factory=StreamingConfig)
    conversation: ConversationConfig = field(default_factory=ConversationConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    tools: ToolConfig = field(default_factory=ToolConfig)
    events: EventConfig = field(default_factory=EventConfig)
    features: FeatureFlags = field(default_factory=FeatureFlags)

    def build_routing_config(self) -> Any:
        from app.ai.routing import RoutingConfig, RoutingStrategy

        strategy_map = {
            "preferred": RoutingStrategy.PREFERRED,
            "offline_first": RoutingStrategy.OFFLINE_FIRST,
            "online_first": RoutingStrategy.ONLINE_FIRST,
            "failover": RoutingStrategy.FAILOVER,
        }
        return RoutingConfig(
            strategy=strategy_map.get(
                self.routing.strategy, RoutingStrategy.PREFERRED
            ),
            providers=self.routing.provider_order,
            offline_provider=self.routing.offline_provider,
            max_retries_per_provider=self.routing.max_retries_per_provider,
            disabled_providers=self.routing.disabled_providers,
        )

    def reload(self) -> None:
        from app.core.config import Config
        try:
            incoming = Config.AI
            for name, cfg in incoming.providers.items():
                if name in self.providers:
                    self.providers[name] = cfg
            self.routing = incoming.routing
            self.retry = incoming.retry
            self.streaming = incoming.streaming
            self.conversation = incoming.conversation
            self.memory = incoming.memory
            self.tools = incoming.tools
            self.events = incoming.events
            self.features = incoming.features
        except AttributeError:
            pass

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.providers:
            errors.append("providers must not be empty")
        if self.routing.max_retries_per_provider < 0:
            errors.append("routing.max_retries_per_provider must be >= 0")
        if self.conversation.max_messages < 1:
            errors.append("conversation.max_messages must be >= 1")
        if self.conversation.conversation_id_length < 4:
            errors.append("conversation.conversation_id_length must be >= 4")
        if self.retry.max_retries < 0:
            errors.append("retry.max_retries must be >= 0")
        if self.retry.base_delay <= 0:
            errors.append("retry.base_delay must be > 0")
        if self.streaming.chunk_timeout <= 0:
            errors.append("streaming.chunk_timeout must be > 0")
        if self.memory.max_session_messages < 0:
            errors.append("memory.max_session_messages must be >= 0")
        if self.memory.max_search_results < 0:
            errors.append("memory.max_search_results must be >= 0")
        if self.tools.max_calls_per_request < 0:
            errors.append("tools.max_calls_per_request must be >= 0")
        for name, cfg in self.providers.items():
            if cfg.timeout <= 0:
                errors.append(f"providers.{name}.timeout must be > 0")
            if cfg.max_retries < 0:
                errors.append(f"providers.{name}.max_retries must be >= 0")
        return errors
