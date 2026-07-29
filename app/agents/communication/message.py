from __future__ import annotations

import enum
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

# ── Message types ────────────────────────────────────────────────────


class MessageType(enum.Enum):
    REQUEST = "request"
    RESPONSE = "response"
    DELEGATE = "delegate"
    STATUS = "status"
    ESCALATE = "escalate"
    VOTE_REQUEST = "vote_request"
    VOTE = "vote"
    NEGOTIATE = "negotiate"
    CONSENSUS = "consensus"
    SHARE_MEMORY = "share_memory"
    SHARE_PLAN = "share_plan"
    SHARE_RESULT = "share_result"
    BROADCAST = "broadcast"
    HEARTBEAT = "heartbeat"
    HEALTH = "health"
    ERROR = "error"
    METRICS = "metrics"


class DeliveryGuarantee(enum.Enum):
    AT_MOST_ONCE = "at_most_once"
    AT_LEAST_ONCE = "at_least_once"
    EXACTLY_ONCE = "exactly_once"


# ── Message Schema ───────────────────────────────────────────────────

MESSAGE_SCHEMAS: dict[MessageType, list[str]] = {
    MessageType.REQUEST: ["sender", "target", "action", "payload"],
    MessageType.RESPONSE: ["sender", "target", "status", "payload"],
    MessageType.DELEGATE: ["sender", "target", "task_id", "payload"],
    MessageType.STATUS: ["sender", "status", "details"],
    MessageType.ESCALATE: ["sender", "target", "issue", "details"],
    MessageType.VOTE_REQUEST: ["sender", "group", "proposal", "options"],
    MessageType.VOTE: ["sender", "group", "choice"],
    MessageType.NEGOTIATE: ["sender", "target", "proposal", "counter"],
    MessageType.CONSENSUS: ["sender", "group", "decision", "payload"],
    MessageType.SHARE_MEMORY: ["sender", "target", "memory_key", "memory_entry"],
    MessageType.SHARE_PLAN: ["sender", "target", "plan_id", "plan"],
    MessageType.SHARE_RESULT: ["sender", "target", "task_id", "result"],
    MessageType.BROADCAST: ["sender", "group", "message"],
    MessageType.HEARTBEAT: ["sender", "timestamp"],
    MessageType.HEALTH: ["sender", "status", "metrics"],
    MessageType.ERROR: ["sender", "error_code", "details"],
    MessageType.METRICS: ["sender", "metrics"],
}


def validate_message(msg_type: MessageType, body: dict[str, Any]) -> list[str]:
    """Return list of missing required fields (empty means valid)."""
    required = MESSAGE_SCHEMAS.get(msg_type, [])
    return [f for f in required if f not in body]


# ── Message ──────────────────────────────────────────────────────────


@dataclass
class Message:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    msg_type: MessageType = MessageType.REQUEST
    sender: str = ""
    target: str | list[str] | None = None
    correlation_id: str | None = None
    body: dict[str, Any] = field(default_factory=dict)
    ttl_seconds: float = 0.0
    delivery_guarantee: DeliveryGuarantee = DeliveryGuarantee.AT_MOST_ONCE
    created_at: float = field(default_factory=time.time)
    delivered_at: float | None = None

    def is_expired(self) -> bool:
        if self.ttl_seconds <= 0:
            return False
        return (time.time() - self.created_at) > self.ttl_seconds

    def is_valid(self) -> bool:
        return len(validate_message(self.msg_type, self.body)) == 0

    def to_dict(self) -> dict[str, Any]:
        target = self.target
        if isinstance(target, list):
            target = list(target)
        return {
            "id": self.id,
            "msg_type": self.msg_type.value,
            "sender": self.sender,
            "target": target,
            "correlation_id": self.correlation_id,
            "body": dict(self.body),
            "ttl_seconds": self.ttl_seconds,
            "delivery_guarantee": self.delivery_guarantee.value,
            "created_at": self.created_at,
            "delivered_at": self.delivered_at,
        }
