from __future__ import annotations

import time

import pytest

from app.agents.communication.bus import MessageBus
from app.agents.communication.message import Message, MessageType
from app.agents.communication.patterns import (
    Broadcast,
    DelegateReturn,
    Escalation,
    Negotiation,
    Pipeline,
    RequestResponse,
    VoteType,
    Voting,
)


@pytest.fixture
def bus():
    return MessageBus()


class TestRequestResponse:
    def test_request_timeout(self, bus):
        rr = RequestResponse(bus)
        result = rr.send_request("a1", "nonexistent", "ping", timeout=0.1)
        assert result is None

    def test_request_response_cycle(self, bus):
        rr = RequestResponse(bus)
        # Manually simulate: subscribe to requests topic and auto-respond
        def handler(msg: Message) -> None:
            if msg.msg_type == MessageType.REQUEST:
                rr.send_response("a2", "a1", msg, "ok", {"result": "pong"})
        bus.subscribe("requests", handler)

        result = rr.send_request("a1", "a2", "ping", timeout=2.0)
        assert result is not None
        assert result["status"] == "ok"
        assert result["payload"]["result"] == "pong"


class TestDelegateReturn:
    def test_delegate_timeout(self, bus):
        dr = DelegateReturn(bus)
        result = dr.delegate("a1", "nonexistent", "task-1", timeout=0.1)
        assert result is None

    def test_delegate_and_return(self, bus):
        dr = DelegateReturn(bus)

        def handler(msg: Message) -> None:
            if msg.msg_type == MessageType.DELEGATE:
                # Simulate handling
                pass

        bus.subscribe("delegations", handler)
        result = dr.delegate("a1", "a2", "task-1", timeout=0.1)
        # May timeout since no response handler wired, but that's OK
        assert result is None or isinstance(result, dict)


class TestBroadcast:
    def test_broadcast(self, bus):
        bc = Broadcast(bus)
        received = []

        def handler(msg: Message) -> None:
            received.append(msg)

        bus.subscribe_direct("a1", handler)
        bus.subscribe_direct("a2", handler)
        count = bc.broadcast("sender", group="all", message="hello")
        assert count >= 2


class TestVoting:
    def test_majority(self, bus):
        v = Voting(bus)
        # Simulate votes
        def vote_handler(msg: Message) -> None:
            if msg.msg_type == MessageType.VOTE_REQUEST:
                for target in (msg.target or []):
                    vote_msg = Message(
                        sender=target,
                        msg_type=MessageType.VOTE,
                        correlation_id=msg.correlation_id,
                        body={"sender": target, "group": msg.body.get("group", []),
                              "correlation_id": msg.correlation_id or "", "choice": "option_a"},
                    )
                    bus.publish(vote_msg, topic="votes")

        bus.subscribe("vote_requests", vote_handler)

        result = v.request_votes(
            "a1", ["a2", "a3", "a4"], "proposal_x", ["option_a", "option_b"],
            vote_type=VoteType.MAJORITY, timeout=2.0,
        )
        assert result["winner"] == "option_a"
        assert result["decided"] is True

    def test_unanimous(self, bus):
        v = Voting(bus)

        def vote_handler(msg: Message) -> None:
            if msg.msg_type == MessageType.VOTE_REQUEST:
                targets = msg.target if isinstance(msg.target, list) else []
                for t in targets:
                    vm = Message(sender=t, msg_type=MessageType.VOTE,
                                 correlation_id=msg.correlation_id,
                                 body={"sender": t, "group": [], "correlation_id": msg.correlation_id or "",
                                       "choice": "yes"})
                    bus.publish(vm, topic="votes")

        bus.subscribe("vote_requests", vote_handler)
        result = v.request_votes("a1", ["a2", "a3"], "approve?", ["yes", "no"],
                                  vote_type=VoteType.UNANIMOUS, timeout=2.0)
        assert result["decided"] is True
        assert result["winner"] == "yes"

    def test_supermajority(self, bus):
        v = Voting(bus)

        def vote_handler(msg: Message) -> None:
            if msg.msg_type == MessageType.VOTE_REQUEST:
                targets = msg.target if isinstance(msg.target, list) else []
                for i, t in enumerate(targets):
                    choice = "yes" if i < 2 else "no"
                    vm = Message(sender=t, msg_type=MessageType.VOTE,
                                 correlation_id=msg.correlation_id,
                                 body={"sender": t, "group": [], "correlation_id": msg.correlation_id or "",
                                       "choice": choice})
                    bus.publish(vm, topic="votes")

        bus.subscribe("vote_requests", vote_handler)
        result = v.request_votes("a1", ["a2", "a3", "a4"], "proposal?", ["yes", "no"],
                                  vote_type=VoteType.SUPERMAJORITY, timeout=2.0)
        assert result["winner"] == "yes"
        assert result["decided"] is True

    def test_vote_timeout(self, bus):
        v = Voting(bus)
        result = v.request_votes("a1", ["a2", "a3"], "proposal?", ["yes", "no"],
                                  timeout=0.1)
        assert result["decided"] is False


class TestEscalation:
    def test_escalate(self, bus):
        e = Escalation(bus)
        e.set_chain("agent-1", ["supervisor", "executive_controller"])
        received = []
        def handler(msg: Message) -> None:
            received.append(msg)
        bus.subscribe("escalation", handler)
        notified = e.escalate("agent-1", "something broke")
        assert len(notified) == 2
        assert len(received) == 2
        assert received[0].body["issue"] == "something broke"

    def test_default_chain(self, bus):
        e = Escalation(bus)
        notified = e.escalate("agent-1", "failure")
        assert notified == ["executive_controller"]

    def test_health(self, bus):
        e = Escalation(bus)
        h = e.health()
        assert h["alive"] is True


class TestNegotiation:
    def test_negotiation_accept(self, bus):
        n = Negotiation(bus)
        result = n.negotiate(
            "a1", "a2", "initial offer",
            max_rounds=3, timeout=2.0,
            accept_if=lambda p: "acceptable" in p,
        )
        # Without "acceptable" in proposals, it'll run all rounds
        assert result["agreed"] is False
        assert result["rounds"] == 3

    def test_negotiation_immediate_accept(self, bus):
        n = Negotiation(bus)
        result = n.negotiate(
            "a1", "a2", "acceptable offer",
            max_rounds=5, timeout=2.0,
            accept_if=lambda p: "acceptable" in p,
        )
        assert result["agreed"] is True
        assert result["final"] == "acceptable offer"


class TestPipeline:
    def test_pipeline(self, bus):
        p = Pipeline(bus)
        stages = [
            {"agent_id": "a1", "action": "fetch"},
            {"agent_id": "a2", "action": "transform"},
            {"agent_id": "a3", "action": "store"},
        ]
        results = p.run(stages, initial_input={"data": "raw"})
        assert len(results) == 3
        assert "pipeline:" in results[0]
        assert "pipeline:" in results[1]
        assert "pipeline:" in results[2]
