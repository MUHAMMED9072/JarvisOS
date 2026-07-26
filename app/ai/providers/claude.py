from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any, Generator

from anthropic import Anthropic

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


def _handle_claude_response(raw_response: Any, tool_calls: list, structured_result: Any = None) -> tuple[str, dict]:
    content = raw_response.content[0].text if raw_response.content and hasattr(raw_response.content[0], "text") else ""
    metadata: dict = {}
    if raw_response.usage:
        metadata["input_tokens"] = raw_response.usage.input_tokens
        metadata["output_tokens"] = raw_response.usage.output_tokens
    if tool_calls:
        metadata["tool_calls"] = tool_calls
    if structured_result is not None:
        metadata["structured"] = structured_result
    return content, metadata


class AnthropicProvider(_ProviderBase):

    provider_name: str = "claude"

    capabilities: frozenset = frozenset({
        ProviderCapability.STREAMING,
        ProviderCapability.FUNCTION_CALLING,
        ProviderCapability.IMAGE_INPUT,
        ProviderCapability.JSON_OUTPUT,
        ProviderCapability.CONVERSATION,
        ProviderCapability.SYSTEM_PROMPT,
        ProviderCapability.REASONING,
        ProviderCapability.TEXT_GENERATION,
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

    def format_tools(self, tools: list[ToolDefinition]) -> list[dict]:
        return [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.parameters,
            }
            for t in tools
        ]

    def parse_tool_calls(self, raw_response: Any) -> list[ToolCall]:
        from ..tools import ToolCall
        content = getattr(raw_response, "content", None)
        if not content:
            return []
        result: list[ToolCall] = []
        for block in content:
            if getattr(block, "type", None) == "tool_use":
                result.append(
                    ToolCall(
                        id=block.id,
                        name=block.name,
                        arguments=dict(block.input),
                    )
                )
        return result

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
        kwargs = {}
        if self._temperature is not None:
            kwargs["temperature"] = self._temperature
        if tools:
            kwargs["tools"] = self.format_tools(tools)

        system_text = self._system_prompt or ""
        if schema:
            system_text = (
                f"{system_text}\n\nYou must respond with valid JSON that "
                f"matches this schema: {schema.schema}"
            ).strip()

        return _call_sdk(
            sdk_call=lambda: client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                system=system_text,
                messages=[{"role": "user", "content": prompt}],
                **kwargs,
            ),
            provider_name=self.provider_name,
            model=self._model,
            response_handler=lambda r: _handle_claude_response(
                r, self.parse_tool_calls(r),
                self.parse_structured_response(
                    r.content[0].text if r.content and hasattr(r.content[0], "text") else "",
                    schema,
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
        kwargs = {}
        if self._temperature is not None:
            kwargs["temperature"] = self._temperature

        def chunk_handler(raw_chunk: Any) -> AIStreamChunk | None:
            if raw_chunk.type == "content_block_delta":
                text = getattr(raw_chunk.delta, "text", None)
                if text:
                    return AIStreamChunk(content=text)
            elif raw_chunk.type == "message_delta":
                usage = (
                    {
                        "input_tokens": raw_chunk.usage.input_tokens,
                        "output_tokens": raw_chunk.usage.output_tokens,
                    }
                    if getattr(raw_chunk, "usage", None)
                    else None
                )
                stop_reason = getattr(raw_chunk.delta, "stop_reason", None)
                return AIStreamChunk(
                    finish_reason=stop_reason,
                    usage=usage,
                )
            return None

        yield from _stream_sdk(
            sdk_call=lambda: client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                system=self._system_prompt or "",
                messages=[{"role": "user", "content": prompt}],
                stream=True,
                **kwargs,
            ),
            provider_name=self.provider_name,
            chunk_handler=chunk_handler,
        )
