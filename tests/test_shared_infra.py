from __future__ import annotations


from unittest.mock import patch

import pytest

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
from app.ai.providers.claude import AnthropicProvider
from app.ai.providers.deepseek import DeepSeekProvider
from app.ai.providers.gemini import GeminiProvider
from app.ai.providers.ollama import OllamaProvider
from app.ai.providers.openai import OpenAIProvider


class TestAIResponse:
    def test_ai_response_is_str(self):
        r = AIResponse("hello", provider="openai", model="gpt-4", latency_ms=12.5)
        assert isinstance(r, str)
        assert r == "hello"

    def test_ai_response_metadata(self):
        r = AIResponse("hello", provider="openai", model="gpt-4", latency_ms=12.5)
        assert r.provider == "openai"
        assert r.model == "gpt-4"
        assert r.latency_ms == 12.5
        assert r.metadata == {}

    def test_ai_response_metadata_with_extra(self):
        r = AIResponse(
            "hello",
            provider="openai",
            model="gpt-4",
            latency_ms=12.5,
            metadata={"tokens": 42},
        )
        assert r.metadata == {"tokens": 42}

    def test_ai_response_operations_work_like_str(self):
        r = AIResponse("hello world", provider="openai", model="gpt-4", latency_ms=5.0)
        assert r.upper() == "HELLO WORLD"
        assert r.startswith("hello")

    def test_ai_response_equality_with_str(self):
        r = AIResponse("test", provider="openai", model="gpt-4", latency_ms=1.0)
        assert r == "test"


class TestProviderCapability:
    def test_streaming_flag(self):
        assert ProviderCapability.STREAMING.value > 0

    def test_function_calling_flag(self):
        assert ProviderCapability.FUNCTION_CALLING.value > 0

    def test_embeddings_flag(self):
        assert ProviderCapability.EMBEDDINGS.value > 0

    def test_image_input_flag(self):
        assert ProviderCapability.IMAGE_INPUT.value > 0

    def test_json_output_flag(self):
        assert ProviderCapability.JSON_OUTPUT.value > 0

    def test_combining_capabilities(self):
        cap = ProviderCapability.STREAMING | ProviderCapability.FUNCTION_CALLING
        assert ProviderCapability.STREAMING in cap
        assert ProviderCapability.FUNCTION_CALLING in cap
        assert ProviderCapability.EMBEDDINGS not in cap

    def test_empty_capabilities_frozenset(self):
        assert ProviderCapability.STREAMING not in frozenset()


class TestProviderMetadata:
    def test_creation(self):
        meta = ProviderMetadata(
            name="openai",
            model="gpt-4",
            base_url="https://api.openai.com/v1",
        )
        assert meta.name == "openai"
        assert meta.model == "gpt-4"
        assert meta.base_url == "https://api.openai.com/v1"
        assert meta.capabilities == frozenset()
        assert meta.timeout == 30.0

    def test_with_capabilities(self):
        cap = ProviderCapability.STREAMING | ProviderCapability.JSON_OUTPUT
        meta = ProviderMetadata(
            name="openai",
            model="gpt-4",
            base_url="https://api.openai.com/v1",
            capabilities=cap,
            timeout=60.0,
        )
        assert meta.capabilities == cap
        assert meta.timeout == 60.0

    def test_is_frozen(self):
        meta = ProviderMetadata(
            name="openai",
            model="gpt-4",
            base_url="https://api.openai.com/v1",
        )
        with pytest.raises(AttributeError):
            meta.name = "claude"  # type: ignore[misc]


class TestSharedValidation:
    def test_validate_str_returns_string(self):
        assert validate_str("hello", "field", owner="TestProvider") == "hello"

    def test_validate_str_rejects_non_string(self):
        with pytest.raises(ProviderNotConfiguredError):
            validate_str(42, "field", owner="TestProvider")

    def test_validate_str_rejects_empty(self):
        with pytest.raises(ProviderNotConfiguredError):
            validate_str("  ", "field", owner="TestProvider")

    def test_validate_str_rejects_none(self):
        with pytest.raises(ProviderNotConfiguredError):
            validate_str(None, "field", owner="TestProvider")

    def test_validate_optional_str_returns_none(self):
        assert validate_optional_str(None, "field", owner="TestProvider") is None

    def test_validate_optional_str_returns_string(self):
        assert validate_optional_str("hello", "field", owner="TestProvider") == "hello"

    def test_validate_optional_str_rejects_empty(self):
        with pytest.raises(ProviderNotConfiguredError):
            validate_optional_str("", "field", owner="TestProvider")

    def test_validate_timeout_returns_float(self):
        assert validate_timeout(30, owner="TestProvider") == 30.0

    def test_validate_timeout_rejects_bool(self):
        with pytest.raises(ProviderNotConfiguredError):
            validate_timeout(True, owner="TestProvider")

    def test_validate_timeout_rejects_non_numeric(self):
        with pytest.raises(ProviderNotConfiguredError):
            validate_timeout("fast", owner="TestProvider")

    def test_validate_timeout_rejects_non_positive(self):
        with pytest.raises(ProviderNotConfiguredError):
            validate_timeout(0, owner="TestProvider")

    def test_validate_api_key_returns_key(self):
        assert validate_api_key("sk-test", "api_key", owner="TestProvider") == "sk-test"

    def test_validate_api_key_rejects_none(self):
        with pytest.raises(ProviderNotConfiguredError):
            validate_api_key(None, "api_key", owner="TestProvider")


class TestMapException:
    def test_already_ai_provider_error_returns_as_is(self):
        exc = ProviderNotConfiguredError("test")
        assert map_exception(exc, "openai") is exc

    def test_maps_timeout_exception(self):
        exc = Exception("timeout exceeded")
        result = map_exception(exc, "openai")
        assert isinstance(result, ProviderTimeoutError)

    def test_maps_rate_limit_exception(self):
        exc = Exception("429 rate limit exceeded")
        result = map_exception(exc, "openai")
        assert isinstance(result, ProviderRateLimitError)

    def test_maps_connection_error(self):
        exc = Exception("ConnectionError: refused")
        result = map_exception(exc, "openai")
        assert isinstance(result, ProviderConnectionError)

    def test_maps_auth_error(self):
        exc = Exception("401 Unauthorized")
        result = map_exception(exc, "openai")
        assert isinstance(result, ProviderAPIAuthorizationError)

    def test_maps_unexpected_exception(self):
        exc = Exception("something weird")
        result = map_exception(exc, "openai")
        assert isinstance(result, ProviderUnexpectedError)

    def test_exception_contains_provider_name(self):
        exc = Exception("boom")
        result = map_exception(exc, "deepseek")
        assert "deepseek" in str(result)


class TestRetryWithBackoff:
    def test_retry_succeeds_on_first_attempt(self):
        call_count = 0

        @retry_with_backoff(max_retries=3)
        def fast():
            nonlocal call_count
            call_count += 1
            return AIResponse("ok", provider="test", model="test", latency_ms=0)

        result = fast()
        assert call_count == 1
        assert result == "ok"

    def test_retry_succeeds_after_failures(self):
        call_count = 0

        @retry_with_backoff(max_retries=3, base_delay=0.01)
        def eventually_succeeds():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ProviderTimeoutError("timeout")
            return AIResponse("ok", provider="test", model="test", latency_ms=0)

        result = eventually_succeeds()
        assert call_count == 3
        assert result == "ok"

    def test_retry_exhausts_retries(self):
        call_count = 0

        @retry_with_backoff(max_retries=2, base_delay=0.01)
        def always_fails():
            nonlocal call_count
            call_count += 1
            raise ProviderTimeoutError("timeout")

        with pytest.raises(ProviderTimeoutError):
            always_fails()
        assert call_count == 3

    def test_retry_does_not_retry_non_retryable(self):
        call_count = 0

        @retry_with_backoff(max_retries=3, base_delay=0.01)
        def auth_error():
            nonlocal call_count
            call_count += 1
            raise ProviderAPIAuthorizationError("auth failed")

        with pytest.raises(ProviderAPIAuthorizationError):
            auth_error()
        assert call_count == 1

    def test_retry_preserves_function_metadata(self):
        def original():
            return 42

        decorated = retry_with_backoff(max_retries=1)(original)
        assert decorated.__name__ == "original"


class TestProviderCapabilities:
    def test_all_providers_have_name(self):
        for cls in [OpenAIProvider, AnthropicProvider, GeminiProvider, DeepSeekProvider, OllamaProvider]:
            assert isinstance(cls.provider_name, str)
            assert len(cls.provider_name) > 0

    def test_all_providers_have_capabilities_frozenset(self):
        for cls in [OpenAIProvider, AnthropicProvider, GeminiProvider, DeepSeekProvider, OllamaProvider]:
            assert isinstance(cls.capabilities, frozenset)