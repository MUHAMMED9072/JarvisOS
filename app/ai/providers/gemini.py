from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any, Generator

from google.generativeai import GenerativeModel
from google.generativeai import configure as genai_configure
from google.generativeai.types import GenerationConfig

from dotenv import load_dotenv

if TYPE_CHECKING:
    from ..structured import StructuredResult, StructuredSchema
    from ..tools import ToolCall, ToolDefinition

from .base import (
    _ProviderBase,
    AIResponse,
    AIStreamChunk,
    ProviderCapability,
    ProviderNotConfiguredError,
    _call_sdk,
    _stream_sdk,
    validate_optional_str,
    validate_str,
    validate_timeout,
    retry_with_backoff,
)


load_dotenv()


def _handle_gemini_response(raw_response: Any, tool_calls: list, structured_result: Any = None) -> tuple[str, dict]:
    content = raw_response.text or ""
    metadata: dict = {}
    if raw_response.usage_metadata:
        metadata.update({
            "prompt_token_count": raw_response.usage_metadata.prompt_token_count,
            "candidates_token_count": raw_response.usage_metadata.candidates_token_count,
            "total_token_count": raw_response.usage_metadata.total_token_count,
        })
    if tool_calls:
        metadata["tool_calls"] = tool_calls
    if structured_result is not None:
        metadata["structured"] = structured_result
    return content, metadata


class GeminiProvider(_ProviderBase):

    provider_name: str = "gemini"

    capabilities: frozenset = frozenset({
        ProviderCapability.STREAMING,
        ProviderCapability.FUNCTION_CALLING,
        ProviderCapability.EMBEDDINGS,
        ProviderCapability.IMAGE_INPUT,
        ProviderCapability.JSON_OUTPUT,
        ProviderCapability.CONVERSATION,
        ProviderCapability.SYSTEM_PROMPT,
        ProviderCapability.TEXT_GENERATION,
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

    def format_tools(self, tools: list[ToolDefinition]) -> list[dict]:
        return [
            {
                "function_declarations": [
                    {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    }
                    for t in tools
                ],
            }
        ]

    def format_structured_schema(self, schema: StructuredSchema) -> dict | None:
        return {
            "generation_config": GenerationConfig(
                response_mime_type="application/json",
            ),
        }

    def parse_tool_calls(self, raw_response: Any) -> list[ToolCall]:
        from ..tools import ToolCall
        try:
            candidates = raw_response.candidates
            if not candidates:
                return []
            parts = candidates[0].content.parts
            result: list[ToolCall] = []
            for part in parts:
                fc = getattr(part, "function_call", None)
                if fc is None:
                    continue
                args = {}
                for key, val in fc.args.items():
                    if hasattr(val, "number_value"):
                        args[key] = val.number_value
                    elif hasattr(val, "string_value"):
                        args[key] = val.string_value
                    elif hasattr(val, "bool_value"):
                        args[key] = val.bool_value
                    else:
                        args[key] = str(val)
                result.append(
                    ToolCall(
                        id=fc.name,
                        name=fc.name,
                        arguments=args,
                    )
                )
            return result
        except (AttributeError, IndexError, TypeError):
            return []

    @retry_with_backoff()
    def generate(
        self,
        prompt: str,
        tools: list[ToolDefinition] | None = None,
        schema: StructuredSchema | None = None,
    ) -> AIResponse:
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
        sdk_kwargs = {}
        if generation_config is not None:
            sdk_kwargs["generation_config"] = generation_config
        if tools:
            sdk_kwargs["tools"] = self.format_tools(tools)
        if schema:
            structured_config = self.format_structured_schema(schema)
            if structured_config:
                sdk_kwargs.update(structured_config)
        return _call_sdk(
            sdk_call=lambda: model.generate_content(
                prompt,
                **sdk_kwargs,
            ),
            provider_name=self.provider_name,
            model=self._model,
            response_handler=lambda r: _handle_gemini_response(
                r, self.parse_tool_calls(r),
                self.parse_structured_response(
                    r.text or "", schema,
                ) if schema else None,
            ),
        )

    def generate_stream(
        self, prompt: str,
    ) -> Generator[AIStreamChunk, None, None]:
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

        def chunk_handler(raw_chunk: Any) -> AIStreamChunk | None:
            text = getattr(raw_chunk, "text", None)
            usage_meta = getattr(raw_chunk, "usage_metadata", None)
            usage = (
                {
                    "prompt_token_count": usage_meta.prompt_token_count,
                    "candidates_token_count": usage_meta.candidates_token_count,
                    "total_token_count": usage_meta.total_token_count,
                }
                if usage_meta
                else None
            )
            return AIStreamChunk(
                content=text or "",
                usage=usage,
            )

        yield from _stream_sdk(
            sdk_call=lambda: model.generate_content(
                prompt,
                generation_config=generation_config,
                stream=True,
            ),
            provider_name=self.provider_name,
            chunk_handler=chunk_handler,
        )
