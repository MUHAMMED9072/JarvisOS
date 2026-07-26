from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING, Generator

if TYPE_CHECKING:
    from .structured import StructuredSchema
    from .tools import ToolDefinition

from .conversation import Conversation, ConversationManager
from .diagnostics import MetricsCollector
from .planning import (
    DEFAULT_PLAN_PROMPT,
    PLAN_SCHEMA,
    Plan,
    PlanResult,
    PlanValidationError,
    parse_plan,
    validate_plan,
)
from .providers.base import (
    AIProviderError,
    AIResponse,
    AIStreamChunk,
    AIStreamResponse,
    ProviderCapability,
)
from .reasoning import (
    DEFAULT_REASONING_PROMPT,
    REASONING_SCHEMA,
    ReasoningChain,
    ReasoningResult,
    parse_reasoning,
    validate_reasoning,
)
from .router import AIRouter
from .templates import (
    PromptRenderResult,
    PromptTemplateRegistry,
    render_template,
)
from app.core.config import Config
from app.core.events import AIEvents


class _ConversationStreamWrapper(AIStreamResponse):
    """Wraps a stream to append the assistant message to a conversation
    only after successful completion."""

    def __init__(
        self,
        provider: str,
        model: str,
        generator: Generator[AIStreamChunk, None, None],
        conversation_id: str,
        manager: ConversationManager,
        template_metadata: dict | None = None,
    ) -> None:
        super().__init__(provider, model, generator)
        self._conv_id = conversation_id
        self._conv_manager = manager
        self._template_meta = template_metadata or {}

    def __next__(self) -> AIStreamChunk:
        try:
            return super().__next__()
        except StopIteration:
            result = self.final_response()
            if self._template_meta:
                result.metadata.update(self._template_meta)
            self._conv_manager.add_message(
                self._conv_id, "assistant", str(result),
                metadata={
                    "provider": result.provider,
                    "model": result.model,
                },
            )
            self._conv_manager.update_timestamp(self._conv_id)
            raise

    def cancel(self) -> None:
        super().cancel()
        self._conv_manager.update_timestamp(self._conv_id)


class _MetadataStreamWrapper(AIStreamResponse):
    """Wraps a stream to inject template metadata into the final response."""

    def __init__(
        self,
        stream: AIStreamResponse,
        template_metadata: dict | None = None,
    ) -> None:
        super().__init__(stream._provider, stream._model, stream._generator)
        self._template_meta = template_metadata or {}

    def final_response(self) -> AIResponse:
        result = super().final_response()
        if self._template_meta:
            result.metadata.update(self._template_meta)
        return result

    def cancel(self) -> None:
        super().cancel()


class _EventStreamWrapper(AIStreamResponse):
    """Wraps a stream to publish STREAM_COMPLETE / STREAM_CANCEL events."""

    def __init__(
        self,
        stream: AIStreamResponse,
        event_bus: object,
        stream_id: str,
        **event_data: object,
    ) -> None:
        super().__init__(stream._provider, stream._model, stream._generator)
        self._event_bus = event_bus
        self._stream_id = stream_id
        self._event_data = event_data

    def __next__(self) -> AIStreamChunk:
        try:
            return super().__next__()
        except StopIteration:
            try:
                result = self.final_response()
                self._event_bus.publish(
                    AIEvents.STREAM_COMPLETE,
                    {
                        "stream_id": self._stream_id,
                        "provider": result.provider,
                        "model": result.model,
                        "final_length": len(str(result)),
                    },
                )
            except Exception:
                pass
            raise

    def cancel(self) -> None:
        super().cancel()
        try:
            self._event_bus.publish(
                AIEvents.STREAM_CANCEL,
                {
                    "stream_id": self._stream_id,
                    "provider": self._provider,
                    "model": self._model,
                },
            )
        except Exception:
            pass


class _MetricsStreamWrapper(AIStreamResponse):
    """Wraps a stream to record streaming metrics."""

    def __init__(
        self,
        stream: AIStreamResponse,
        metrics: MetricsCollector | None,
        provider: str,
    ) -> None:
        super().__init__(stream._provider, stream._model, stream._generator)
        self._wrapped = stream
        self._metrics = metrics
        self._metrics_provider = provider

    def __next__(self) -> AIStreamChunk:
        try:
            return self._wrapped.__next__()
        except StopIteration:
            if self._metrics:
                self._metrics.streaming.record(True)
            raise

    def cancel(self) -> None:
        self._wrapped.cancel()
        if self._metrics:
            self._metrics.streaming.record(False)

    def final_response(self) -> AIResponse:
        return self._wrapped.final_response()


def _try_parse_json(text: str) -> dict:
    """Best-effort JSON extraction from *text*."""
    text = text.strip()
    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Try extracting JSON from markdown code fence
    import re
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    # Try finding first { ... } block
    brace_match = re.search(r"\{.*\}", text, re.DOTALL)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            pass
    return {}


class AIManager:
    def __init__(
        self,
        event_bus=None,
        conversation_manager=None,
        template_registry=None,
        router=None,
        metrics_collector=None,
    ):
        self.router = router or AIRouter()
        self.conversation_manager = (
            conversation_manager or ConversationManager()
        )
        self.template_registry = (
            template_registry or PromptTemplateRegistry()
        )
        self._event_bus = event_bus
        self._metrics = metrics_collector

    def ask(
        self,
        provider: str | None = None,
        prompt: str = "",
        *,
        prompt_template: str | None = None,
        template_variables: dict[str, str] | None = None,
        conversation_id: str | None = None,
        required_capabilities: frozenset[ProviderCapability] | None = None,
        tools: list[ToolDefinition] | None = None,
        schema: StructuredSchema | None = None,
    ) -> AIResponse:
        rendered_prompt, template_meta = self._resolve_prompt(
            prompt, prompt_template, template_variables,
        )
        effective_required = required_capabilities or frozenset()
        if tools:
            effective_required = frozenset(effective_required) | frozenset({ProviderCapability.FUNCTION_CALLING})
        if schema:
            effective_required = frozenset(effective_required) | frozenset({ProviderCapability.JSON_OUTPUT})

        if conversation_id is None:
            self._publish(AIEvents.REQUEST,
                prompt_length=len(rendered_prompt),
                provider=provider,
                has_tools=tools is not None,
                has_schema=schema is not None,
                conversation_id=conversation_id,
            )
            _start = time.monotonic()
            try:
                result = self._route_or_ask(provider, rendered_prompt, effective_required, tools, schema)
            except Exception:
                if self._metrics:
                    self._metrics.requests.record(False)
                    self._metrics.errors.record(True)
                raise
            _latency = (time.monotonic() - _start) * 1000
            if self._metrics:
                self._metrics.requests.record(True, _latency)
            if template_meta:
                result.metadata.update(template_meta)
            self._publish(AIEvents.RESPONSE,
                provider=result.provider,
                model=result.model,
                latency_ms=result.latency_ms,
                response_length=len(str(result)),
                conversation_id=conversation_id,
            )
            return result

        conv = self.conversation_manager.get(conversation_id)
        if conv is None:
            raise ValueError(
                f"Conversation {conversation_id!r} not found"
            )

        self.conversation_manager.add_message(
            conversation_id, "user", rendered_prompt,
            metadata={"template_name": template_meta.get("template_name")} if template_meta else None,
        )

        history_prompt = self._build_prompt_from_conversation(conv)
        self._publish(AIEvents.REQUEST,
            prompt_length=len(rendered_prompt),
            provider=provider,
            has_tools=tools is not None,
            has_schema=schema is not None,
            conversation_id=conversation_id,
        )
        _start = time.monotonic()
        try:
            result = self._route_or_ask(provider, history_prompt, effective_required, tools, schema)
        except Exception:
            if self._metrics:
                self._metrics.requests.record(False)
                self._metrics.errors.record(True)
            raise
        _latency = (time.monotonic() - _start) * 1000
        if self._metrics:
            self._metrics.requests.record(True, _latency)

        if template_meta:
            result.metadata.update(template_meta)

        self.conversation_manager.add_message(
            conversation_id, "assistant", str(result),
            metadata={"provider": result.provider, "model": result.model},
        )
        self.conversation_manager.update_timestamp(conversation_id)

        self._publish(AIEvents.RESPONSE,
            provider=result.provider,
            model=result.model,
            latency_ms=result.latency_ms,
            response_length=len(str(result)),
            conversation_id=conversation_id,
        )

        return result

    def _route_or_ask(
        self,
        provider: str | None,
        prompt: str,
        required_capabilities: frozenset[ProviderCapability],
        tools: list[ToolDefinition] | None = None,
        schema: StructuredSchema | None = None,
    ) -> AIResponse:
        """Dispatch *prompt* via routing when *provider* is None, or to a
        specific provider otherwise."""
        if provider is None:
            return self.router.ask_routed(
                prompt,
                required_capabilities=required_capabilities,
                tools=tools,
                schema=schema,
            )
        self._validate_capabilities(provider, required_capabilities)
        return self.router.ask(provider, prompt, tools=tools, schema=schema)

    def _publish(self, event: str, **data: object) -> None:
        """Publish an AI event to the EventBus if configured.

        Failures are silently ignored so that event publishing never
        interrupts AI operations.
        """
        if self._event_bus is None:
            return
        try:
            self._event_bus.publish(event, data)
        except Exception:
            pass

    def ask_stream(
        self,
        provider: str,
        prompt: str = "",
        *,
        prompt_template: str | None = None,
        template_variables: dict[str, str] | None = None,
        conversation_id: str | None = None,
    ) -> AIStreamResponse:
        rendered_prompt, template_meta = self._resolve_prompt(
            prompt, prompt_template, template_variables,
        )
        self._validate_capabilities(provider, {ProviderCapability.STREAMING})

        stream_id = f"{provider}-{time.monotonic_ns()}"

        if self._metrics:
            self._metrics.streaming.record(True)

        self._publish(AIEvents.STREAM_START,
            provider=provider,
            prompt_length=len(rendered_prompt),
            conversation_id=conversation_id,
            stream_id=stream_id,
        )

        if conversation_id is None:
            stream = self.router.ask_stream(provider, rendered_prompt)
            wrapped: AIStreamResponse = _MetadataStreamWrapper(stream, template_meta)
            if self._event_bus:
                wrapped = _EventStreamWrapper(wrapped, self._event_bus, stream_id)
            if self._metrics:
                wrapped = _MetricsStreamWrapper(wrapped, self._metrics, provider)
            return wrapped

        conv = self.conversation_manager.get(conversation_id)
        if conv is None:
            raise ValueError(
                f"Conversation {conversation_id!r} not found"
            )

        self.conversation_manager.add_message(
            conversation_id, "user", rendered_prompt,
            metadata={"template_name": template_meta.get("template_name")} if template_meta else None,
        )

        history_prompt = self._build_prompt_from_conversation(conv)
        stream = self.router.ask_stream(provider, history_prompt)

        wrapped: AIStreamResponse = _ConversationStreamWrapper(
            stream._provider,
            stream._model,
            stream._generator,
            conversation_id,
            self.conversation_manager,
            template_metadata=template_meta,
        )

        if self._event_bus:
            wrapped = _EventStreamWrapper(wrapped, self._event_bus, stream_id)

        if self._metrics:
            wrapped = _MetricsStreamWrapper(wrapped, self._metrics, provider)

        return wrapped

    def _resolve_prompt(
        self,
        prompt: str,
        prompt_template: str | None = None,
        template_variables: dict[str, str] | None = None,
    ) -> tuple[str, dict]:
        """Return (rendered_prompt, template_metadata).

        When *prompt_template* is given, renders the template and returns
        the result.  Otherwise returns *prompt* unchanged with empty metadata.
        """
        if prompt_template is None:
            return prompt, {}

        tmpl = self.template_registry.get(prompt_template)
        if tmpl is None:
            raise ValueError(
                f"Prompt template {prompt_template!r} is not registered"
            )

        result: PromptRenderResult = render_template(tmpl, template_variables)
        meta: dict = {
            "template_name": result.template_name,
            "render_duration_ms": result.render_duration_ms,
            "template_variables": list(result.variables_used),
        }
        if tmpl.metadata and "version" in tmpl.metadata:
            meta["template_version"] = tmpl.metadata["version"]
        return result.text, meta

    def create_conversation(
        self,
        provider: str = "",
        model: str = "",
        system_prompt: str = "",
        max_messages: int | None = None,
        metadata: dict | None = None,
    ) -> Conversation:
        if max_messages is None:
            max_messages = Config.AI.conversation.max_messages
        conv = self.conversation_manager.create(
            provider=provider,
            model=model,
            system_prompt=system_prompt,
            max_messages=max_messages,
            metadata=metadata,
        )
        self._publish(AIEvents.CONVERSATION_CREATE,
            conversation_id=conv.conversation_id,
            provider=provider,
            model=model,
        )
        return conv

    def plan(
        self,
        objective: str,
        *,
        provider: str | None = None,
        conversation_id: str | None = None,
        prompt_template: str | None = None,
        template_variables: dict[str, str] | None = None,
        planning_prompt: str | None = None,
        required_capabilities: frozenset[ProviderCapability] | None = None,
    ) -> PlanResult:
        if conversation_id is not None:
            conv = self.conversation_manager.get(conversation_id)
            if conv is None:
                raise ValueError(
                    f"Conversation {conversation_id!r} not found"
                )

        base_caps = frozenset({
            ProviderCapability.REASONING,
            ProviderCapability.JSON_OUTPUT,
        })
        effective_caps = base_caps | (required_capabilities or frozenset())

        # Build the planning prompt
        if prompt_template is not None:
            rendered, template_meta = self._resolve_prompt(
                "", prompt_template, template_variables,
            )
            final_prompt = rendered
        elif planning_prompt is not None:
            final_prompt = planning_prompt.format(objective=objective)
            template_meta = {}
        else:
            final_prompt = DEFAULT_PLAN_PROMPT.format(objective=objective)
            template_meta = {}

        self._publish(AIEvents.PLAN_START,
            objective=objective,
            provider=provider,
            conversation_id=conversation_id,
        )

        try:
            _pstart = time.monotonic()
            if provider is None:
                result = self.router.ask_routed(
                    final_prompt,
                    required_capabilities=effective_caps,
                    schema=PLAN_SCHEMA,
                )
            else:
                self._validate_capabilities(provider, effective_caps)
                result = self.router.ask(
                    provider, final_prompt, schema=PLAN_SCHEMA,
                )
        except Exception as exc:
            if self._metrics:
                self._metrics.planning.record(False)
            self._publish(AIEvents.PLAN_FAIL,
                objective=objective,
                error=str(exc),
                provider=provider,
            )
            raise

        if self._metrics:
            _platency = (time.monotonic() - _pstart) * 1000
            self._metrics.planning.record(True, _platency)

        # Parse and validate the plan
        raw = result.metadata.get("structured")
        if raw and isinstance(raw, dict) and raw.get("data"):
            plan_data = raw["data"]
        else:
            plan_data = _try_parse_json(str(result))

        start = time.monotonic()
        plan = parse_plan(plan_data, provider=result.provider, model=result.model)
        validation = validate_plan(plan)
        duration = (time.monotonic() - start) * 1000

        # Merge metadata
        meta: dict = {
            "provider": result.provider,
            "model": result.model,
            "planning_duration_ms": duration,
            "validation_status": "valid" if validation.valid else "invalid",
        }
        routing_strategy = result.metadata.get("routing_strategy")
        if routing_strategy:
            meta["routing_strategy"] = routing_strategy
        if template_meta:
            meta.update(template_meta)
        if conversation_id:
            meta["conversation_id"] = conversation_id

        self._publish(AIEvents.PLAN_COMPLETE,
            provider=result.provider,
            model=result.model,
            num_steps=len(plan.steps),
            valid=validation.valid,
            duration_ms=duration,
            conversation_id=conversation_id,
        )

        return PlanResult(
            plan=plan,
            provider=result.provider,
            model=result.model,
            duration_ms=result.latency_ms,
            valid=validation.valid,
            validation_errors=list(validation.errors),
            metadata=meta,
        )

    def reason(
        self,
        objective: str,
        *,
        provider: str | None = None,
        conversation_id: str | None = None,
        prompt_template: str | None = None,
        template_variables: dict[str, str] | None = None,
        reasoning_prompt: str | None = None,
        required_capabilities: frozenset[ProviderCapability] | None = None,
    ) -> ReasoningResult:
        if conversation_id is not None:
            conv = self.conversation_manager.get(conversation_id)
            if conv is None:
                raise ValueError(
                    f"Conversation {conversation_id!r} not found"
                )

        base_caps = frozenset({
            ProviderCapability.REASONING,
            ProviderCapability.JSON_OUTPUT,
        })
        effective_caps = base_caps | (required_capabilities or frozenset())

        if prompt_template is not None:
            rendered, template_meta = self._resolve_prompt(
                "", prompt_template, template_variables,
            )
            final_prompt = rendered
        elif reasoning_prompt is not None:
            final_prompt = reasoning_prompt.format(objective=objective)
            template_meta = {}
        else:
            final_prompt = DEFAULT_REASONING_PROMPT.format(objective=objective)
            template_meta = {}

        self._publish(AIEvents.REASON_START,
            objective=objective,
            provider=provider,
            conversation_id=conversation_id,
        )

        try:
            _rstart = time.monotonic()
            if provider is None:
                result = self.router.ask_routed(
                    final_prompt,
                    required_capabilities=effective_caps,
                    schema=REASONING_SCHEMA,
                )
            else:
                self._validate_capabilities(provider, effective_caps)
                result = self.router.ask(
                    provider, final_prompt, schema=REASONING_SCHEMA,
                )
        except Exception as exc:
            if self._metrics:
                self._metrics.reasoning.record(False)
            self._publish(AIEvents.REASON_FAIL,
                objective=objective,
                error=str(exc),
                provider=provider,
            )
            raise

        if self._metrics:
            _rlatency = (time.monotonic() - _rstart) * 1000
            self._metrics.reasoning.record(True, _rlatency)

        raw = result.metadata.get("structured")
        if raw and isinstance(raw, dict) and raw.get("data"):
            chain_data = raw["data"]
        else:
            chain_data = _try_parse_json(str(result))

        start = time.monotonic()
        chain = parse_reasoning(
            chain_data, provider=result.provider, model=result.model,
        )
        validation = validate_reasoning(chain)
        duration = (time.monotonic() - start) * 1000

        meta: dict = {
            "provider": result.provider,
            "model": result.model,
            "reasoning_duration_ms": duration,
            "validation_status": "valid" if validation.valid else "invalid",
        }
        routing_strategy = result.metadata.get("routing_strategy")
        if routing_strategy:
            meta["routing_strategy"] = routing_strategy
        if template_meta:
            meta.update(template_meta)
        if conversation_id:
            meta["conversation_id"] = conversation_id

        self._publish(AIEvents.REASON_COMPLETE,
            provider=result.provider,
            model=result.model,
            num_steps=len(chain.steps),
            valid=validation.valid,
            duration_ms=duration,
            conversation_id=conversation_id,
        )

        return ReasoningResult(
            chain=chain,
            provider=result.provider,
            model=result.model,
            duration_ms=result.latency_ms,
            valid=validation.valid,
            validation_errors=list(validation.errors),
            metadata=meta,
        )

    def _validate_capabilities(
        self,
        provider: str,
        required: frozenset[ProviderCapability] | set[ProviderCapability] | None,
    ) -> None:
        """Raise ``AIProviderError`` if *provider* does not support all
        *required* capabilities.

        Validation is skipped when the provider does not declare any
        capabilities (backward-compatible with test mocks).
        """
        if not required:
            return
        provider_caps = self.router.provider_capabilities(provider)
        if not provider_caps:
            return
        missing = frozenset(required) - provider_caps
        if missing:
            missing_names = sorted(c.name for c in missing)
            raise AIProviderError(
                f"Provider {provider!r} does not support required "
                f"capabilities: {', '.join(missing_names)}"
            )

    @staticmethod
    def _build_prompt_from_conversation(conv: Conversation) -> str:
        parts: list[str] = []
        if conv.system_prompt:
            parts.append(f"system: {conv.system_prompt}")
        for msg in conv.messages:
            parts.append(f"{msg.role}: {msg.content}")
        return "\n".join(parts)
