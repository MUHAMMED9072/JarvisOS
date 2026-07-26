from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any, Generator

from openai import OpenAI

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


def _handle_openai_response(
    raw_response: Any, tool_calls: list, structured_result: Any = None,
) -> tuple[str, dict]:
    """Build ``(content, metadata)`` from an OpenAI SDK response."""
    content = raw_response.choices[0].message.content or ""
    metadata: dict = {}
    if raw_response.usage:
        metadata["prompt_tokens"] = raw_response.usage.prompt_tokens
        metadata["completion_tokens"] = raw_response.usage.completion_tokens
        metadata["total_tokens"] = raw_response.usage.total_tokens
    if tool_calls:
        metadata["tool_calls"] = tool_calls
    if structured_result is not None:
        metadata["structured"] = structured_result
        if structured_result.valid:
            content = raw_response.choices[0].message.content or ""
    return content, metadata


class OpenAIProvider(_ProviderBase):

    provider_name: str = "openai"

    capabilities: frozenset = frozenset({
        ProviderCapability.STREAMING,
        ProviderCapability.FUNCTION_CALLING,
        ProviderCapability.EMBEDDINGS,
        ProviderCapability.IMAGE_INPUT,
        ProviderCapability.JSON_OUTPUT,
        ProviderCapability.CONVERSATION,
        ProviderCapability.SYSTEM_PROMPT,
        ProviderCapability.REASONING,
        ProviderCapability.TEXT_GENERATION,
    })

    DEFAULT_BASE_URL = "https://api.openai.com/v1"
    DEFAULT_MODEL = "gpt-4o-mini"
    DEFAULT_TIMEOUT = 30.0
    ENV_API_KEY_VAR = "OPENAI_API_KEY"

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
        self._client: OpenAI | None = None

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

    def _get_client(self) -> OpenAI:
        if self._client is None:
            api_key = self._resolve_api_key()
            self._client = OpenAI(
                api_key=api_key,
                base_url=self._base_url,
                timeout=self._timeout,
            )
        return self._client

    def format_tools(self, tools: list[ToolDefinition]) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in tools
        ]

    def format_structured_schema(self, schema: StructuredSchema) -> dict | None:
        return {
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": schema.name,
                    "schema": schema.schema,
                    "strict": True,
                },
            },
        }

    def parse_tool_calls(self, raw_response: Any) -> list[ToolCall]:
        from ..tools import ToolCall
        if raw_response is None:
            return []
        message = getattr(raw_response.choices[0], "message", None)
        if message is None:
            return []
        raw_calls = getattr(message, "tool_calls", None)
        if raw_calls is None:
            return []
        return [
            ToolCall(
                id=tc.id,
                name=tc.function.name,
                arguments=tc.function.arguments,
            )
            for tc in raw_calls
        ]

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
        client = self._get_client()
        messages = []
        if self._system_prompt:
            messages.append({"role": "system", "content": self._system_prompt})
        messages.append({"role": "user", "content": prompt})
        kwargs = {}
        if self._temperature is not None:
            kwargs["temperature"] = self._temperature
        if self._max_tokens is not None:
            kwargs["max_tokens"] = self._max_tokens
        if tools:
            kwargs["tools"] = self.format_tools(tools)

        structured_result = None
        if schema:
            config = self.format_structured_schema(schema)
            if config:
                kwargs.update(config)

        return _call_sdk(
            sdk_call=lambda: client.chat.completions.create(
                model=self._model,
                messages=messages,
                **kwargs,
            ),
            provider_name=self.provider_name,
            model=self._model,
            response_handler=lambda r: _handle_openai_response(
                r, self.parse_tool_calls(r),
                self.parse_structured_response(
                    r.choices[0].message.content or "", schema
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
        client = self._get_client()
        messages = []
        if self._system_prompt:
            messages.append({"role": "system", "content": self._system_prompt})
        messages.append({"role": "user", "content": prompt})
        kwargs = {}
        if self._temperature is not None:
            kwargs["temperature"] = self._temperature
        if self._max_tokens is not None:
            kwargs["max_tokens"] = self._max_tokens

        def chunk_handler(raw_chunk: Any) -> AIStreamChunk | None:
            choice = raw_chunk.choices[0] if raw_chunk.choices else None
            if choice is None:
                return None
            content = choice.delta.content if choice.delta else ""
            finish = choice.finish_reason
            usage = (
                {
                    "prompt_tokens": raw_chunk.usage.prompt_tokens,
                    "completion_tokens": raw_chunk.usage.completion_tokens,
                    "total_tokens": raw_chunk.usage.total_tokens,
                }
                if getattr(raw_chunk, "usage", None)
                else None
            )
            return AIStreamChunk(
                content=content or "",
                finish_reason=finish,
                usage=usage,
            )

        yield from _stream_sdk(
            sdk_call=lambda: client.chat.completions.create(
                model=self._model,
                messages=messages,
                stream=True,
                stream_options={"include_usage": True},
                **kwargs,
            ),
            provider_name=self.provider_name,
            chunk_handler=chunk_handler,
        )
