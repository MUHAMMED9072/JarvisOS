# tests/test_ai_providers.py
"""
Tests for the production-ready AI provider classes added in P2-13.

Covers, for every concrete provider shipped under ``app/ai/providers/``:

* ``AIProvider`` protocol satisfaction.
* ``provider_name`` is a non-empty string and matches the
  registration key used by ``AIRouter``.
* Constructor validates configuration eagerly (type and value checks
  on every provided argument).
* Constructor with no arguments does not raise, so ``AIRouter`` can
  instantiate the provider during discovery.
* ``generate(prompt)`` raises a ``TypeError`` on a non-string prompt.
* ``generate(prompt)`` without a configured API key raises
  ``ProviderNotConfiguredError``.
* ``generate(prompt)`` with a configured API key raises
  ``ProviderNotImplementedError`` (real SDK integration pending).
* Custom exception hierarchy: both subclasses derive from
  ``AIProviderError`` and ``Exception``.
* ``AIRouter`` discovers all five real providers and registers them
  under their ``provider_name`` keys.
* The ``OllamaProvider`` preserves its legacy
  ``generate(prompt, model=...)`` call signature.
"""

from __future__ import annotations

import os
from typing import Type
from unittest.mock import MagicMock, patch

import pytest

from app.ai.providers.claude import AnthropicProvider
from app.ai.providers.base import (
    AIProvider,
    AIProviderError,
    AIResponse,
    ProviderCapability,
    ProviderMetadata,
    ProviderNotConfiguredError,
    ProviderNotImplementedError,
    ProviderTimeoutError,
    ProviderRateLimitError,
    ProviderConnectionError,
    ProviderAPIAuthorizationError,
    ProviderUnexpectedError,
    map_exception,
    retry_with_backoff,
    validate_api_key,
    validate_optional_str,
    validate_str,
    validate_timeout,
)
from app.ai.providers.deepseek import DeepSeekProvider
from app.ai.providers.gemini import GeminiProvider
from app.ai.providers.ollama import OllamaProvider
from app.ai.providers.openai import OpenAIProvider
from app.ai.router import AIRouter


# ---------------------------------------------------------------------------
# Provider registry used throughout this test module.
# ---------------------------------------------------------------------------
#
# Each entry is ``(provider_class, expected_provider_name)``.  The
# AnthropicProvider is special: it lives in ``claude.py`` for
# backward compatibility but is the class the tests assert on.
# ---------------------------------------------------------------------------

CLOUD_PROVIDER_CLASSES: list[tuple[Type[AIProvider], str]] = [
    (OpenAIProvider, "openai"),
    (AnthropicProvider, "claude"),
    (GeminiProvider, "gemini"),
    (DeepSeekProvider, "deepseek"),
]

ALL_PROVIDER_CLASSES: list[tuple[Type[AIProvider], str]] = [
    (OllamaProvider, "ollama"),
    *CLOUD_PROVIDER_CLASSES,
]


# ---------------------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------------------


class TestAIProviderExceptions:
    def test_ai_provider_error_is_exception(self) -> None:
        assert issubclass(AIProviderError, Exception)

    def test_provider_not_configured_is_ai_provider_error(self) -> None:
        assert issubclass(ProviderNotConfiguredError, AIProviderError)
        assert issubclass(ProviderNotConfiguredError, Exception)

    def test_provider_not_implemented_is_ai_provider_error(self) -> None:
        assert issubclass(ProviderNotImplementedError, AIProviderError)
        assert issubclass(ProviderNotImplementedError, Exception)

    def test_exceptions_are_catchable_individually(self) -> None:
        """Each subclass is a distinct catchable type."""
        try:
            raise ProviderNotConfiguredError("a")
        except ProviderNotImplementedError:
            pytest.fail(
                "ProviderNotConfiguredError should not be caught as "
                "ProviderNotImplementedError"
            )
        except ProviderNotConfiguredError:
            pass

        try:
            raise ProviderNotImplementedError("b")
        except ProviderNotConfiguredError:
            pytest.fail(
                "ProviderNotImplementedError should not be caught as "
                "ProviderNotConfiguredError"
            )
        except ProviderNotImplementedError:
            pass

    def test_ai_provider_error_catches_both_subclasses(self) -> None:
        for exc_cls in (
            ProviderNotConfiguredError,
            ProviderNotImplementedError,
        ):
            try:
                raise exc_cls("x")
            except AIProviderError:
                pass


# ---------------------------------------------------------------------------
# Protocol satisfaction + provider_name
# ---------------------------------------------------------------------------


class TestAIProviderProtocol:
    @pytest.mark.parametrize(
        "provider_cls,expected_name",
        ALL_PROVIDER_CLASSES,
        ids=[cls.__name__ for cls, _ in ALL_PROVIDER_CLASSES],
    )
    def test_class_satisfies_protocol(
        self, provider_cls: Type[AIProvider], expected_name: str
    ) -> None:
        assert issubclass(provider_cls, AIProvider)
        # ``isinstance`` against the runtime-checkable Protocol works
        # on instances too.
        instance = provider_cls()
        assert isinstance(instance, AIProvider)

    @pytest.mark.parametrize(
        "provider_cls,expected_name",
        ALL_PROVIDER_CLASSES,
        ids=[cls.__name__ for cls, _ in ALL_PROVIDER_CLASSES],
    )
    def test_provider_name(
        self, provider_cls: Type[AIProvider], expected_name: str
    ) -> None:
        assert hasattr(provider_cls, "provider_name")
        assert isinstance(provider_cls.provider_name, str)
        assert provider_cls.provider_name == expected_name
        assert provider_cls.provider_name != ""

    def test_class_attribute_not_instance_attribute(self) -> None:
        """``provider_name`` must be declared on the class, not set in
        ``__init__`` - the router inspects the *class* during
        discovery before instantiation."""
        for provider_cls, _ in ALL_PROVIDER_CLASSES:
            assert "provider_name" in vars(provider_cls), (
                f"{provider_cls.__name__} must declare provider_name as "
                f"a class attribute, not via __init__"
            )

    def test_all_provider_names_are_unique(self) -> None:
        names = [name for _, name in ALL_PROVIDER_CLASSES]
        assert len(names) == len(set(names)), (
            f"Duplicate provider_name values: {names}"
        )


# ---------------------------------------------------------------------------
# Constructor validation
# ---------------------------------------------------------------------------


class TestOllamaProviderConstruction:
    def test_construct_with_no_arguments(self) -> None:
        provider = OllamaProvider()
        assert provider._base_url == "http://localhost:11434"
        assert provider._model == "qwen2.5-coder"
        assert provider._timeout == 30.0

    def test_construct_with_overrides(self) -> None:
        provider = OllamaProvider(
            base_url="http://example.test:1234",
            model="llama3.1",
            timeout=5.0,
        )
        assert provider._base_url == "http://example.test:1234"
        assert provider._model == "llama3.1"
        assert provider._timeout == 5.0

    def test_construct_rejects_non_positive_timeout(self) -> None:
        with pytest.raises(ProviderNotConfiguredError):
            OllamaProvider(timeout=0)
        with pytest.raises(ProviderNotConfiguredError):
            OllamaProvider(timeout=-1.0)

    def test_construct_rejects_non_numeric_timeout(self) -> None:
        with pytest.raises(ProviderNotConfiguredError):
            OllamaProvider(timeout="30")  # type: ignore[arg-type]
        with pytest.raises(ProviderNotConfiguredError):
            OllamaProvider(timeout=None)  # type: ignore[arg-type]

    def test_construct_rejects_bool_timeout(self) -> None:
        # ``bool`` is a subclass of ``int`` in Python; the validator
        # must reject it explicitly.
        with pytest.raises(ProviderNotConfiguredError):
            OllamaProvider(timeout=True)  # type: ignore[arg-type]

    def test_construct_rejects_empty_base_url(self) -> None:
        with pytest.raises(ProviderNotConfiguredError):
            OllamaProvider(base_url="")
        with pytest.raises(ProviderNotConfiguredError):
            OllamaProvider(base_url="   ")

    def test_construct_rejects_empty_model(self) -> None:
        with pytest.raises(ProviderNotConfiguredError):
            OllamaProvider(model="")


class _CloudProviderConstruction:
    """Shared cases for the four cloud provider classes."""

    provider_cls: Type[AIProvider] = NotImplemented  # set in subclasses
    env_var: str = NotImplemented

    def test_construct_with_no_arguments_does_not_raise(self) -> None:
        # Lazy API-key resolution: missing key is permitted at
        # construction time so the router can register the provider.
        provider = self.provider_cls()
        # The default base_url / model are populated even without
        # an API key.
        assert isinstance(provider._base_url, str)
        assert provider._base_url
        assert isinstance(provider._model, str)
        assert provider._model
        assert provider._timeout == 30.0

    def test_construct_with_explicit_api_key(self) -> None:
        provider = self.provider_cls(api_key="sk-test-key")
        assert provider._api_key == "sk-test-key"

    def test_construct_with_overrides(self) -> None:
        provider = self.provider_cls(
            api_key="sk-test",
            base_url="https://override.test/v1",
            model="override-model",
            timeout=12.5,
        )
        assert provider._api_key == "sk-test"
        assert provider._base_url == "https://override.test/v1"
        assert provider._model == "override-model"
        assert provider._timeout == 12.5

    def test_construct_rejects_empty_api_key(self) -> None:
        with pytest.raises(ProviderNotConfiguredError):
            self.provider_cls(api_key="")

    def test_construct_rejects_whitespace_api_key(self) -> None:
        with pytest.raises(ProviderNotConfiguredError):
            self.provider_cls(api_key="   ")

    def test_construct_rejects_non_string_api_key(self) -> None:
        with pytest.raises(ProviderNotConfiguredError):
            self.provider_cls(api_key=123)  # type: ignore[arg-type]

    def test_construct_rejects_non_positive_timeout(self) -> None:
        with pytest.raises(ProviderNotConfiguredError):
            self.provider_cls(api_key="k", timeout=0)
        with pytest.raises(ProviderNotConfiguredError):
            self.provider_cls(api_key="k", timeout=-3)

    def test_construct_rejects_bool_timeout(self) -> None:
        with pytest.raises(ProviderNotConfiguredError):
            self.provider_cls(api_key="k", timeout=True)  # type: ignore[arg-type]

    def test_construct_rejects_empty_base_url(self) -> None:
        with pytest.raises(ProviderNotConfiguredError):
            self.provider_cls(api_key="k", base_url="")

    def test_construct_rejects_empty_model(self) -> None:
        with pytest.raises(ProviderNotConfiguredError):
            self.provider_cls(api_key="k", model="")

    def test_generate_without_api_key_raises_not_configured(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv(self.env_var, raising=False)
        provider = self.provider_cls()
        with pytest.raises(ProviderNotConfiguredError):
            provider.generate("hello")

    def test_generate_with_explicit_api_key_raises_not_implemented(self) -> None:
        provider = self.provider_cls(api_key="sk-test")
        with pytest.raises(ProviderNotImplementedError):
            provider.generate("hello")

    def test_generate_with_env_api_key_raises_not_implemented(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(self.env_var, "sk-from-env")
        provider = self.provider_cls()
        with pytest.raises(ProviderNotImplementedError):
            provider.generate("hello")

    def test_generate_rejects_non_string_prompt(self) -> None:
        provider = self.provider_cls(api_key="sk-test")
        with pytest.raises(TypeError):
            provider.generate(123)  # type: ignore[arg-type]
        with pytest.raises(TypeError):
            provider.generate(None)  # type: ignore[arg-type]


class TestOpenAIProviderConstruction(_CloudProviderConstruction):
    provider_cls = OpenAIProvider
    env_var = "OPENAI_API_KEY"

    @staticmethod
    def _mock_openai_sdk(content: str = "test") -> MagicMock:
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content=content))]
        mock_response.usage = None
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        patcher = patch("app.ai.providers.openai.OpenAI", return_value=mock_client)
        patcher.start()
        return mock_client

    def test_generate_with_explicit_api_key_raises_not_implemented(self) -> None:
        self._mock_openai_sdk()
        try:
            provider = self.provider_cls(api_key="sk-test")
            result = provider.generate("hello")
            assert isinstance(result, AIResponse)
            assert result.provider == "openai"
            assert result == "test"
        finally:
            patch.stopall()

    def test_generate_with_env_api_key_raises_not_implemented(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(self.env_var, "sk-from-env")
        self._mock_openai_sdk()
        try:
            provider = self.provider_cls()
            result = provider.generate("hello")
            assert isinstance(result, AIResponse)
            assert result.provider == "openai"
        finally:
            patch.stopall()


class TestAnthropicProviderConstruction(_CloudProviderConstruction):
    provider_cls = AnthropicProvider
    env_var = "ANTHROPIC_API_KEY"

    @staticmethod
    def _mock_anthropic_sdk(content: str = "test") -> MagicMock:
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=content)]
        mock_response.usage = None
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        patcher = patch("app.ai.providers.claude.Anthropic", return_value=mock_client)
        patcher.start()
        return mock_client

    def test_generate_with_explicit_api_key_raises_not_implemented(self) -> None:
        self._mock_anthropic_sdk()
        try:
            provider = self.provider_cls(api_key="sk-test")
            result = provider.generate("hello")
            assert isinstance(result, AIResponse)
            assert result.provider == "claude"
            assert result == "test"
        finally:
            patch.stopall()

    def test_generate_with_env_api_key_raises_not_implemented(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(self.env_var, "sk-from-env")
        self._mock_anthropic_sdk()
        try:
            provider = self.provider_cls()
            result = provider.generate("hello")
            assert isinstance(result, AIResponse)
            assert result.provider == "claude"
        finally:
            patch.stopall()

    def test_class_name_is_anthropic_for_naming_consistency(self) -> None:
        """The class is named after the upstream API, not the file."""
        assert self.provider_cls.__name__ == "AnthropicProvider"

    def test_provider_name_remains_claude_for_backward_compatibility(
        self,
    ) -> None:
        """Registration key stays ``"claude"`` so the existing
        ``AIRouter.ask("claude", ...)`` calls and the
        ``ANTHROPIC_API_KEY`` env var both keep working."""
        assert self.provider_cls.provider_name == "claude"

    def test_module_name_remains_claude_for_backward_compatibility(
        self,
    ) -> None:
        import app.ai.providers.claude as claude_module

        assert claude_module.AnthropicProvider is AnthropicProvider


class TestGeminiProviderConstruction(_CloudProviderConstruction):
    provider_cls = GeminiProvider
    env_var = "GEMINI_API_KEY"

    @staticmethod
    def _mock_gemini_sdk(text: str = "test") -> MagicMock:
        mock_response = MagicMock()
        mock_response.text = text
        mock_response.usage_metadata = None
        mock_model = MagicMock()
        mock_model.generate_content.return_value = mock_response
        patcher = patch("app.ai.providers.gemini.GenerativeModel", return_value=mock_model)
        patcher.start()
        return mock_model

    def test_generate_with_explicit_api_key_raises_not_implemented(self) -> None:
        self._mock_gemini_sdk()
        try:
            provider = self.provider_cls(api_key="sk-test")
            result = provider.generate("hello")
            assert isinstance(result, AIResponse)
            assert result.provider == "gemini"
            assert result == "test"
        finally:
            patch.stopall()

    def test_generate_with_env_api_key_raises_not_implemented(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(self.env_var, "sk-from-env")
        self._mock_gemini_sdk()
        try:
            provider = self.provider_cls()
            result = provider.generate("hello")
            assert isinstance(result, AIResponse)
            assert result.provider == "gemini"
        finally:
            patch.stopall()


class TestDeepSeekProviderConstruction(_CloudProviderConstruction):
    provider_cls = DeepSeekProvider
    env_var = "DEEPSEEK_API_KEY"

    # Override "not-implemented" tests: DeepSeek is now implemented.
    def test_generate_with_explicit_api_key_raises_not_implemented(self) -> None:
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="test"))]
        mock_response.usage = None
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        with patch("app.ai.providers.deepseek.OpenAI", return_value=mock_client):
            provider = self.provider_cls(api_key="sk-test")
            result = provider.generate("hello")
        assert isinstance(result, AIResponse)
        assert result.provider == "deepseek"
        assert result == "test"

    def test_generate_with_env_api_key_raises_not_implemented(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(self.env_var, "sk-from-env")
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="test"))]
        mock_response.usage = None
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        with patch("app.ai.providers.deepseek.OpenAI", return_value=mock_client):
            provider = self.provider_cls()
            result = provider.generate("hello")
        assert isinstance(result, AIResponse)
        assert result.provider == "deepseek"


# ---------------------------------------------------------------------------
# Ollama-specific behavior (legacy call signature, real SDK path)
# ---------------------------------------------------------------------------


class TestOllamaProviderBehavior:
    def test_generate_legacy_two_arg_signature_preserved(self) -> None:
        """Existing callers in the Evolution Engine pass ``model=`` as
        a second argument; the historical call shape must keep
        working alongside the protocol-compliant single-argument
        shape."""
        provider = OllamaProvider()
        # We do not actually call the network here; we only assert
        # the method accepts the second argument without raising
        # ``TypeError`` (the underlying SDK call would then fail if
        # the daemon is unavailable, which is a different concern).
        try:
            provider.generate("hi", model="qwen2.5-coder")
        except TypeError as exc:
            pytest.fail(
                f"OllamaProvider.generate must keep accepting "
                f"(prompt, model=...), got TypeError: {exc}"
            )
        except Exception:
            # Any non-TypeError exception (connection refused, etc.)
            # is acceptable - the daemon may not be running in CI.
            pass

    def test_generate_protocol_compliant_signature(self) -> None:
        """The signature matches the ``AIProvider`` Protocol."""
        import inspect

        sig = inspect.signature(OllamaProvider.generate)
        params = list(sig.parameters.keys())
        # ``self`` + ``prompt`` are required; everything else must
        # be keyword-only with defaults.
        assert params[0] == "self"
        assert params[1] == "prompt"
        # No required positional after ``prompt``.
        for name, param in sig.parameters.items():
            if name in {"self", "prompt"}:
                continue
            assert param.default is not inspect.Parameter.empty, (
                f"OllamaProvider.generate parameter {name!r} must have "
                f"a default value"
            )
            assert param.kind == inspect.Parameter.KEYWORD_ONLY, (
                f"OllamaProvider.generate parameter {name!r} must be "
                f"keyword-only to preserve the protocol signature"
            )

    def test_generate_rejects_non_string_prompt(self) -> None:
        provider = OllamaProvider()
        with pytest.raises(TypeError):
            provider.generate(123)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# AIRouter integration
# ---------------------------------------------------------------------------


class TestAIRouterIntegration:
    def test_router_discovers_all_five_real_providers(self) -> None:
        router = AIRouter()
        discovered_names = set(router.providers.keys())
        expected = {name for _, name in ALL_PROVIDER_CLASSES}
        assert expected.issubset(discovered_names), (
            f"Missing providers: {expected - discovered_names}"
        )

    @pytest.mark.parametrize(
        "provider_cls,expected_name",
        ALL_PROVIDER_CLASSES,
        ids=[cls.__name__ for cls, _ in ALL_PROVIDER_CLASSES],
    )
    def test_router_registers_under_provider_name(
        self,
        provider_cls: Type[AIProvider],
        expected_name: str,
    ) -> None:
        router = AIRouter()
        assert expected_name in router.providers
        assert isinstance(router.providers[expected_name], provider_cls)

    def test_router_providers_satisfy_protocol(self) -> None:
        router = AIRouter()
        for name, provider in router.providers.items():
            assert isinstance(provider, AIProvider), (
                f"Router provider {name!r} does not satisfy AIProvider"
            )

    def test_router_ask_dispatches_to_provider(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Smoke test: ``router.ask(name, prompt)`` reaches the
        provider's ``generate`` method."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        monkeypatch.setenv("GEMINI_API_KEY", "sk-test")
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")

        mock_openai_response = MagicMock()
        mock_openai_response.choices = [MagicMock(message=MagicMock(content="hello from openai"))]
        mock_openai_response.usage = None
        mock_openai_client = MagicMock()
        mock_openai_client.chat.completions.create.return_value = mock_openai_response

        mock_anthropic_response = MagicMock()
        mock_anthropic_response.content = [MagicMock(text="hello from claude")]
        mock_anthropic_response.usage = None
        mock_anthropic_client = MagicMock()
        mock_anthropic_client.messages.create.return_value = mock_anthropic_response

        mock_gemini_response = MagicMock()
        mock_gemini_response.text = "hello from gemini"
        mock_gemini_response.usage_metadata = None
        mock_gemini_model = MagicMock()
        mock_gemini_model.generate_content.return_value = mock_gemini_response

        mock_deepseek_response = MagicMock()
        mock_deepseek_response.choices = [MagicMock(message=MagicMock(content="hello from deepseek"))]
        mock_deepseek_response.usage = None
        mock_deepseek_client = MagicMock()
        mock_deepseek_client.chat.completions.create.return_value = mock_deepseek_response

        with (
            patch("app.ai.providers.openai.OpenAI", return_value=mock_openai_client),
            patch("app.ai.providers.claude.Anthropic", return_value=mock_anthropic_client),
            patch("app.ai.providers.gemini.GenerativeModel", return_value=mock_gemini_model),
            patch("app.ai.providers.deepseek.OpenAI", return_value=mock_deepseek_client),
        ):
            router = AIRouter()

            result = router.ask("openai", "hello")
            assert isinstance(result, AIResponse)
            assert result == "hello from openai"
            assert result.provider == "openai"

            result = router.ask("claude", "hello")
            assert isinstance(result, AIResponse)
            assert result == "hello from claude"
            assert result.provider == "claude"

            result = router.ask("gemini", "hello")
            assert isinstance(result, AIResponse)
            assert result == "hello from gemini"
            assert result.provider == "gemini"

            result = router.ask("deepseek", "hello")
            assert isinstance(result, AIResponse)
            assert result == "hello from deepseek"
            assert result.provider == "deepseek"

            for cls, name in CLOUD_PROVIDER_CLASSES:
                if name in ("openai", "claude", "gemini", "deepseek"):
                    continue
                with pytest.raises(ProviderNotImplementedError):
                    router.ask(name, "hello")

    def test_router_ask_unknown_provider_still_raises_value_error(
        self,
    ) -> None:
        router = AIRouter()
        with pytest.raises(ValueError):
            router.ask("does_not_exist", "hello")


# ---------------------------------------------------------------------------
# OpenAI provider generation (mocked SDK)
# ---------------------------------------------------------------------------


class TestOpenAIProviderGenerate:
    """Tests for the real OpenAI provider implementation with mocked SDK."""

    @staticmethod
    def _make_mock_success(
        content: str = "Hello, world!",
        prompt_tokens: int | None = 10,
        completion_tokens: int | None = 5,
    ) -> MagicMock:
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content=content))]
        if prompt_tokens is not None:
            mock_response.usage = MagicMock(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens or 0,
                total_tokens=(prompt_tokens or 0) + (completion_tokens or 0),
            )
        else:
            mock_response.usage = None
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        return patch("app.ai.providers.openai.OpenAI", return_value=mock_client)

    @staticmethod
    def _make_mock_error(exc_cls: type[Exception], message: str = "sdkerror") -> MagicMock:
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = exc_cls(message)
        return patch("app.ai.providers.openai.OpenAI", return_value=mock_client)

    def test_successful_completion(self) -> None:
        with self._make_mock_success(content="Hello, world!", prompt_tokens=10, completion_tokens=5):
            provider = OpenAIProvider(api_key="sk-test")
            result = provider.generate("Hello")
        assert isinstance(result, AIResponse)
        assert result == "Hello, world!"
        assert result.provider == "openai"
        assert result.model == "gpt-4o-mini"
        assert result.latency_ms > 0
        assert result.metadata["prompt_tokens"] == 10
        assert result.metadata["completion_tokens"] == 5
        assert result.metadata["total_tokens"] == 15

    def test_successful_completion_without_usage(self) -> None:
        with self._make_mock_success(content="No usage", prompt_tokens=None):
            provider = OpenAIProvider(api_key="sk-test")
            result = provider.generate("Hello")
        assert isinstance(result, AIResponse)
        assert result == "No usage"
        assert result.metadata == {}

    def test_empty_content(self) -> None:
        with self._make_mock_success(content="", prompt_tokens=1, completion_tokens=0):
            provider = OpenAIProvider(api_key="sk-test")
            result = provider.generate("Hello")
        assert isinstance(result, AIResponse)
        assert result == ""

    def test_none_content(self) -> None:
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content=None))]
        mock_response.usage = None
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        with patch("app.ai.providers.openai.OpenAI", return_value=mock_client):
            provider = OpenAIProvider(api_key="sk-test")
            result = provider.generate("Hello")
        assert isinstance(result, AIResponse)
        assert result == ""

    def test_api_key_missing(self) -> None:
        provider = OpenAIProvider()
        with pytest.raises(ProviderNotConfiguredError):
            provider.generate("hello")

    def test_timeout(self) -> None:
        with self._make_mock_error(Exception, "timeout exceeded"):
            provider = OpenAIProvider(api_key="sk-test")
            with pytest.raises(ProviderTimeoutError):
                provider.generate("hello")

    def test_rate_limit(self) -> None:
        with self._make_mock_error(Exception, "429 Too Many Requests"):
            provider = OpenAIProvider(api_key="sk-test")
            with pytest.raises(ProviderRateLimitError):
                provider.generate("hello")

    def test_authentication_error(self) -> None:
        with self._make_mock_error(Exception, "401 Invalid API key"):
            provider = OpenAIProvider(api_key="sk-test")
            with pytest.raises(ProviderAPIAuthorizationError):
                provider.generate("hello")

    def test_connection_error(self) -> None:
        with self._make_mock_error(Exception, "connection refused"):
            provider = OpenAIProvider(api_key="sk-test")
            with pytest.raises(ProviderConnectionError):
                provider.generate("hello")

    def test_unexpected_error(self) -> None:
        with self._make_mock_error(Exception, "internal server error"):
            provider = OpenAIProvider(api_key="sk-test")
            with pytest.raises(ProviderUnexpectedError):
                provider.generate("hello")

    def test_retry_on_transient_error_then_succeeds(self) -> None:
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="recovered"))]
        mock_response.usage = None
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            TimeoutError("first timeout"),
            TimeoutError("second timeout"),
            mock_response,
        ]
        with patch("app.ai.providers.openai.OpenAI", return_value=mock_client):
            provider = OpenAIProvider(api_key="sk-test")
            result = provider.generate("hello")
        assert isinstance(result, AIResponse)
        assert result == "recovered"

    def test_retry_exhausted_raises_last_error(self) -> None:
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = TimeoutError("always timeout")
        with patch("app.ai.providers.openai.OpenAI", return_value=mock_client):
            provider = OpenAIProvider(api_key="sk-test")
            with pytest.raises(ProviderTimeoutError):
                provider.generate("hello")

    def test_non_retryable_error_propagates_immediately(self) -> None:
        with self._make_mock_error(Exception, "403 Forbidden"):
            provider = OpenAIProvider(api_key="sk-test")
            with pytest.raises(ProviderAPIAuthorizationError):
                provider.generate("hello")

    def test_provider_info(self) -> None:
        provider = OpenAIProvider(api_key="sk-test")
        info = provider.provider_info()
        assert isinstance(info, ProviderMetadata)
        assert info.name == "openai"
        assert info.model == "gpt-4o-mini"
        assert info.base_url == "https://api.openai.com/v1"
        assert info.timeout == 30.0
        assert ProviderCapability.STREAMING in info.capabilities
        assert ProviderCapability.FUNCTION_CALLING in info.capabilities
        assert ProviderCapability.JSON_OUTPUT in info.capabilities

    def test_capabilities_class_attribute(self) -> None:
        assert hasattr(OpenAIProvider, "capabilities")
        assert isinstance(OpenAIProvider.capabilities, frozenset)
        assert ProviderCapability.STREAMING in OpenAIProvider.capabilities
        assert ProviderCapability.FUNCTION_CALLING in OpenAIProvider.capabilities
        assert ProviderCapability.EMBEDDINGS in OpenAIProvider.capabilities
        assert ProviderCapability.IMAGE_INPUT in OpenAIProvider.capabilities
        assert ProviderCapability.JSON_OUTPUT in OpenAIProvider.capabilities

    def test_temperature_and_max_tokens_default_not_sent(self) -> None:
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="ok"))]
        mock_response.usage = None
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        with patch("app.ai.providers.openai.OpenAI", return_value=mock_client):
            provider = OpenAIProvider(api_key="sk-test")
            provider.generate("hi")
        _call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert "temperature" not in _call_kwargs
        assert "max_tokens" not in _call_kwargs

    def test_temperature_and_max_tokens_sent_when_set(self) -> None:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="ok"))]
        mock_response.usage = None
        mock_client.chat.completions.create.return_value = mock_response
        with patch("app.ai.providers.openai.OpenAI", return_value=mock_client):
            provider = OpenAIProvider(api_key="sk-test", temperature=0.5, max_tokens=512)
            provider.generate("hi")
        kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert kwargs["temperature"] == 0.5
        assert kwargs["max_tokens"] == 512

    def test_system_prompt_not_sent_when_not_set(self) -> None:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="ok"))]
        mock_response.usage = None
        mock_client.chat.completions.create.return_value = mock_response
        with patch("app.ai.providers.openai.OpenAI", return_value=mock_client):
            provider = OpenAIProvider(api_key="sk-test")
            provider.generate("hi")
        messages = mock_client.chat.completions.create.call_args.kwargs["messages"]
        assert len(messages) == 1
        assert messages[0]["role"] == "user"

    def test_system_prompt_included_when_set(self) -> None:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="ok"))]
        mock_response.usage = None
        mock_client.chat.completions.create.return_value = mock_response
        with patch("app.ai.providers.openai.OpenAI", return_value=mock_client):
            provider = OpenAIProvider(
                api_key="sk-test",
                system_prompt="You are a helpful assistant.",
            )
            provider.generate("hi")
        messages = mock_client.chat.completions.create.call_args.kwargs["messages"]
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == "You are a helpful assistant."
        assert messages[1]["role"] == "user"


# ---------------------------------------------------------------------------
# Anthropic / Claude provider generation (mocked SDK)
# ---------------------------------------------------------------------------


class TestAnthropicProviderGenerate:
    """Tests for the real Anthropic provider implementation with mocked SDK."""

    @staticmethod
    def _make_mock_success(
        text: str = "Hello from Claude!",
        input_tokens: int | None = 8,
        output_tokens: int | None = 4,
    ) -> MagicMock:
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=text)]
        if input_tokens is not None:
            mock_response.usage = MagicMock(
                input_tokens=input_tokens,
                output_tokens=output_tokens or 0,
            )
        else:
            mock_response.usage = None
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        return patch("app.ai.providers.claude.Anthropic", return_value=mock_client)

    @staticmethod
    def _make_mock_error(exc_cls: type[Exception], message: str = "sdkerror") -> MagicMock:
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = exc_cls(message)
        return patch("app.ai.providers.claude.Anthropic", return_value=mock_client)

    def test_successful_completion(self) -> None:
        with self._make_mock_success(text="Hello!", input_tokens=8, output_tokens=4):
            provider = AnthropicProvider(api_key="sk-test")
            result = provider.generate("Hi")
        assert isinstance(result, AIResponse)
        assert result == "Hello!"
        assert result.provider == "claude"
        assert result.model == "claude-3-5-sonnet-latest"
        assert result.latency_ms > 0
        assert result.metadata["input_tokens"] == 8
        assert result.metadata["output_tokens"] == 4

    def test_successful_completion_without_usage(self) -> None:
        with self._make_mock_success(text="No usage", input_tokens=None):
            provider = AnthropicProvider(api_key="sk-test")
            result = provider.generate("Hi")
        assert isinstance(result, AIResponse)
        assert result == "No usage"
        assert result.metadata == {}

    def test_api_key_missing(self) -> None:
        provider = AnthropicProvider()
        with pytest.raises(ProviderNotConfiguredError):
            provider.generate("hello")

    def test_timeout(self) -> None:
        with self._make_mock_error(Exception, "timeout exceeded"):
            provider = AnthropicProvider(api_key="sk-test")
            with pytest.raises(ProviderTimeoutError):
                provider.generate("hello")

    def test_rate_limit(self) -> None:
        with self._make_mock_error(Exception, "429 Too Many Requests"):
            provider = AnthropicProvider(api_key="sk-test")
            with pytest.raises(ProviderRateLimitError):
                provider.generate("hello")

    def test_authentication_error(self) -> None:
        with self._make_mock_error(Exception, "401 Invalid API key"):
            provider = AnthropicProvider(api_key="sk-test")
            with pytest.raises(ProviderAPIAuthorizationError):
                provider.generate("hello")

    def test_connection_error(self) -> None:
        with self._make_mock_error(Exception, "connection refused"):
            provider = AnthropicProvider(api_key="sk-test")
            with pytest.raises(ProviderConnectionError):
                provider.generate("hello")

    def test_unexpected_error(self) -> None:
        with self._make_mock_error(Exception, "internal server error"):
            provider = AnthropicProvider(api_key="sk-test")
            with pytest.raises(ProviderUnexpectedError):
                provider.generate("hello")

    def test_retry_on_transient_error_then_succeeds(self) -> None:
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="recovered")]
        mock_response.usage = None
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = [
            Exception("timeout one"),
            Exception("timeout two"),
            mock_response,
        ]
        with patch("app.ai.providers.claude.Anthropic", return_value=mock_client):
            provider = AnthropicProvider(api_key="sk-test")
            result = provider.generate("hello")
        assert isinstance(result, AIResponse)
        assert result == "recovered"

    def test_retry_exhausted_raises_last_error(self) -> None:
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = Exception("timeout always")
        with patch("app.ai.providers.claude.Anthropic", return_value=mock_client):
            provider = AnthropicProvider(api_key="sk-test")
            with pytest.raises(ProviderTimeoutError):
                provider.generate("hello")

    def test_non_retryable_error_propagates_immediately(self) -> None:
        with self._make_mock_error(Exception, "403 Forbidden"):
            provider = AnthropicProvider(api_key="sk-test")
            with pytest.raises(ProviderAPIAuthorizationError):
                provider.generate("hello")

    def test_provider_info(self) -> None:
        provider = AnthropicProvider(api_key="sk-test")
        info = provider.provider_info()
        assert isinstance(info, ProviderMetadata)
        assert info.name == "claude"
        assert info.model == "claude-3-5-sonnet-latest"
        assert info.base_url == "https://api.anthropic.com"
        assert info.timeout == 30.0
        assert ProviderCapability.STREAMING in info.capabilities
        assert ProviderCapability.FUNCTION_CALLING in info.capabilities
        assert ProviderCapability.IMAGE_INPUT in info.capabilities
        assert ProviderCapability.JSON_OUTPUT in info.capabilities
        assert ProviderCapability.EMBEDDINGS not in info.capabilities

    def test_capabilities_class_attribute(self) -> None:
        assert hasattr(AnthropicProvider, "capabilities")
        assert isinstance(AnthropicProvider.capabilities, frozenset)
        assert ProviderCapability.STREAMING in AnthropicProvider.capabilities
        assert ProviderCapability.FUNCTION_CALLING in AnthropicProvider.capabilities
        assert ProviderCapability.IMAGE_INPUT in AnthropicProvider.capabilities
        assert ProviderCapability.JSON_OUTPUT in AnthropicProvider.capabilities
        assert ProviderCapability.EMBEDDINGS not in AnthropicProvider.capabilities

    def test_temperature_not_sent_when_not_set(self) -> None:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="ok")]
        mock_response.usage = None
        mock_client.messages.create.return_value = mock_response
        with patch("app.ai.providers.claude.Anthropic", return_value=mock_client):
            provider = AnthropicProvider(api_key="sk-test")
            provider.generate("hi")
        kwargs = mock_client.messages.create.call_args.kwargs
        assert "temperature" not in kwargs

    def test_temperature_sent_when_set(self) -> None:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="ok")]
        mock_response.usage = None
        mock_client.messages.create.return_value = mock_response
        with patch("app.ai.providers.claude.Anthropic", return_value=mock_client):
            provider = AnthropicProvider(api_key="sk-test", temperature=0.3)
            provider.generate("hi")
        kwargs = mock_client.messages.create.call_args.kwargs
        assert kwargs["temperature"] == 0.3

    def test_system_prompt_sent_when_set(self) -> None:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="ok")]
        mock_response.usage = None
        mock_client.messages.create.return_value = mock_response
        with patch("app.ai.providers.claude.Anthropic", return_value=mock_client):
            provider = AnthropicProvider(
                api_key="sk-test",
                system_prompt="You are Claude.",
            )
            provider.generate("hi")
        kwargs = mock_client.messages.create.call_args.kwargs
        assert kwargs["system"] == "You are Claude."


# ---------------------------------------------------------------------------
# Gemini provider generation (mocked SDK)
# ---------------------------------------------------------------------------


class TestGeminiProviderGenerate:
    """Tests for the real Gemini provider implementation with mocked SDK."""

    @staticmethod
    def _make_mock_success(
        text: str = "Hello from Gemini!",
        prompt_tokens: int | None = 8,
        candidates_tokens: int | None = 4,
    ) -> MagicMock:
        mock_response = MagicMock()
        mock_response.text = text
        if prompt_tokens is not None:
            mock_response.usage_metadata = MagicMock(
                prompt_token_count=prompt_tokens,
                candidates_token_count=candidates_tokens or 0,
                total_token_count=(prompt_tokens or 0) + (candidates_tokens or 0),
            )
        else:
            mock_response.usage_metadata = None
        mock_model = MagicMock()
        mock_model.generate_content.return_value = mock_response
        return patch("app.ai.providers.gemini.GenerativeModel", return_value=mock_model)

    @staticmethod
    def _make_mock_error(exc_cls: type[Exception], message: str = "sdkerror") -> MagicMock:
        mock_model = MagicMock()
        mock_model.generate_content.side_effect = exc_cls(message)
        return patch("app.ai.providers.gemini.GenerativeModel", return_value=mock_model)

    def test_successful_completion(self) -> None:
        with self._make_mock_success(text="Hello!", prompt_tokens=8, candidates_tokens=4):
            provider = GeminiProvider(api_key="sk-test")
            result = provider.generate("Hi")
        assert isinstance(result, AIResponse)
        assert result == "Hello!"
        assert result.provider == "gemini"
        assert result.model == "gemini-2.0-flash-exp"
        assert result.latency_ms > 0
        assert result.metadata["prompt_token_count"] == 8
        assert result.metadata["candidates_token_count"] == 4
        assert result.metadata["total_token_count"] == 12

    def test_successful_completion_without_usage(self) -> None:
        with self._make_mock_success(text="No usage", prompt_tokens=None):
            provider = GeminiProvider(api_key="sk-test")
            result = provider.generate("Hi")
        assert isinstance(result, AIResponse)
        assert result == "No usage"
        assert result.metadata == {}

    def test_api_key_missing(self) -> None:
        provider = GeminiProvider()
        with pytest.raises(ProviderNotConfiguredError):
            provider.generate("hello")

    def test_timeout(self) -> None:
        with self._make_mock_error(Exception, "deadline exceeded"):
            provider = GeminiProvider(api_key="sk-test")
            with pytest.raises(ProviderTimeoutError):
                provider.generate("hello")

    def test_rate_limit(self) -> None:
        with self._make_mock_error(Exception, "429 Too Many Requests"):
            provider = GeminiProvider(api_key="sk-test")
            with pytest.raises(ProviderRateLimitError):
                provider.generate("hello")

    def test_authentication_error(self) -> None:
        with self._make_mock_error(Exception, "401 Unauthenticated"):
            provider = GeminiProvider(api_key="sk-test")
            with pytest.raises(ProviderAPIAuthorizationError):
                provider.generate("hello")

    def test_connection_error(self) -> None:
        with self._make_mock_error(Exception, "connection refused"):
            provider = GeminiProvider(api_key="sk-test")
            with pytest.raises(ProviderConnectionError):
                provider.generate("hello")

    def test_unexpected_error(self) -> None:
        with self._make_mock_error(Exception, "internal server error"):
            provider = GeminiProvider(api_key="sk-test")
            with pytest.raises(ProviderUnexpectedError):
                provider.generate("hello")

    def test_retry_on_transient_error_then_succeeds(self) -> None:
        mock_response = MagicMock()
        mock_response.text = "recovered"
        mock_response.usage_metadata = None
        mock_model = MagicMock()
        mock_model.generate_content.side_effect = [
            Exception("deadline exceeded one"),
            Exception("deadline exceeded two"),
            mock_response,
        ]
        with patch("app.ai.providers.gemini.GenerativeModel", return_value=mock_model):
            provider = GeminiProvider(api_key="sk-test")
            result = provider.generate("hello")
        assert isinstance(result, AIResponse)
        assert result == "recovered"

    def test_retry_exhausted_raises_last_error(self) -> None:
        mock_model = MagicMock()
        mock_model.generate_content.side_effect = Exception("deadline exceeded always")
        with patch("app.ai.providers.gemini.GenerativeModel", return_value=mock_model):
            provider = GeminiProvider(api_key="sk-test")
            with pytest.raises(ProviderTimeoutError):
                provider.generate("hello")

    def test_non_retryable_error_propagates_immediately(self) -> None:
        with self._make_mock_error(Exception, "403 Forbidden"):
            provider = GeminiProvider(api_key="sk-test")
            with pytest.raises(ProviderAPIAuthorizationError):
                provider.generate("hello")

    def test_provider_info(self) -> None:
        provider = GeminiProvider(api_key="sk-test")
        info = provider.provider_info()
        assert isinstance(info, ProviderMetadata)
        assert info.name == "gemini"
        assert info.model == "gemini-2.0-flash-exp"
        assert info.base_url == "https://generativelanguage.googleapis.com"
        assert info.timeout == 30.0
        assert ProviderCapability.STREAMING in info.capabilities
        assert ProviderCapability.FUNCTION_CALLING in info.capabilities
        assert ProviderCapability.EMBEDDINGS in info.capabilities
        assert ProviderCapability.IMAGE_INPUT in info.capabilities
        assert ProviderCapability.JSON_OUTPUT in info.capabilities

    def test_capabilities_class_attribute(self) -> None:
        assert hasattr(GeminiProvider, "capabilities")
        assert isinstance(GeminiProvider.capabilities, frozenset)
        assert ProviderCapability.STREAMING in GeminiProvider.capabilities
        assert ProviderCapability.FUNCTION_CALLING in GeminiProvider.capabilities
        assert ProviderCapability.EMBEDDINGS in GeminiProvider.capabilities
        assert ProviderCapability.IMAGE_INPUT in GeminiProvider.capabilities
        assert ProviderCapability.JSON_OUTPUT in GeminiProvider.capabilities

    def test_temperature_and_max_tokens_not_sent_when_not_set(self) -> None:
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "ok"
        mock_response.usage_metadata = None
        mock_model.generate_content.return_value = mock_response
        with patch("app.ai.providers.gemini.GenerativeModel", return_value=mock_model):
            provider = GeminiProvider(api_key="sk-test")
            provider.generate("hi")
        call_kwargs = mock_model.generate_content.call_args.kwargs
        assert call_kwargs.get("generation_config") is None

    def test_temperature_and_max_tokens_sent_when_set(self) -> None:
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "ok"
        mock_response.usage_metadata = None
        mock_model.generate_content.return_value = mock_response
        with patch("app.ai.providers.gemini.GenerativeModel", return_value=mock_model):
            provider = GeminiProvider(api_key="sk-test", temperature=0.7, max_tokens=512)
            provider.generate("hi")
        call_kwargs = mock_model.generate_content.call_args.kwargs
        config = call_kwargs["generation_config"]
        assert config.temperature == 0.7
        assert config.max_output_tokens == 512

    def test_system_prompt_sent_when_set(self) -> None:
        mock_response = MagicMock()
        mock_response.text = "ok"
        mock_response.usage_metadata = None
        mock_model = MagicMock()
        mock_model.generate_content.return_value = mock_response
        with patch("app.ai.providers.gemini.GenerativeModel", return_value=mock_model) as model_cls:
            provider = GeminiProvider(
                api_key="sk-test",
                system_prompt="You are Gemini.",
            )
            provider.generate("hi")
        init_kwargs = model_cls.call_args.kwargs
        assert init_kwargs.get("system_instruction") == "You are Gemini."


# ---------------------------------------------------------------------------
# DeepSeek-specific behavior (OpenAI-compatible SDK, custom base URL)
# ---------------------------------------------------------------------------


class TestDeepSeekProviderGenerate:
    """Tests for the real DeepSeek provider implementation with mocked SDK."""

    @staticmethod
    def _make_mock_success(
        text: str = "Hello from DeepSeek!",
        prompt_tokens: int | None = 8,
        completion_tokens: int | None = 4,
    ) -> MagicMock:
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content=text))]
        if prompt_tokens is not None:
            mock_response.usage = MagicMock(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens or 0,
                total_tokens=(prompt_tokens or 0) + (completion_tokens or 0),
            )
        else:
            mock_response.usage = None
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        return patch("app.ai.providers.deepseek.OpenAI", return_value=mock_client)

    @staticmethod
    def _make_mock_error(exc_cls: type[Exception], message: str = "sdkerror") -> MagicMock:
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = exc_cls(message)
        return patch("app.ai.providers.deepseek.OpenAI", return_value=mock_client)

    def test_successful_completion(self) -> None:
        with self._make_mock_success(text="Hello!", prompt_tokens=8, completion_tokens=4):
            provider = DeepSeekProvider(api_key="sk-test")
            result = provider.generate("Hi")
        assert isinstance(result, AIResponse)
        assert result == "Hello!"
        assert result.provider == "deepseek"
        assert result.model == "deepseek-chat"
        assert result.latency_ms > 0
        assert result.metadata["prompt_tokens"] == 8
        assert result.metadata["completion_tokens"] == 4
        assert result.metadata["total_tokens"] == 12

    def test_successful_completion_without_usage(self) -> None:
        with self._make_mock_success(text="No usage", prompt_tokens=None):
            provider = DeepSeekProvider(api_key="sk-test")
            result = provider.generate("Hi")
        assert isinstance(result, AIResponse)
        assert result == "No usage"
        assert result.metadata == {}

    def test_api_key_missing(self) -> None:
        provider = DeepSeekProvider()
        with pytest.raises(ProviderNotConfiguredError):
            provider.generate("hello")

    def test_timeout(self) -> None:
        with self._make_mock_error(Exception, "timeout"):
            provider = DeepSeekProvider(api_key="sk-test")
            with pytest.raises(ProviderTimeoutError):
                provider.generate("hello")

    def test_rate_limit(self) -> None:
        with self._make_mock_error(Exception, "429 Too Many Requests"):
            provider = DeepSeekProvider(api_key="sk-test")
            with pytest.raises(ProviderRateLimitError):
                provider.generate("hello")

    def test_authentication_error(self) -> None:
        with self._make_mock_error(Exception, "401 Unauthenticated"):
            provider = DeepSeekProvider(api_key="sk-test")
            with pytest.raises(ProviderAPIAuthorizationError):
                provider.generate("hello")

    def test_connection_error(self) -> None:
        with self._make_mock_error(Exception, "connection refused"):
            provider = DeepSeekProvider(api_key="sk-test")
            with pytest.raises(ProviderConnectionError):
                provider.generate("hello")

    def test_unexpected_error(self) -> None:
        with self._make_mock_error(Exception, "internal server error"):
            provider = DeepSeekProvider(api_key="sk-test")
            with pytest.raises(ProviderUnexpectedError):
                provider.generate("hello")

    def test_retry_on_transient_error_then_succeeds(self) -> None:
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="recovered"))]
        mock_response.usage = None
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            Exception("timeout one"),
            Exception("timeout two"),
            mock_response,
        ]
        with patch("app.ai.providers.deepseek.OpenAI", return_value=mock_client):
            provider = DeepSeekProvider(api_key="sk-test")
            result = provider.generate("hello")
        assert isinstance(result, AIResponse)
        assert result == "recovered"

    def test_retry_exhausted_raises_last_error(self) -> None:
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("timeout always")
        with patch("app.ai.providers.deepseek.OpenAI", return_value=mock_client):
            provider = DeepSeekProvider(api_key="sk-test")
            with pytest.raises(ProviderTimeoutError):
                provider.generate("hello")

    def test_non_retryable_error_propagates_immediately(self) -> None:
        with self._make_mock_error(Exception, "403 Forbidden"):
            provider = DeepSeekProvider(api_key="sk-test")
            with pytest.raises(ProviderAPIAuthorizationError):
                provider.generate("hello")

    def test_provider_info(self) -> None:
        provider = DeepSeekProvider(api_key="sk-test")
        info = provider.provider_info()
        assert isinstance(info, ProviderMetadata)
        assert info.name == "deepseek"
        assert info.model == "deepseek-chat"
        assert info.base_url == "https://api.deepseek.com"
        assert info.timeout == 30.0
        assert ProviderCapability.STREAMING in info.capabilities
        assert ProviderCapability.FUNCTION_CALLING in info.capabilities
        assert ProviderCapability.JSON_OUTPUT in info.capabilities
        assert ProviderCapability.EMBEDDINGS not in info.capabilities
        assert ProviderCapability.IMAGE_INPUT not in info.capabilities

    def test_capabilities_class_attribute(self) -> None:
        assert hasattr(DeepSeekProvider, "capabilities")
        assert isinstance(DeepSeekProvider.capabilities, frozenset)
        assert ProviderCapability.STREAMING in DeepSeekProvider.capabilities
        assert ProviderCapability.FUNCTION_CALLING in DeepSeekProvider.capabilities
        assert ProviderCapability.JSON_OUTPUT in DeepSeekProvider.capabilities
        assert ProviderCapability.EMBEDDINGS not in DeepSeekProvider.capabilities
        assert ProviderCapability.IMAGE_INPUT not in DeepSeekProvider.capabilities

    def test_temperature_not_sent_when_not_set(self) -> None:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="ok"))]
        mock_response.usage = None
        mock_client.chat.completions.create.return_value = mock_response
        with patch("app.ai.providers.deepseek.OpenAI", return_value=mock_client):
            provider = DeepSeekProvider(api_key="sk-test")
            provider.generate("hi")
        kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert "temperature" not in kwargs

    def test_temperature_sent_when_set(self) -> None:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="ok"))]
        mock_response.usage = None
        mock_client.chat.completions.create.return_value = mock_response
        with patch("app.ai.providers.deepseek.OpenAI", return_value=mock_client):
            provider = DeepSeekProvider(api_key="sk-test", temperature=0.3)
            provider.generate("hi")
        kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert kwargs["temperature"] == 0.3

    def test_max_tokens_not_sent_when_not_set(self) -> None:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="ok"))]
        mock_response.usage = None
        mock_client.chat.completions.create.return_value = mock_response
        with patch("app.ai.providers.deepseek.OpenAI", return_value=mock_client):
            provider = DeepSeekProvider(api_key="sk-test")
            provider.generate("hi")
        kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert "max_tokens" not in kwargs

    def test_max_tokens_sent_when_set(self) -> None:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="ok"))]
        mock_response.usage = None
        mock_client.chat.completions.create.return_value = mock_response
        with patch("app.ai.providers.deepseek.OpenAI", return_value=mock_client):
            provider = DeepSeekProvider(api_key="sk-test", max_tokens=512)
            provider.generate("hi")
        kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert kwargs["max_tokens"] == 512

    def test_system_prompt_sent_when_set(self) -> None:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="ok"))]
        mock_response.usage = None
        mock_client.chat.completions.create.return_value = mock_response
        with patch("app.ai.providers.deepseek.OpenAI", return_value=mock_client):
            provider = DeepSeekProvider(api_key="sk-test", system_prompt="You are DeepSeek.")
            provider.generate("hi")
        msgs = mock_client.chat.completions.create.call_args.kwargs["messages"]
        assert {"role": "system", "content": "You are DeepSeek."} in msgs
