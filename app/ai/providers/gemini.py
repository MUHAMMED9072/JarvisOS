from __future__ import annotations

import os

from google.generativeai import GenerativeModel
from google.generativeai import configure as genai_configure
from google.generativeai.types import GenerationConfig

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


class GeminiProvider(_ProviderBase):

    provider_name: str = "gemini"

    capabilities: frozenset = frozenset({
        ProviderCapability.STREAMING,
        ProviderCapability.FUNCTION_CALLING,
        ProviderCapability.EMBEDDINGS,
        ProviderCapability.IMAGE_INPUT,
        ProviderCapability.JSON_OUTPUT,
    })

    DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com"
    DEFAULT_MODEL = "gemini-2.0-flash-exp"
    DEFAULT_TIMEOUT = 30.0
    ENV_API_KEY_VAR = "GEMINI_API_KEY"

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        temperature: float | None = None,
        max_tokens: int | None = None,
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
        self._configured: bool = False
        self._gen_model: GenerativeModel | None = None

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

    def _configure(self) -> None:
        if not self._configured:
            api_key = self._resolve_api_key()
            genai_configure(api_key=api_key)
            self._configured = True

    def _get_model(self) -> GenerativeModel:
        if self._gen_model is None:
            self._configure()
            kwargs = {}
            if self._system_prompt:
                kwargs["system_instruction"] = self._system_prompt
            self._gen_model = GenerativeModel(
                self._model,
                **kwargs,
            )
        return self._gen_model

    @retry_with_backoff()
    def generate(self, prompt: str) -> AIResponse:
        if not isinstance(prompt, str):
            raise TypeError(
                f"prompt must be str, got {type(prompt).__name__}"
            )
        model = self._get_model()
        config_kwargs = {}
        if self._temperature is not None:
            config_kwargs["temperature"] = self._temperature
        if self._max_tokens is not None:
            config_kwargs["max_output_tokens"] = self._max_tokens
        generation_config = GenerationConfig(**config_kwargs) if config_kwargs else None
        return _call_sdk(
            sdk_call=lambda: model.generate_content(
                prompt,
                generation_config=generation_config,
            ),
            provider_name=self.provider_name,
            model=self._model,
            response_handler=lambda r: (
                r.text or "",
                {
                    "prompt_token_count": r.usage_metadata.prompt_token_count,
                    "candidates_token_count": r.usage_metadata.candidates_token_count,
                    "total_token_count": r.usage_metadata.total_token_count,
                } if r.usage_metadata else {},
            ),
        )
