from __future__ import annotations

import enum
import threading
import time
import uuid
from collections import Counter
from typing import Any, Callable

from app.agents.communication.bus import MessageBus
from app.agents.communication.message import Message, MessageType


class VoteType(enum.Enum):
    MAJORITY = "majority"
    SUPERMAJORITY = "supermajority"
    UNANIMOUS = "unanimous"


# ── Request-Response ─────────────────────────────────────────────────


class RequestResponse:
    """Type-safe request/response with timeout."""

    def __init__(self, bus: MessageBus) -> None:
        self._bus = bus
        self._responses: dict[str, Any] = {}
        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)
        bus.subscribe("responses", self._on_response)

    def _on_response(self, message: Message) -> None:
        if message.msg_type != MessageType.RESPONSE:
            return
        cid = message.correlation_id
        if cid:
            with self._cond:
                self._responses[cid] = message.body
                self._cond.notify_all()

    def send_request(
        self,
        sender: str,
        target: str,
        action: str,
        payload: dict[str, Any] | None = None,
        timeout: float = 30.0,
    ) -> dict[str, Any] | None:
        req = Message(
            sender=sender,
            target=target,
            msg_type=MessageType.REQUEST,
            body={
                "sender": sender,
                "target": target,
                "action": action,
                "payload": payload or {},
            },
            ttl_seconds=timeout,
        )
        self._bus.publish(req, topic="requests")
        correlation_id = req.id
        deadline = time.time() + timeout
        with self._cond:
            while correlation_id not in self._responses:
                remaining = deadline - time.time()
                if remaining <= 0:
                    return None
                self._cond.wait(timeout=remaining)
            return self._responses.pop(correlation_id, None)

    def send_response(
        self, sender: str, target: str, request: Message, status: str, payload: Any,
    ) -> None:
        resp = Message(
            sender=sender,
            target=target,
            msg_type=MessageType.RESPONSE,
            correlation_id=request.id,
            body={
                "sender": sender,
                "target": target,
                "status": status,
                "payload": payload,
            },
        )
        self._bus.publish(resp, topic="responses")


# ── Delegate-Return ──────────────────────────────────────────────────


class DelegateReturn:
    """Delegate subtask, await result, handle failure."""

    TIMEOUT = 60.0

    def __init__(self, bus: MessageBus) -> None:
        self._bus = bus
        self._rr = RequestResponse(bus)

    def delegate(
        self,
        sender: str,
        target: str,
        task_id: str,
        payload: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any] | None:
        msg = Message(
            sender=sender,
            target=target,
            msg_type=MessageType.DELEGATE,
            body={
                "sender": sender,
                "target": target,
                "task_id": task_id,
                "payload": payload or {},
            },
            ttl_seconds=timeout or self.TIMEOUT,
        )
        self._bus.publish(msg, topic="delegations")
        return self._rr.send_request(
            sender=sender,
            target=target,
            action=f"delegate:{task_id}",
            payload=payload,
            timeout=timeout or self.TIMEOUT,
        )


# ── Broadcast ────────────────────────────────────────────────────────


class Broadcast:
    """Send message to all agents matching criteria."""

    def __init__(self, bus: MessageBus) -> None:
        self._bus = bus

    def broadcast(
        self,
        sender: str,
        group: str = "all",
        message: str = "",
        payload: dict[str, Any] | None = None,
    ) -> int:
        msg = Message(
            sender=sender,
            msg_type=MessageType.BROADCAST,
            target=group,
            body={
                "sender": sender,
                "group": group,
                "message": message,
                **(payload or {}),
            },
        )
        return self._bus.publish(msg)


# ── Voting ───────────────────────────────────────────────────────────


class Voting:
    """Request votes from agent group, compute consensus."""

    def __init__(self, bus: MessageBus) -> None:
        self._bus = bus
        self._votes: dict[str, dict[str, str]] = {}
        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)
        bus.subscribe("votes", self._on_vote)

    def _on_vote(self, message: Message) -> None:
        if message.msg_type != MessageType.VOTE:
            return
        cid = message.correlation_id
        if cid:
            with self._cond:
                if cid not in self._votes:
                    self._votes[cid] = {}
                self._votes[cid][message.sender] = message.body.get("choice", "")
                self._cond.notify_all()

    def request_votes(
        self,
        sender: str,
        group: list[str],
        proposal: str,
        options: list[str],
        vote_type: VoteType = VoteType.MAJORITY,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        vote_id = uuid.uuid4().hex[:16]
        req = Message(
            sender=sender,
            target=group,
            msg_type=MessageType.VOTE_REQUEST,
            body={
                "sender": sender,
                "group": group,
                "proposal": proposal,
                "options": options,
            },
            correlation_id=vote_id,
            ttl_seconds=timeout,
        )
        self._bus.publish(req, topic="vote_requests")

        deadline = time.time() + timeout
        with self._cond:
            while vote_id not in self._votes or len(self._votes[vote_id]) < len(group):
                remaining = deadline - time.time()
                if remaining <= 0:
                    break
                self._cond.wait(timeout=remaining)

        votes = self._votes.pop(vote_id, {})
        total = len(group)
        received = len(votes)
        counter: Counter[str] = Counter(votes.values())
        most_common = counter.most_common(1)
        winner = most_common[0][0] if most_common else ""
        winner_count = most_common[0][1] if most_common else 0

        decided = False
        if vote_type == VoteType.UNANIMOUS:
            decided = received == total and winner_count == total
        elif vote_type == VoteType.SUPERMAJORITY:
            decided = received > 0 and winner_count / total >= 0.666
        else:  # MAJORITY
            decided = received > 0 and winner_count > total / 2

        return {
            "proposal": proposal,
            "vote_id": vote_id,
            "votes": votes,
            "winner": winner,
            "winner_count": winner_count,
            "total": total,
            "received": received,
            "decided": decided,
            "vote_type": vote_type.value,
        }


# ── Escalation ───────────────────────────────────────────────────────


class Escalation:
    """Automatic escalation chain on failure."""

    def __init__(self, bus: MessageBus) -> None:
        self._bus = bus
        self._chain: dict[str, list[str]] = {}  # agent_id -> escalation path

    def set_chain(self, agent_id: str, chain: list[str]) -> None:
        self._chain[agent_id] = chain

    def escalate(
        self,
        agent_id: str,
        issue: str,
        details: dict[str, Any] | None = None,
    ) -> list[str]:
        chain = self._chain.get(agent_id, ["executive_controller"])
        notified: list[str] = []
        for target in chain:
            msg = Message(
                sender=agent_id,
                target=target,
                msg_type=MessageType.ESCALATE,
                body={
                    "sender": agent_id,
                    "target": target,
                    "issue": issue,
                    "details": details or {},
                },
                ttl_seconds=60.0,
            )
            self._bus.publish(msg, topic="escalation")
            notified.append(target)
        return notified

    def health(self) -> dict[str, Any]:
        return {
            "alive": True,
            "chains_configured": len(self._chain),
        }


# ── Negotiation ──────────────────────────────────────────────────────


class Negotiation:
    """Two-party negotiation protocol with counter-proposals."""

    def __init__(self, bus: MessageBus) -> None:
        self._bus = bus
        self._proposals: dict[str, list[str]] = {}  # session_id -> proposal history
        self._lock = threading.Lock()

    def negotiate(
        self,
        sender: str,
        target: str,
        initial_proposal: str,
        max_rounds: int = 5,
        timeout: float = 30.0,
        accept_if: Callable[[str], bool] | None = None,
    ) -> dict[str, Any]:
        session_id = uuid.uuid4().hex[:16]
        with self._lock:
            self._proposals[session_id] = [initial_proposal]

        current = initial_proposal
        for round_idx in range(max_rounds):
            if accept_if and accept_if(current):
                with self._lock:
                    self._proposals[session_id].append(f"accepted: {current}")
                return {
                    "session_id": session_id,
                    "agreed": True,
                    "rounds": round_idx + 1,
                    "final": current,
                    "history": list(self._proposals.get(session_id, [])),
                }

            msg = Message(
                sender=sender,
                target=target,
                msg_type=MessageType.NEGOTIATE,
                body={
                    "sender": sender,
                    "target": target,
                    "proposal": current,
                    "counter": f"counter_{round_idx}",
                },
                correlation_id=session_id,
                ttl_seconds=timeout,
            )
            self._bus.publish(msg, topic="negotiations")

            # Simulate counter-proposal from target
            counter = f"counter_proposal_{round_idx + 1}"
            with self._lock:
                self._proposals[session_id].append(counter)
            current = counter

        with self._lock:
            self._proposals[session_id].append("timeout")
        return {
            "session_id": session_id,
            "agreed": False,
            "rounds": max_rounds,
            "final": current,
            "history": list(self._proposals.get(session_id, [])),
        }


# ── Pipeline ─────────────────────────────────────────────────────────


class Pipeline:
    """Chain agent executions: output of one feeds into next."""

    def __init__(self, bus: MessageBus) -> None:
        self._bus = bus

    def run(
        self,
        stages: list[dict[str, Any]],
        initial_input: Any = None,
    ) -> list[Any]:
        results: list[Any] = []
        current_input = initial_input
        for stage in stages:
            agent_id = stage.get("agent_id", "")
            action = stage.get("action", "process")
            msg = Message(
                sender="pipeline",
                target=agent_id,
                msg_type=MessageType.REQUEST,
                body={
                    "sender": "pipeline",
                    "target": agent_id,
                    "action": action,
                    "payload": {"input": current_input},
                },
                ttl_seconds=stage.get("timeout", 30.0),
            )
            self._bus.publish(msg, topic="pipeline")
            # In a real system the response comes back async.
            # Here we capture the pipeline state as the message ID.
            current_input = f"pipeline:{msg.id}:stage_output"
            results.append(current_input)
        return results
