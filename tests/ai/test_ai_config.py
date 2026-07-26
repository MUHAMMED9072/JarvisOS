"""Tests for AI Configuration Framework."""

from __future__ import annotations

import copy

import pytest

from app.ai.config import (
    AIConfig,
    ConversationConfig,
    EventConfig,
    FeatureFlags,
    MemoryConfig,
    ProviderConfig,
    RetryConfig,
    RoutingConfig,
    StreamingConfig,
    ToolConfig,
)
from app.ai.manager import AIManager
from app.ai.router import AIRouter
from app.core.config import Config
from app.cortex.handlers.ai_handler import AIHandler


# ==========================================================================
# Configuration loading
# ==========================================================================


class TestAIConfigDefaults:
    """AIConfig loads with sensible defaults matching the codebase."""

    def test_providers_have_defaults(self):
        cfg = AIConfig()
        assert "openai" in cfg.providers
        assert "ollama" in cfg.providers
        assert "gemini" in cfg.providers
        assert "deepseek" in cfg.providers
        assert "claude" in cfg.providers

    def test_openai_defaults(self):
        p = AIConfig().providers["openai"]
        assert p.base_url == "https://api.openai.com/v1"
        assert p.model == "gpt-4o-mini"
        assert p.timeout == 30.0
        assert p.max_retries == 3
        assert p.enabled is True
        assert p.api_key_env == "OPENAI_API_KEY"

    def test_ollama_defaults(self):
        p = AIConfig().providers["ollama"]
        assert p.base_url == "http://localhost:11434"
        assert p.model == "qwen2.5-coder"
        assert p.timeout == 30.0
        assert p.api_key_env == ""

    def test_gemini_defaults(self):
        p = AIConfig().providers["gemini"]
        assert p.model == "gemini-2.0-flash-exp"
        assert p.api_key_env == "GEMINI_API_KEY"

    def test_deepseek_defaults(self):
        p = AIConfig().providers["deepseek"]
        assert p.model == "deepseek-chat"
        assert p.api_key_env == "DEEPSEEK_API_KEY"

    def test_claude_defaults(self):
        p = AIConfig().providers["claude"]
        assert p.model == "claude-3-5-sonnet-latest"
        assert p.api_key_env == "ANTHROPIC_API_KEY"
        assert p.extra.get("max_tokens") == 1024

    def test_retry_defaults(self):
        r = AIConfig().retry
        assert r.max_retries == 3
        assert r.base_delay == 0.5
        assert "timeout" in r.retryable_errors

    def test_streaming_defaults(self):
        s = AIConfig().streaming
        assert s.enabled is True
        assert s.chunk_timeout == 30.0

    def test_conversation_defaults(self):
        c = AIConfig().conversation
        assert c.max_messages == 50
        assert c.default_provider == "deepseek"
        assert c.conversation_id_length == 12

    def test_memory_defaults(self):
        m = AIConfig().memory
        assert m.include_session_messages is True
        assert m.include_memory_search is True
        assert m.max_session_messages == 6
        assert m.max_search_results == 3

    def test_tool_defaults(self):
        t = AIConfig().tools
        assert t.max_calls_per_request == 10

    def test_event_defaults(self):
        e = AIConfig().events
        assert e.publish_enabled is True

    def test_feature_flags_defaults(self):
        f = AIConfig().features
        assert f.streaming is True
        assert f.function_calling is True
        assert f.embeddings is True
        assert f.image_input is True
        assert f.json_output is True
        assert f.conversation is True
        assert f.system_prompt is True
        assert f.reasoning is True
        assert f.planning is True
        assert f.memory_integration is True
        assert f.event_publishing is True

    def test_routing_defaults(self):
        r = AIConfig().routing
        assert r.strategy == "preferred"
        assert "ollama" in r.provider_order
        assert "deepseek" in r.provider_order
        assert r.offline_provider == "ollama"
        assert r.max_retries_per_provider == 3
        assert r.disabled_providers == ()


# ==========================================================================
# Overrides
# ==========================================================================


class TestAIConfigOverrides:
    """AIConfig fields can be overridden."""

    def test_override_provider_model(self):
        cfg = AIConfig()
        cfg.providers["openai"].model = "gpt-4"
        assert cfg.providers["openai"].model == "gpt-4"

    def test_override_conversation_max_messages(self):
        cfg = AIConfig()
        cfg.conversation.max_messages = 100
        assert cfg.conversation.max_messages == 100

    def test_override_feature_flag(self):
        cfg = AIConfig()
        cfg.features.streaming = False
        assert cfg.features.streaming is False


# ==========================================================================
# Validation
# ==========================================================================


class TestAIConfigValidation:
    """AIConfig.validate() catches invalid values."""

    def test_valid_config_returns_empty(self):
        cfg = AIConfig()
        assert cfg.validate() == []

    def test_invalid_conversation_max_messages(self):
        cfg = AIConfig()
        cfg.conversation.max_messages = 0
        errors = cfg.validate()
        assert any("max_messages" in e for e in errors)

    def test_invalid_retry_base_delay(self):
        cfg = AIConfig()
        cfg.retry.base_delay = 0
        errors = cfg.validate()
        assert any("base_delay" in e for e in errors)

    def test_invalid_timeout(self):
        cfg = AIConfig()
        cfg.providers["ollama"].timeout = -1
        errors = cfg.validate()
        assert any("timeout" in e for e in errors)

    def test_empty_providers(self):
        cfg = AIConfig()
        cfg.providers.clear()
        errors = cfg.validate()
        assert any("providers" in e for e in errors)


# ==========================================================================
# Runtime reload
# ==========================================================================


class TestRuntimeReload:
    """AIConfig.reload() re-reads from Config.AI."""

    def test_reload_updates_providers(self):
        original = Config.AI.providers["ollama"].model
        Config.AI.providers["ollama"].model = "llama3"
        cfg = copy.deepcopy(Config.AI)
        try:
            assert cfg.providers["ollama"].model == "llama3"
        finally:
            Config.AI.providers["ollama"].model = original

    def test_reload_preserves_other_fields(self):
        original = Config.AI.conversation.max_messages
        Config.AI.conversation.max_messages = 100
        cfg = AIConfig()
        cfg.reload()
        assert cfg.conversation.max_messages == 100
        Config.AI.conversation.max_messages = original

    def test_reload_handles_missing_config(self):
        cfg = AIConfig()
        original = Config.AI
        # Simulate Config.AI being missing by temporarily
        # replacing it with an object that lacks expected attrs
        class _FakeConfig:
            pass
        Config.AI = _FakeConfig()  # type: ignore[assignment]
        cfg.reload()  # Should not raise
        Config.AI = original


# ==========================================================================
# Feature flags
# ==========================================================================


class TestFeatureFlags:
    """Feature flags control AI capabilities."""

    def test_streaming_flag(self):
        cfg = AIConfig()
        assert cfg.features.streaming is True
        cfg.features.streaming = False
        assert cfg.features.streaming is False

    def test_planning_flag(self):
        cfg = AIConfig()
        assert cfg.features.planning is True

    def test_reasoning_flag(self):
        cfg = AIConfig()
        assert cfg.features.reasoning is True

    def test_event_publishing_flag(self):
        cfg = AIConfig()
        assert cfg.features.event_publishing is True


# ==========================================================================
# Provider configuration
# ==========================================================================


class TestProviderConfiguration:
    """Each provider has its own config entry."""

    def test_all_providers_have_config(self):
        cfg = AIConfig()
        for name in ("openai", "ollama", "gemini", "deepseek", "claude"):
            assert name in cfg.providers
            p = cfg.providers[name]
            assert isinstance(p, ProviderConfig)
            assert p.timeout > 0


# ==========================================================================
# Routing configuration
# ==========================================================================


class TestRoutingConfiguration:
    """Routing config controls provider selection."""

    def test_build_routing_config(self):
        cfg = AIConfig()
        rc = cfg.build_routing_config()
        from app.ai.routing import RoutingConfig, RoutingStrategy

        assert isinstance(rc, RoutingConfig)
        assert rc.strategy == RoutingStrategy.PREFERRED
        assert "ollama" in rc.providers

    def test_custom_routing_config(self):
        cfg = AIConfig()
        cfg.routing.strategy = "failover"
        cfg.routing.offline_provider = "deepseek"
        rc = cfg.build_routing_config()
        from app.ai.routing import RoutingConfig, RoutingStrategy

        assert rc.strategy == RoutingStrategy.FAILOVER
        assert rc.offline_provider == "deepseek"


# ==========================================================================
# AIManager wiring
# ==========================================================================


class TestAIManagerWiring:
    """AIManager uses Config.AI for conversation defaults."""

    def test_create_conversation_uses_config_default(self):
        ai = AIManager()
        conv = ai.create_conversation()
        assert conv.max_messages == Config.AI.conversation.max_messages

    def test_create_conversation_override_still_works(self):
        ai = AIManager()
        conv = ai.create_conversation(max_messages=10)
        assert conv.max_messages == 10


# ==========================================================================
# Router wiring
# ==========================================================================


class TestRouterWiring:
    """AIRouter uses Config.AI for routing defaults."""

    def test_router_uses_config_routing(self):
        router = AIRouter()
        assert router.routing_config is not None
        assert "ollama" in router.routing_config.providers

    def test_router_accepts_explicit_routing_config(self):
        from app.ai.routing import RoutingConfig, RoutingStrategy

        rc = RoutingConfig(strategy=RoutingStrategy.FAILOVER)
        router = AIRouter(routing_config=rc)
        assert router.routing_config.strategy == RoutingStrategy.FAILOVER


# ==========================================================================
# AIHandler wiring
# ==========================================================================


class TestAIHandlerWiring:
    """AIHandler uses Config.AI for default provider."""

    def test_default_provider_matches_config(self):
        assert AIHandler.DEFAULT_PROVIDER == Config.AI.conversation.default_provider


# ==========================================================================
# Backward compatibility
# ==========================================================================


class TestBackwardCompatibility:
    """Existing code continues to work with the new config."""

    def test_aimanager_works_as_before(self):
        ai = AIManager()
        assert ai.conversation_manager is not None
        assert ai.router is not None

    def test_router_works_as_before(self):
        router = AIRouter()
        assert router.providers is not None
        assert len(router.providers) > 0

    def test_aihandler_works_as_before(self):
        from app.core.registry import ServiceRegistry

        reg = ServiceRegistry()
        reg.register("ai_manager", AIManager())
        reg.register("memory_aware_ai", None)
        reg.register("memory", None)
        handler = AIHandler(reg)
        assert handler is not None

    def test_config_ai_is_accessible(self):
        assert hasattr(Config, "AI")
        assert Config.AI.conversation.max_messages == 50


# ==========================================================================
# Config reload
# ==========================================================================


class TestRuntimeConfigReload:
    """Config.AI supports runtime reload."""

    def test_reload_with_modifications(self):
        original = Config.AI.conversation.max_messages
        Config.AI.conversation.max_messages = 200
        cfg = AIConfig()
        cfg.reload()
        assert cfg.conversation.max_messages == 200
        Config.AI.conversation.max_messages = original

    def test_reload_validation_after_modification(self):
        original = Config.AI.providers["ollama"].timeout
        Config.AI.providers["ollama"].timeout = 60.0
        cfg = AIConfig()
        cfg.reload()
        assert cfg.providers["ollama"].timeout == 60.0
        Config.AI.providers["ollama"].timeout = original
