from __future__ import annotations

import json
import time
from typing import Any, AsyncGenerator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.ai.conversation import ConversationManager
from app.ai.manager import AIManager
from app.ai.router import ProviderStatus
from app.api.dependencies import get_service, require_service
from app.api.errors import NotFoundError, ServiceUnavailableError
from app.api.schemas import (
    ChatRequest,
    ChatResponse,
    ConversationCreateRequest,
    ConversationCreateResponse,
    ConversationListResponse,
    ConversationSummary,
    MessageListResponse,
    MessageResponse,
    ModelInfo,
    ModelListResponse,
    PlanRequest,
    PlanResponse,
    PlanStep,
    ProviderInfo,
    ProviderListResponse,
    ReasonRequest,
    ReasonResponse,
    ReasonStep,
    StreamChunk,
)

router = APIRouter(prefix="/api/v1/ai", tags=["AI"])

# ------------------------------------------------------------------
# Dependencies
# ------------------------------------------------------------------

AI_DEP = Depends(require_service("ai_manager"))


# ------------------------------------------------------------------
# Chat
# ------------------------------------------------------------------


@router.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    ai: AIManager = AI_DEP,
) -> ChatResponse:
    try:
        result = ai.ask(
            provider=body.provider,
            prompt=body.prompt,
            conversation_id=body.conversation_id,
            prompt_template=body.prompt_template,
            template_variables=body.template_variables,
        )
    except ValueError as exc:
        raise NotFoundError(str(exc))
    return ChatResponse(
        response=str(result),
        provider=result.provider,
        model=result.model,
        latency_ms=result.latency_ms,
        conversation_id=body.conversation_id,
        metadata=dict(result.metadata),
    )


# ------------------------------------------------------------------
# Streaming chat
# ------------------------------------------------------------------


@router.post("/chat/stream")
async def chat_stream(
    body: ChatRequest,
    ai: AIManager = AI_DEP,
) -> StreamingResponse:
    async def _generate() -> AsyncGenerator[str, None]:
        try:
            stream = ai.ask_stream(
                provider=body.provider or "openai",
                prompt=body.prompt,
                conversation_id=body.conversation_id,
                prompt_template=body.prompt_template,
                template_variables=body.template_variables,
            )
        except ValueError as exc:
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"
            yield "data: [DONE]\n\n"
            return

        for chunk in stream:
            sc = StreamChunk(content=chunk.content)
            yield f"data: {json.dumps(sc.model_dump())}\n\n"

        final = stream.final_response()
        meta = dict(final.metadata) if hasattr(final, 'metadata') else {}
        cr = ChatResponse(
            response=str(final),
            provider=final.provider,
            model=final.model,
            latency_ms=final.latency_ms,
            conversation_id=body.conversation_id,
            metadata=meta,
        )
        yield f"data: {json.dumps(cr.model_dump())}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ------------------------------------------------------------------
# Planning
# ------------------------------------------------------------------


@router.post("/plan", response_model=PlanResponse)
async def plan(
    body: PlanRequest,
    ai: AIManager = AI_DEP,
) -> PlanResponse:
    result = ai.plan(
        objective=body.objective,
        provider=body.provider,
        conversation_id=body.conversation_id,
        prompt_template=body.prompt_template,
        template_variables=body.template_variables,
        planning_prompt=body.planning_prompt,
    )
    steps = [
        PlanStep(
            step=s.step,
            action=s.action,
            reasoning=s.reasoning,
            expected_outcome=str(getattr(s, 'expected_outcome', '')),
        )
        for s in result.plan.steps
    ]
    return PlanResponse(
        steps=steps,
        provider=result.provider,
        model=result.model,
        duration_ms=result.duration_ms,
        valid=result.valid,
        validation_errors=list(result.validation_errors),
        metadata=dict(result.metadata),
    )


# ------------------------------------------------------------------
# Reasoning
# ------------------------------------------------------------------


@router.post("/reason", response_model=ReasonResponse)
async def reason(
    body: ReasonRequest,
    ai: AIManager = AI_DEP,
) -> ReasonResponse:
    try:
        result = ai.reason(
            objective=body.objective,
            provider=body.provider,
            conversation_id=body.conversation_id,
            prompt_template=body.prompt_template,
            template_variables=body.template_variables,
            reasoning_prompt=body.reasoning_prompt,
        )
    except ValueError as exc:
        raise NotFoundError(str(exc))
    steps = [
        ReasonStep(
            step=s.step,
            statement=s.statement,
            evidence=str(getattr(s, 'evidence', '')),
            conclusion=str(getattr(s, 'conclusion', '')),
        )
        for s in result.chain.steps
    ]
    return ReasonResponse(
        steps=steps,
        provider=result.provider,
        model=result.model,
        duration_ms=result.duration_ms,
        valid=result.valid,
        validation_errors=list(result.validation_errors),
        metadata=dict(result.metadata),
    )


# ------------------------------------------------------------------
# Conversations
# ------------------------------------------------------------------


@router.get("/conversations", response_model=ConversationListResponse)
async def list_conversations(
    ai: AIManager = AI_DEP,
) -> ConversationListResponse:
    cm = ai.conversation_manager
    conversations = [
        ConversationSummary(
            id=conv_id,
            provider=conv.provider,
            model=conv.model,
            message_count=len(conv.messages),
            created_at=conv.created_at,
            updated_at=conv.updated_at,
            system_prompt=conv.system_prompt,
            metadata=dict(conv.metadata),
        )
        for conv_id, conv in cm._conversations.items()
    ]
    conversations.sort(key=lambda c: c.updated_at, reverse=True)
    return ConversationListResponse(conversations=conversations)


@router.get("/conversations/{conversation_id}", response_model=ConversationSummary)
async def get_conversation(
    conversation_id: str,
    ai: AIManager = AI_DEP,
) -> ConversationSummary:
    conv = ai.conversation_manager.get(conversation_id)
    if conv is None:
        raise NotFoundError(f"Conversation {conversation_id!r} not found")
    return ConversationSummary(
        id=conv.conversation_id,
        provider=conv.provider,
        model=conv.model,
        message_count=len(conv.messages),
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        system_prompt=conv.system_prompt,
        metadata=dict(conv.metadata),
    )


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    ai: AIManager = AI_DEP,
) -> dict[str, str]:
    deleted = ai.conversation_manager.delete(conversation_id)
    if not deleted:
        raise NotFoundError(f"Conversation {conversation_id!r} not found")
    return {"status": "deleted", "id": conversation_id}


@router.post("/conversations", response_model=ConversationCreateResponse)
async def create_conversation(
    body: ConversationCreateRequest,
    ai: AIManager = AI_DEP,
) -> ConversationCreateResponse:
    conv = ai.create_conversation(
        provider=body.provider,
        model=body.model,
        system_prompt=body.system_prompt,
        max_messages=body.max_messages,
        metadata=body.metadata,
    )
    return ConversationCreateResponse(
        id=conv.conversation_id,
        provider=conv.provider,
        model=conv.model,
        created_at=conv.created_at,
    )


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=MessageListResponse,
)
async def get_conversation_messages(
    conversation_id: str,
    ai: AIManager = AI_DEP,
) -> MessageListResponse:
    conv = ai.conversation_manager.get(conversation_id)
    if conv is None:
        raise NotFoundError(f"Conversation {conversation_id!r} not found")
    messages = [
        MessageResponse(
            role=msg.role,
            content=msg.content,
            timestamp=msg.timestamp,
            metadata=dict(msg.metadata),
        )
        for msg in conv.messages
    ]
    return MessageListResponse(messages=messages)


# ------------------------------------------------------------------
# Providers
# ------------------------------------------------------------------


@router.get("/providers", response_model=ProviderListResponse)
async def list_providers(
    ai: AIManager = AI_DEP,
) -> ProviderListResponse:
    ai_router = ai.router
    providers: list[ProviderInfo] = []
    for name in sorted(ai_router.providers):
        p = ai_router.providers[name]
        caps = getattr(p, "capabilities", frozenset())
        status = ai_router.provider_status(name)
        available = status is ProviderStatus.AVAILABLE
        providers.append(
            ProviderInfo(
                name=name,
                model=getattr(p, "_model", ""),
                capabilities=sorted(c.name.lower() for c in caps),
                available=available,
            ),
        )
    return ProviderListResponse(providers=providers)


@router.get("/models", response_model=ModelListResponse)
async def list_models(
    ai: AIManager = AI_DEP,
) -> ModelListResponse:
    ai_router = ai.router
    models: list[ModelInfo] = []
    seen: set[tuple[str, str]] = set()
    for name in sorted(ai_router.providers):
        p = ai_router.providers[name]
        model = getattr(p, "_model", "")
        if model and (name, model) not in seen:
            seen.add((name, model))
            models.append(ModelInfo(provider=name, model=model))
    return ModelListResponse(models=models)
