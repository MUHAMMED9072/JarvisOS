"""Central event name constants and event data helpers for the JARVIS OS EventBus.

All event-related constants are defined here so that publishers and
subscribers use the same strings without duplication.
"""

from __future__ import annotations

from typing import Any


class KernelEvents:
    """Kernel lifecycle event name constants."""

    BOOT_STARTED = "kernel.boot.started"
    BOOT_COMPLETE = "kernel.boot.complete"
    BOOT_FAILED = "kernel.boot.failed"
    SHUTDOWN_STARTED = "kernel.shutdown.started"
    SHUTDOWN_COMPLETE = "kernel.shutdown.complete"


class SystemEvents:
    """System-wide event name constants."""

    HEALTH_CHECK = "system.health.check"
    HEALTH_OK = "system.health.ok"
    HEALTH_DEGRADED = "system.health.degraded"
    HEALTH_FAILED = "system.health.failed"
    CONFIG_CHANGED = "system.config.changed"
    CONFIG_RELOADED = "system.config.reloaded"


class LifecycleEvents:
    """Service lifecycle event name constants."""

    SERVICE_REGISTERED = "lifecycle.service.registered"
    SERVICE_STARTING = "lifecycle.service.starting"
    SERVICE_STARTED = "lifecycle.service.started"
    SERVICE_STOPPING = "lifecycle.service.stopping"
    SERVICE_STOPPED = "lifecycle.service.stopped"
    SERVICE_FAILED = "lifecycle.service.failed"


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


class AuthEvents:
    """Authentication event name constants for the EventBus."""

    AUTH_SUCCESS = "auth.success"
    AUTH_FAILURE = "auth.failure"
    AUTH_LOGOUT = "auth.logout"
    AUTH_EXPIRED = "auth.expired"
    AUTH_DENIED = "auth.denied"
    AUTH_REFRESH = "auth.refresh"


class PluginConfigEvents:
    """Plugin configuration event name constants for the EventBus."""

    CHANGED = "plugin.config.changed"
    LOADED = "plugin.config.loaded"
    SAVED = "plugin.config.saved"
    RELOADED = "plugin.config.reloaded"
    VALIDATION_ERROR = "plugin.config.validation_error"


class WSReliabilityEvents:
    """WebSocket reliability & resilience event name constants for the EventBus."""

    ACK_RECEIVED = "ws.ack.received"
    ACK_TIMEOUT = "ws.ack.timeout"
    RETRY_EXHAUSTED = "ws.retry.exhausted"
    RETRY_SCHEDULED = "ws.retry.scheduled"
    RECONNECT_SUCCESS = "ws.reconnect.success"
    RECONNECT_FAIL = "ws.reconnect.fail"
    RECONNECT_TOKEN_GENERATED = "ws.reconnect.token_generated"
    RECONNECT_TOKEN_REVOKED = "ws.reconnect.token_revoked"
    OFFLINE_QUEUE_DRAINED = "ws.offline_queue.drained"
    OFFLINE_QUEUE_OVERFLOW = "ws.offline_queue.overflow"
    STATS_REPORT = "ws.stats.report"
    LATENCY_UPDATE = "ws.latency.update"


class WSProductionEvents:
    """WebSocket production features & observability event name constants."""

    METRICS_UPDATED = "ws.metrics.updated"
    HEALTH_CHANGED = "ws.health.changed"
    DIAGNOSTICS_GENERATED = "ws.diagnostics.generated"
    MAINTENANCE_COMPLETED = "ws.maintenance.completed"
