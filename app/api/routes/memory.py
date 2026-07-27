from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import require_service
from app.api.errors import BadRequestError, NotFoundError
from app.api.schemas import (
    MemoryActionResponse,
    MemoryItemResponse,
    MemoryListResponse,
    MemoryRecentResponse,
    MemoryRememberRequest,
    MemoryRememberResponse,
    MemorySearchResponse,
    MemorySessionDetailResponse,
    MemorySessionInfo,
    MemorySessionListResponse,
)
from app.memory.manager import MemoryManager

router = APIRouter(prefix="/api/v1/memory", tags=["Memory"])

MEMORY_DEP = Depends(require_service("memory"))


def _item_to_response(item: dict[str, Any]) -> MemoryItemResponse:
    return MemoryItemResponse(
        role=item.get("role", ""),
        content=item.get("content", ""),
        metadata=item.get("metadata", {}),
        timestamp=item.get("timestamp", ""),
    )


# ------------------------------------------------------------------
# List all stored memories
# ------------------------------------------------------------------


@router.get("", response_model=MemoryListResponse)
async def list_memories(
    mem: MemoryManager = MEMORY_DEP,
) -> MemoryListResponse:
    items = [ _item_to_response(it) for it in mem.history.get_all() ]
    return MemoryListResponse(items=items, count=len(items))


# ------------------------------------------------------------------
# Search memories by content
# ------------------------------------------------------------------


@router.get("/search", response_model=MemorySearchResponse)
async def search_memories(
    q: str = Query(..., min_length=1, description="Search query"),
    mem: MemoryManager = MEMORY_DEP,
) -> MemorySearchResponse:
    results = mem.search(q)
    items = [ _item_to_response(it) for it in results ]
    return MemorySearchResponse(query=q, items=items, count=len(items))


# ------------------------------------------------------------------
# Recent memories
# ------------------------------------------------------------------


@router.get("/recent", response_model=MemoryRecentResponse)
async def recent_memories(
    limit: int = Query(10, ge=1, le=100, description="Number of recent items"),
    mem: MemoryManager = MEMORY_DEP,
) -> MemoryRecentResponse:
    results = mem.get_recent(limit)
    items = [ _item_to_response(it) for it in results ]
    return MemoryRecentResponse(items=items, count=len(items))


# ------------------------------------------------------------------
# Manually store a memory
# ------------------------------------------------------------------


@router.post("/remember", response_model=MemoryRememberResponse)
async def remember(
    body: MemoryRememberRequest,
    mem: MemoryManager = MEMORY_DEP,
) -> MemoryRememberResponse:
    if body.role not in ("user", "assistant", "system"):
        raise BadRequestError(
            f"Invalid role {body.role!r}. Must be 'user', 'assistant', or 'system'",
        )
    mem.remember(
        role=body.role,
        content=body.content,
        metadata=body.metadata,
    )
    return MemoryRememberResponse(
        status="ok",
        message="Memory stored",
    )


# ------------------------------------------------------------------
# List sessions
# ------------------------------------------------------------------


@router.get("/sessions", response_model=MemorySessionListResponse)
async def list_sessions(
    mem: MemoryManager = MEMORY_DEP,
) -> MemorySessionListResponse:
    return MemorySessionListResponse(
        sessions=[
            MemorySessionInfo(
                id="current",
                message_count=len(mem.get_session_messages()),
                last_intent=mem.session.last_intent,
                last_application=mem.session.last_application,
                last_skill=mem.session.last_skill,
            ),
        ],
    )


# ------------------------------------------------------------------
# Get session detail
# ------------------------------------------------------------------


@router.get("/sessions/{session_id}", response_model=MemorySessionDetailResponse)
async def get_session(
    session_id: str,
    mem: MemoryManager = MEMORY_DEP,
) -> MemorySessionDetailResponse:
    if session_id != "current":
        raise NotFoundError(f"Session {session_id!r} not found")
    messages = [
        _item_to_response(msg)
        for msg in mem.get_session_messages()
    ]
    return MemorySessionDetailResponse(
        id="current",
        messages=messages,
        last_intent=mem.session.last_intent,
        last_entities=dict(mem.session.last_entities),
        last_application=mem.session.last_application,
        last_skill=mem.session.last_skill,
        message_count=len(messages),
    )


# ------------------------------------------------------------------
# Delete a session
# ------------------------------------------------------------------


@router.delete("/sessions/{session_id}", response_model=MemoryActionResponse)
async def delete_session(
    session_id: str,
    mem: MemoryManager = MEMORY_DEP,
) -> MemoryActionResponse:
    if session_id != "current":
        raise NotFoundError(f"Session {session_id!r} not found")
    mem.session.clear()
    return MemoryActionResponse(
        status="ok",
        message="Session cleared",
    )


# ------------------------------------------------------------------
# Clear all memory
# ------------------------------------------------------------------


@router.delete("", response_model=MemoryActionResponse)
async def clear_memory(
    mem: MemoryManager = MEMORY_DEP,
) -> MemoryActionResponse:
    mem.clear()
    return MemoryActionResponse(
        status="ok",
        message="All memory cleared",
    )
