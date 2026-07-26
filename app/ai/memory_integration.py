from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from app.ai.manager import AIManager
from app.ai.providers.base import AIResponse


logger = logging.getLogger(__name__)


@dataclass
class MemoryContextConfig:
    """Configuration for memory context retrieval."""
    include_session_messages: bool = True
    include_memory_search: bool = True
    max_session_messages: int = 6
    max_search_results: int = 3


def _try_get_memory_manager(registry) -> Any:
    """Best-effort retrieval of ``MemoryManager`` from *registry*.

    Returns ``None`` when the service is unavailable, allowing
    memory-aware operations to degrade gracefully.
    """
    try:
        return registry.get("memory")
    except Exception:
        logger.debug("MemoryManager is not available in the registry")
        return None


class MemoryAwareAI:
    """AIManager wrapper that automatically integrates with
    MemoryManager for context retrieval and memory recording.

    Memory failures are always non-fatal: they are logged but never
    prevent AI execution.
    """

    def __init__(
        self,
        ai_manager: AIManager,
        memory_manager: Any | None = None,
        config: MemoryContextConfig | None = None,
    ) -> None:
        self._ai = ai_manager
        self._memory = memory_manager
        self._config = config or MemoryContextConfig()

    # ------------------------------------------------------------------
    # Chat
    # ------------------------------------------------------------------

    def ask(
        self,
        provider: str,
        prompt: str = "",
        *,
        conversation_id: str | None = None,
        prompt_template: str | None = None,
        template_variables: dict[str, str] | None = None,
        schema: Any = None,
        tools: list | None = None,
        required_capabilities: Any = None,
    ) -> AIResponse:
        augmented = self._augment_prompt(prompt)
        result = self._ai.ask(
            provider, augmented,
            conversation_id=conversation_id,
            prompt_template=prompt_template,
            template_variables=template_variables,
            schema=schema,
            tools=tools,
            required_capabilities=required_capabilities,
        )
        self._record(
            prompt, str(result),
            provider=getattr(result, 'provider', ''),
            model=getattr(result, 'model', ''),
            conversation_id=conversation_id,
        )
        return result

    # ------------------------------------------------------------------
    # Streaming
    # ------------------------------------------------------------------

    def ask_stream(
        self,
        provider: str,
        prompt: str = "",
        *,
        conversation_id: str | None = None,
        prompt_template: str | None = None,
        template_variables: dict[str, str] | None = None,
    ) -> Any:
        augmented = self._augment_prompt(prompt)

        stream = self._ai.ask_stream(
            provider, augmented,
            conversation_id=conversation_id,
            prompt_template=prompt_template,
            template_variables=template_variables,
        )

        return _MemoryRecordingStreamWrapper(
            stream, self, prompt, provider,
            conversation_id=conversation_id,
        )

    # ------------------------------------------------------------------
    # Plan
    # ------------------------------------------------------------------

    def plan(
        self,
        objective: str,
        *,
        provider: str | None = None,
        conversation_id: str | None = None,
        prompt_template: str | None = None,
        template_variables: dict[str, str] | None = None,
        planning_prompt: str | None = None,
        required_capabilities: Any = None,
    ) -> Any:
        augmented = self._augment_prompt(objective)
        result = self._ai.plan(
            augmented,
            provider=provider,
            conversation_id=conversation_id,
            prompt_template=prompt_template,
            template_variables=template_variables,
            planning_prompt=planning_prompt,
            required_capabilities=required_capabilities,
        )
        plan_text = str(result.plan) if hasattr(result, "plan") else str(result)
        self._record(
            objective, plan_text,
            provider=getattr(result, 'provider', ''),
            model=getattr(result, 'model', ''),
            conversation_id=conversation_id,
            metadata={"plan_valid": getattr(result, 'valid', False)},
        )
        return result

    # ------------------------------------------------------------------
    # Reason
    # ------------------------------------------------------------------

    def reason(
        self,
        objective: str,
        *,
        provider: str | None = None,
        conversation_id: str | None = None,
        prompt_template: str | None = None,
        template_variables: dict[str, str] | None = None,
        reasoning_prompt: str | None = None,
        required_capabilities: Any = None,
    ) -> Any:
        augmented = self._augment_prompt(objective)
        result = self._ai.reason(
            augmented,
            provider=provider,
            conversation_id=conversation_id,
            prompt_template=prompt_template,
            template_variables=template_variables,
            reasoning_prompt=reasoning_prompt,
            required_capabilities=required_capabilities,
        )
        chain_text = str(result.chain) if hasattr(result, "chain") else str(result)
        self._record(
            objective, chain_text,
            provider=getattr(result, 'provider', ''),
            model=getattr(result, 'model', ''),
            conversation_id=conversation_id,
            metadata={"reasoning_valid": getattr(result, 'valid', False)},
        )
        return result

    # ------------------------------------------------------------------
    # Context retrieval & prompt augmentation
    # ------------------------------------------------------------------

    def _augment_prompt(self, prompt: str) -> str:
        """Inject relevant memory context into *prompt*.

        Returns the augmented prompt, or the original *prompt* when
        memory is unavailable or no context is found.
        """
        if self._memory is None:
            return prompt

        context_parts: list[str] = []

        try:
            if self._config.include_session_messages:
                session = self._memory.get_session_messages()
                if session:
                    recent = session[-self._config.max_session_messages:]
                    lines = [
                        f"{m['role']}: {m['content']}"
                        for m in recent
                    ]
                    context_parts.append(
                        "Previous conversation:\n" + "\n".join(lines),
                    )
        except Exception:
            logger.exception("Failed to retrieve session messages")

        try:
            if self._config.include_memory_search:
                results = self._memory.search(prompt)
                if results:
                    top = results[-self._config.max_search_results:]
                    lines = [
                        f"- {r.get('role', '?')}: {r.get('content', '')[:200]}"
                        for r in top
                    ]
                    context_parts.append(
                        "Related memories:\n" + "\n".join(lines),
                    )
        except Exception:
            logger.exception("Failed to search memory")

        if not context_parts:
            return prompt

        context_block = "\n\n".join(context_parts)
        return f"{context_block}\n\n{prompt}"

    # ------------------------------------------------------------------
    # Memory recording
    # ------------------------------------------------------------------

    def _record(
        self,
        user_message: str,
        assistant_message: str,
        *,
        provider: str = "",
        model: str = "",
        conversation_id: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        if self._memory is None:
            return
        try:
            meta: dict = {"provider": provider, "model": model}
            if conversation_id:
                meta["conversation_id"] = conversation_id
            if metadata:
                meta.update(metadata)
            self._memory.remember("user", user_message, metadata=meta)
            self._memory.remember(
                "assistant", assistant_message, metadata=meta,
            )
        except Exception:
            logger.exception("Failed to record memory")


class _MemoryRecordingStreamWrapper:
    """Wraps a stream to record memory after successful completion."""

    def __init__(
        self,
        stream: Any,
        memory_ai: MemoryAwareAI,
        original_prompt: str,
        provider: str,
        *,
        conversation_id: str | None = None,
    ) -> None:
        self._stream = stream
        self._memory_ai = memory_ai
        self._prompt = original_prompt
        self._provider = provider
        self._conv_id = conversation_id

    def __iter__(self):
        return self

    def __next__(self):
        return next(self._stream)

    def __getattr__(self, name: str):
        return getattr(self._stream, name)

    def final_response(self) -> AIResponse:
        result = self._stream.final_response()
        self._memory_ai._record(
            self._prompt, str(result),
            provider=getattr(result, 'provider', ''),
            model=getattr(result, 'model', ''),
            conversation_id=self._conv_id,
        )
        return result

    def cancel(self) -> None:
        self._stream.cancel()
