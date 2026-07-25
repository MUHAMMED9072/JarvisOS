from __future__ import annotations

import os

from anthropic import Anthropic

from dotenv import load_dotenv

from .base import (
    _ProviderBase,
    AIResponse,
    ProviderCapability,
    ProviderNotConfiguredError,
    _call_sdk,
    validate_optional_str,
    validate_str,
    validate_timeout,
    retry_with_backoff,
)


load_dotenv()


class AnthropicProvider(_ProviderBase):

    provider_name: str = "claude"

    capabilities: frozenset = frozenset({
        ProviderCapability.STREAMING,
        ProviderCapability.FUNCTION_CALLING,
        ProviderCapability.IMAGE_INPUT,
        ProviderCapability.JSON_OUTPUT,
    })

    DEFAULT_BASE_URL = "https://api.anthropic.com"
    DEFAULT_MODEL = "claude-3-5-sonnet-latest"
    DEFAULT_TIMEOUT = 30.0
    DEFAULT_MAX_TOKENS = 1024
    ENV_API_KEY_VAR = "ANTHROPIC_API_KEY"

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        temperature: float | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        system_prompt: str | None = None,
    ) -> None:
        self._api_key: str | None = validate_optional_str(
            api_key, "api_key", owner=self.__class__.__name__
        )
        self._base_url = validate_str(
            base_url if base_url is not None else self.DEFAULT_BASE_URL,
            "base_url",
            owner=self.__class__.__name__,
        )
        self._model = validate_str(
            model if model is not None else self.DEFAULT_MODEL,
            "model",
            owner=self.__class__.__name__,
        )
        self._timeout = validate_timeout(timeout, owner=self.__class__.__name__)
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._system_prompt = system_prompt
        self._client: Anthropic | None = None

    def _resolve_api_key(self) -> str:
        if self._api_key:
            return self._api_key
        env_key = os.getenv(self.ENV_API_KEY_VAR)
        if isinstance(env_key, str) and env_key.strip():
            self._api_key = env_key
            return env_key
        raise ProviderNotConfiguredError(
            f"{type(self).__name__}: {self.ENV_API_KEY_VAR} is not set "
            f"in the environment and no api_key= was supplied"
        )

    def _get_client(self) -> Anthropic:
        if self._client is None:
            api_key = self._resolve_api_key()
            self._client = Anthropic(
                api_key=api_key,
                base_url=self._base_url,
                timeout=self._timeout,
            )
        return self._client

    @retry_with_backoff()
    def generate(self, prompt: str) -> AIResponse:
        if not isinstance(prompt, str):
            raise TypeError(
                f"prompt must be str, got {type(prompt).__name__}"
            )
        client = self._get_client()
        kwargs = {}
        if self._temperature is not None:
            kwargs["temperature"] = self._temperature
        return _call_sdk(
            sdk_call=lambda: client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                system=self._system_prompt or "",
                messages=[{"role": "user", "content": prompt}],
                **kwargs,
            ),
            provider_name=self.provider_name,
            model=self._model,
            response_handler=lambda r: (
                r.content[0].text,
                {
                    "input_tokens": r.usage.input_tokens,
                    "output_tokens": r.usage.output_tokens,
                } if r.usage else {},
            ),
        )
