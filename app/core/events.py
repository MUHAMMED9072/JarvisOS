"""Central event name constants and event data helpers for the JARVIS OS EventBus.

All AI-related event names are defined here as ``AIEvents`` class attributes
so that publishers and subscribers use the same strings without duplication.
"""

from __future__ import annotations

from typing import Any


class AIEvents:
    """AI event name constants for the EventBus."""

    # ------------------------------------------------------------------
    # Request / Response
    # ------------------------------------------------------------------
    REQUEST = "ai.request"
    RESPONSE = "ai.response"

    # ------------------------------------------------------------------
    # Streaming
    # ------------------------------------------------------------------
    STREAM_START = "ai.stream.start"
    STREAM_COMPLETE = "ai.stream.complete"
    STREAM_CANCEL = "ai.stream.cancel"

    # ------------------------------------------------------------------
    # Planning
    # ------------------------------------------------------------------
    PLAN_START = "ai.plan.start"
    PLAN_COMPLETE = "ai.plan.complete"
    PLAN_FAIL = "ai.plan.fail"

    # ------------------------------------------------------------------
    # Reasoning
    # ------------------------------------------------------------------
    REASON_START = "ai.reason.start"
    REASON_COMPLETE = "ai.reason.complete"
    REASON_FAIL = "ai.reason.fail"

    # ------------------------------------------------------------------
    # Tool calling
    # ------------------------------------------------------------------
    TOOL_CALL = "ai.tool.call"
    TOOL_RESULT = "ai.tool.result"

    # ------------------------------------------------------------------
    # Conversation lifecycle
    # ------------------------------------------------------------------
    CONVERSATION_CREATE = "ai.conversation.create"
    CONVERSATION_MESSAGE = "ai.conversation.message"

    # ------------------------------------------------------------------
    # Memory
    # ------------------------------------------------------------------
    MEMORY_STORE = "ai.memory.store"
    MEMORY_RETRIEVE = "ai.memory.retrieve"
