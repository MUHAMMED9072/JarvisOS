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

import pytest

from app.ai.providers.claude import AnthropicProvider
from app.ai.providers.base import (
    AIProvider,
    AIProviderError,
    ProviderNotConfiguredError,
    ProviderNotImplementedError,
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


class TestAnthropicProviderConstruction(_CloudProviderConstruction):
    provider_cls = AnthropicProvider
    env_var = "ANTHROPIC_API_KEY"

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


class TestDeepSeekProviderConstruction(_CloudProviderConstruction):
    provider_cls = DeepSeekProvider
    env_var = "DEEPSEEK_API_KEY"


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
        # Set the API keys in the environment so the providers
        # make it past the configuration check and into the
        # ``ProviderNotImplementedError`` branch.
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        monkeypatch.setenv("GEMINI_API_KEY", "sk-test")
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")

        router = AIRouter()
        # Ollama's real SDK call would hit the network; instead
        # verify the other four raise the expected stub exception
        # when dispatched through the router, which proves the
        # router -> provider wiring is intact without doing a
        # real HTTP call.
        for cls, name in CLOUD_PROVIDER_CLASSES:
            with pytest.raises(ProviderNotImplementedError):
                router.ask(name, "hello")

    def test_router_ask_unknown_provider_still_raises_value_error(
        self,
    ) -> None:
        router = AIRouter()
        with pytest.raises(ValueError):
            router.ask("does_not_exist", "hello")
