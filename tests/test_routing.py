from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.ai.providers.base import (
    AIProvider,
    AIProviderError,
    AIResponse,
    AllProvidersFailedError,
    ProviderTimeoutError,
)
from app.ai.router import AIRouter
from app.ai.routing import ProviderStatus, RoutingConfig, RoutingStrategy


# ---------------------------------------------------------------------------
# Mock provider for controlled routing scenarios
# ---------------------------------------------------------------------------


class _MockProvider:
    """A controllable mock that satisfies the ``AIProvider`` protocol."""

    def __init__(
        self,
        provider_name: str,
        *,
        generate_result: str = "",
        generate_error: type[Exception] | None = None,
        available: bool = True,
    ) -> None:
        self.provider_name = provider_name
        self._generate_result = generate_result
        self._generate_error = generate_error
        self._available = available

    def generate(self, prompt: str) -> str:
        if self._generate_error is not None:
            raise self._generate_error
        return self._generate_result or f"{self.provider_name}: {prompt}"

    def check_availability(self) -> bool:
        return self._available


def _make_router(
    providers: dict[str, _MockProvider],
    config: RoutingConfig | None = None,
) -> AIRouter:
    router = AIRouter(routing_config=config)
    router.providers = providers  # type: ignore[assignment]
    return router


# ---------------------------------------------------------------------------
# Routing configuration and strategy selection
# ---------------------------------------------------------------------------


class TestRoutingConfig:

    def test_default_config(self) -> None:
        config = RoutingConfig()
        assert config.strategy is RoutingStrategy.PREFERRED
        assert "ollama" in config.providers
        assert config.offline_provider == "ollama"
        assert config.max_retries_per_provider == 3

    def test_custom_config(self) -> None:
        config = RoutingConfig(
            strategy=RoutingStrategy.OFFLINE_FIRST,
            providers=("openai", "claude"),
            offline_provider="ollama",
            disabled_providers=("claude",),
        )
        assert config.strategy is RoutingStrategy.OFFLINE_FIRST
        assert config.providers == ("openai", "claude")

    def test_strategy_values(self) -> None:
        assert RoutingStrategy.PREFERRED.name == "PREFERRED"
        assert RoutingStrategy.OFFLINE_FIRST.name == "OFFLINE_FIRST"
        assert RoutingStrategy.ONLINE_FIRST.name == "ONLINE_FIRST"
        assert RoutingStrategy.FAILOVER.name == "FAILOVER"

    def test_provider_status_values(self) -> None:
        assert ProviderStatus.AVAILABLE.name == "AVAILABLE"
        assert ProviderStatus.UNAVAILABLE.name == "UNAVAILABLE"
        assert ProviderStatus.DISABLED.name == "DISABLED"
        assert ProviderStatus.NO_CREDENTIALS.name == "NO_CREDENTIALS"


# ---------------------------------------------------------------------------
# Provider status and availability
# ---------------------------------------------------------------------------


class TestProviderStatus:

    def test_available_provider(self) -> None:
        a = _MockProvider("a", available=True)
        router = _make_router({"a": a})
        assert router.provider_status("a") is ProviderStatus.AVAILABLE

    def test_unavailable_provider_not_registered(self) -> None:
        router = _make_router({})
        assert router.provider_status("nonexistent") is ProviderStatus.UNAVAILABLE

    def test_missing_credentials(self) -> None:
        a = _MockProvider("a", available=False)
        router = _make_router({"a": a})
        assert router.provider_status("a") is ProviderStatus.NO_CREDENTIALS

    def test_disabled_provider(self) -> None:
        a = _MockProvider("a", available=True)
        router = _make_router(
            {"a": a},
            RoutingConfig(disabled_providers=("a",)),
        )
        assert router.provider_status("a") is ProviderStatus.DISABLED

    def test_available_providers_list(self) -> None:
        a = _MockProvider("a", available=True)
        b = _MockProvider("b", available=False)
        c = _MockProvider("c", available=True)
        router = _make_router({"a": a, "b": b, "c": c})
        assert router.available_providers == ["a", "c"]

    def test_available_providers_empty(self) -> None:
        router = _make_router({})
        assert router.available_providers == []


# ---------------------------------------------------------------------------
# Provider order resolution per strategy
# ---------------------------------------------------------------------------


class TestProviderOrderResolution:

    def test_preferred_uses_config_order(self) -> None:
        a = _MockProvider("a")
        b = _MockProvider("b")
        c = _MockProvider("c")
        router = _make_router(
            {"a": a, "b": b, "c": c},
            RoutingConfig(
                strategy=RoutingStrategy.PREFERRED,
                providers=("c", "a", "b"),
            ),
        )
        assert router._resolve_provider_order() == ["c", "a", "b"]

    def test_failover_uses_config_order(self) -> None:
        router = _make_router(
            {},
            RoutingConfig(
                strategy=RoutingStrategy.FAILOVER,
                providers=("openai", "claude"),
            ),
        )
        assert router._resolve_provider_order() == ["openai", "claude"]

    def test_offline_first(self) -> None:
        router = _make_router(
            {},
            RoutingConfig(
                strategy=RoutingStrategy.OFFLINE_FIRST,
                providers=("openai", "ollama", "claude"),
            ),
        )
        assert router._resolve_provider_order() == ["ollama", "openai", "claude"]

    def test_offline_first_no_offline_provider(self) -> None:
        router = _make_router(
            {},
            RoutingConfig(
                strategy=RoutingStrategy.OFFLINE_FIRST,
                providers=("openai", "claude"),
                offline_provider="ollama",
            ),
        )
        assert router._resolve_provider_order() == ["openai", "claude"]

    def test_online_first(self) -> None:
        router = _make_router(
            {},
            RoutingConfig(
                strategy=RoutingStrategy.ONLINE_FIRST,
                providers=("openai", "ollama", "claude"),
            ),
        )
        assert router._resolve_provider_order() == ["openai", "claude", "ollama"]

    def test_online_first_no_offline_provider(self) -> None:
        router = _make_router(
            {},
            RoutingConfig(
                strategy=RoutingStrategy.ONLINE_FIRST,
                providers=("openai", "claude"),
                offline_provider="ollama",
            ),
        )
        assert router._resolve_provider_order() == ["openai", "claude"]


# ---------------------------------------------------------------------------
# Preferred provider selection
# ---------------------------------------------------------------------------


class TestPreferredProviderRouting:

    def test_first_provider_in_order_is_used(self) -> None:
        a = _MockProvider("a", generate_result="from a")
        b = _MockProvider("b", generate_result="from b")
        router = _make_router(
            {"a": a, "b": b},
            RoutingConfig(providers=("a", "b")),
        )
        result = router.ask_routed("hello")
        assert result == "from a"

    def test_second_provider_used_when_first_is_disabled(self) -> None:
        a = _MockProvider("a", generate_result="from a")
        b = _MockProvider("b", generate_result="from b")
        router = _make_router(
            {"a": a, "b": b},
            RoutingConfig(
                providers=("a", "b"),
                disabled_providers=("a",),
            ),
        )
        result = router.ask_routed("hello")
        assert result == "from b"

    def test_provider_without_credentials_is_skipped(self) -> None:
        a = _MockProvider("a", generate_result="from a", available=False)
        b = _MockProvider("b", generate_result="from b")
        router = _make_router(
            {"a": a, "b": b},
            RoutingConfig(providers=("a", "b")),
        )
        result = router.ask_routed("hello")
        assert result == "from b"

    def test_unregistered_provider_in_config_is_skipped(self) -> None:
        a = _MockProvider("a", generate_result="from a")
        router = _make_router(
            {"a": a},
            RoutingConfig(providers=("nonexistent", "a")),
        )
        result = router.ask_routed("hello")
        assert result == "from a"


# ---------------------------------------------------------------------------
# Automatic fallback
# ---------------------------------------------------------------------------


class TestAutomaticFallback:

    def test_fallback_on_provider_error(self) -> None:
        a = _MockProvider("a", generate_error=ProviderTimeoutError("timeout"))
        b = _MockProvider("b", generate_result="from b")
        router = _make_router(
            {"a": a, "b": b},
            RoutingConfig(providers=("a", "b")),
        )
        result = router.ask_routed("hello")
        assert result == "from b"

    def test_fallback_preserves_prompt(self) -> None:
        a = _MockProvider("a", generate_error=ProviderTimeoutError("timeout"))
        b = _MockProvider("b")
        router = _make_router(
            {"a": a, "b": b},
            RoutingConfig(providers=("a", "b")),
        )
        result = router.ask_routed("preserve-me")
        assert "preserve-me" in result

    def test_fallback_skips_disabled_providers(self) -> None:
        a = _MockProvider("a", generate_error=ProviderTimeoutError("timeout"))
        b = _MockProvider("b", generate_result="from b", available=False)
        c = _MockProvider("c", generate_result="from c")
        router = _make_router(
            {"a": a, "b": b, "c": c},
            RoutingConfig(providers=("a", "b", "c")),
        )
        result = router.ask_routed("hello")
        assert result == "from c"

    def test_all_providers_fail_raises_aggregated_error(self) -> None:
        a = _MockProvider("a", generate_error=ProviderTimeoutError("a failed"))
        b = _MockProvider("b", generate_error=ProviderTimeoutError("b failed"))
        router = _make_router(
            {"a": a, "b": b},
            RoutingConfig(providers=("a", "b")),
        )
        with pytest.raises(AllProvidersFailedError) as exc_info:
            router.ask_routed("hello")
        assert "a" in exc_info.value.failures
        assert "b" in exc_info.value.failures

    def test_no_providers_configured_raises_value_error(self) -> None:
        router = _make_router({}, RoutingConfig(providers=()))
        with pytest.raises(ValueError, match="No providers"):
            router.ask_routed("hello")


# ---------------------------------------------------------------------------
# Offline-first routing (Ollama preference)
# ---------------------------------------------------------------------------


class TestOfflineFirstRouting:

    def test_offline_first_prefers_ollama(self) -> None:
        ollama = _MockProvider("ollama", generate_result="from ollama")
        openai = _MockProvider("openai", generate_result="from openai")
        router = _make_router(
            {"ollama": ollama, "openai": openai},
            RoutingConfig(
                strategy=RoutingStrategy.OFFLINE_FIRST,
                providers=("openai", "ollama"),
            ),
        )
        result = router.ask_routed("hello")
        assert result == "from ollama"

    def test_offline_first_falls_back_to_online_when_offline_unavailable(self) -> None:
        ollama = _MockProvider("ollama", available=False)
        openai = _MockProvider("openai", generate_result="from openai")
        router = _make_router(
            {"ollama": ollama, "openai": openai},
            RoutingConfig(
                strategy=RoutingStrategy.OFFLINE_FIRST,
                providers=("openai", "ollama"),
            ),
        )
        result = router.ask_routed("hello")
        assert result == "from openai"

    def test_offline_first_falls_back_on_error(self) -> None:
        ollama = _MockProvider(
            "ollama", generate_error=ProviderTimeoutError("ollama down")
        )
        openai = _MockProvider("openai", generate_result="from openai")
        router = _make_router(
            {"ollama": ollama, "openai": openai},
            RoutingConfig(
                strategy=RoutingStrategy.OFFLINE_FIRST,
                providers=("openai", "ollama"),
            ),
        )
        result = router.ask_routed("hello")
        assert result == "from openai"

    def test_online_first_prefers_online(self) -> None:
        ollama = _MockProvider("ollama", generate_result="from ollama")
        openai = _MockProvider("openai", generate_result="from openai")
        router = _make_router(
            {"ollama": ollama, "openai": openai},
            RoutingConfig(
                strategy=RoutingStrategy.ONLINE_FIRST,
                providers=("openai", "ollama"),
            ),
        )
        result = router.ask_routed("hello")
        assert result == "from openai"


# ---------------------------------------------------------------------------
# Retry followed by fallback
# ---------------------------------------------------------------------------


class TestRetryThenFallback:

    def test_retry_exhausted_then_fallback(self) -> None:
        a = _MockProvider(
            "a", generate_error=ProviderTimeoutError("always timeout")
        )
        b = _MockProvider("b", generate_result="from b")
        router = _make_router(
            {"a": a, "b": b},
            RoutingConfig(providers=("a", "b")),
        )
        result = router.ask_routed("hello")
        assert result == "from b"

    def test_first_successful_response_returned(self) -> None:
        a = _MockProvider("a", generate_result="from a")
        b = _MockProvider("b", generate_result="from b")
        router = _make_router(
            {"a": a, "b": b},
            RoutingConfig(providers=("a", "b")),
        )
        result = router.ask_routed("hello")
        assert result == "from a"

    def test_non_ai_provider_error_propagates(self) -> None:
        a = _MockProvider("a", generate_error=ValueError("unexpected"))
        b = _MockProvider("b", generate_result="from b")
        router = _make_router(
            {"a": a, "b": b},
            RoutingConfig(providers=("a", "b")),
        )
        with pytest.raises(ValueError, match="unexpected"):
            router.ask_routed("hello")


# ---------------------------------------------------------------------------
# Integration: router with real discovered providers (mocked SDK)
# ---------------------------------------------------------------------------


class TestRoutingIntegration:

    def test_ask_routed_returns_ai_response_with_reality_check(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Verify that ``ask_routed`` works with the full discovery path
        when all providers have credentials and mocked SDKs."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        monkeypatch.setenv("GEMINI_API_KEY", "sk-test")
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
        with (
            patch("app.ai.providers.openai.OpenAI") as mock_openai_cls,
            patch("app.ai.providers.claude.Anthropic") as mock_anthropic_cls,
            patch("app.ai.providers.gemini.GenerativeModel") as mock_gemini_cls,
            patch("app.ai.providers.deepseek.OpenAI") as mock_deepseek_cls,
        ):
            mock_openai = MagicMock()
            mock_openai.chat.completions.create.return_value = MagicMock(
                choices=[MagicMock(message=MagicMock(content="from openai"))],
                usage=None,
            )
            mock_openai_cls.return_value = mock_openai

            mock_anthropic = MagicMock()
            mock_anthropic.messages.create.return_value = MagicMock(
                content=[MagicMock(text="from claude")],
                usage=None,
            )
            mock_anthropic_cls.return_value = mock_anthropic

            mock_gemini = MagicMock()
            mock_gemini.generate_content.return_value = MagicMock(
                text="from gemini",
                usage_metadata=None,
            )
            mock_gemini_cls.return_value = mock_gemini

            mock_deepseek = MagicMock()
            mock_deepseek.chat.completions.create.return_value = MagicMock(
                choices=[MagicMock(message=MagicMock(content="from deepseek"))],
                usage=None,
            )
            mock_deepseek_cls.return_value = mock_deepseek

            router = AIRouter(
                routing_config=RoutingConfig(
                    strategy=RoutingStrategy.PREFERRED,
                    providers=("openai", "claude", "gemini", "deepseek"),
                ),
            )

            result = router.ask_routed("hello")
            assert isinstance(result, str)
            assert result == "from openai"
            assert mock_openai.chat.completions.create.called

    def test_ask_routed_falls_back_across_real_providers(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When the first provider fails, the router falls back to the
        next available provider in the configured order."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        with (
            patch("app.ai.providers.openai.OpenAI") as mock_openai_cls,
            patch("app.ai.providers.claude.Anthropic") as mock_anthropic_cls,
        ):
            mock_openai = MagicMock()
            mock_openai.chat.completions.create.side_effect = Exception("timeout")
            mock_openai_cls.return_value = mock_openai

            mock_anthropic = MagicMock()
            mock_anthropic.messages.create.return_value = MagicMock(
                content=[MagicMock(text="from claude")],
                usage=None,
            )
            mock_anthropic_cls.return_value = mock_anthropic

            router = AIRouter(
                routing_config=RoutingConfig(
                    strategy=RoutingStrategy.PREFERRED,
                    providers=("openai", "claude"),
                ),
            )

            result = router.ask_routed("hello")
            assert result == "from claude"

    def test_ask_routed_non_provider_error_still_propagates(
        self,
    ) -> None:
        """Errors raised outside the provider SDK (e.g. missing API key
        for a provider that requires one) cause the provider to be
        skipped as unavailable rather than triggering a fallback
        retry."""
        router = AIRouter(
            routing_config=RoutingConfig(
                strategy=RoutingStrategy.PREFERRED,
                providers=("openai", "claude"),
            ),
        )
        # No env vars are set, so all cloud providers are
        # ``NO_CREDENTIALS`` and the router raises
        # ``AllProvidersFailedError``.
        with pytest.raises(AllProvidersFailedError):
            router.ask_routed("hello")

    def test_ask_routed_propagates_unknown_provider(self) -> None:
        """Calling ``ask`` with an unregistered name still raises
        ``ValueError``."""
        router = AIRouter()
        with pytest.raises(ValueError, match="Unknown provider"):
            router.ask("does_not_exist", "hello")
