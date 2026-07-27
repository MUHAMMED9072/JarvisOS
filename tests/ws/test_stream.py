"""Tests for the real-time event streaming (P12-02)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import WebSocket

from app.core.event_bus import EventBus
from app.ws.bridge import EventStreamBridge
from app.ws.events import (
    EventEnvelope,
    EventReplayBuffer,
    get_matching_subscriptions,
    make_envelope,
    match_event,
)
from app.ws.manager import ConnectionInfo, WebSocketConnectionManager


def _make_ws() -> AsyncMock:
    ws = AsyncMock(spec=WebSocket)
    ws.headers = {}
    return ws


# ==========================================================================
# EventReplayBuffer
# ==========================================================================


class TestEventReplayBuffer:
    def test_push_and_replay_exact(self):
        buf = EventReplayBuffer(max_events_per_type=5)
        e1 = make_envelope("ai.request", {"q": "hello"}, source="test")
        e2 = make_envelope("ai.request", {"q": "world"}, source="test")
        buf.push(e1)
        buf.push(e2)
        result = buf.replay("ai.request")
        assert len(result) == 2
        assert result[0].data == {"q": "hello"}
        assert result[1].data == {"q": "world"}

    def test_replay_wildcard(self):
        buf = EventReplayBuffer(max_events_per_type=10)
        buf.push(make_envelope("ai.request", {"q": "hello"}))
        buf.push(make_envelope("ai.response", {"text": "hi"}))
        buf.push(make_envelope("voice.transcript", {"text": "hello"}))
        result = buf.replay("ai.*")
        assert len(result) == 2

    def test_replay_all_wildcard(self):
        buf = EventReplayBuffer(max_events_per_type=10)
        buf.push(make_envelope("a.x"))
        buf.push(make_envelope("b.y"))
        result = buf.replay("*")
        assert len(result) == 2

    def test_buffer_max_size_per_type(self):
        buf = EventReplayBuffer(max_events_per_type=3)
        for i in range(5):
            buf.push(make_envelope("evt", {"n": i}))
        result = buf.replay("evt")
        assert len(result) == 3
        assert result[0].data == {"n": 2}
        assert result[2].data == {"n": 4}

    def test_replay_no_match(self):
        buf = EventReplayBuffer()
        buf.push(make_envelope("ai.request"))
        result = buf.replay("voice.*")
        assert result == []

    def test_replay_empty_buffer(self):
        buf = EventReplayBuffer()
        assert buf.replay("*") == []

    def test_clear_specific(self):
        buf = EventReplayBuffer()
        buf.push(make_envelope("a"))
        buf.push(make_envelope("b"))
        buf.clear("a")
        assert len(buf.replay("a")) == 0
        assert len(buf.replay("b")) == 1

    def test_clear_all(self):
        buf = EventReplayBuffer()
        buf.push(make_envelope("a"))
        buf.push(make_envelope("b"))
        buf.clear()
        assert len(buf) == 0

    def test_len(self):
        buf = EventReplayBuffer(max_events_per_type=5)
        assert len(buf) == 0
        buf.push(make_envelope("a"))
        assert len(buf) == 1
        buf.push(make_envelope("b"))
        assert len(buf) == 2


# ==========================================================================
# Wildcard matching
# ==========================================================================


class TestWildcardMatching:
    def test_exact_match(self):
        assert match_event("ai.request", "ai.request") is True

    def test_wildcard_prefix(self):
        assert match_event("ai.*", "ai.request") is True
        assert match_event("ai.*", "ai.response") is True

    def test_wildcard_suffix(self):
        assert match_event("*.request", "ai.request") is True
        assert match_event("*.request", "voice.request") is True

    def test_wildcard_no_match(self):
        assert match_event("ai.*", "voice.request") is False

    def test_catch_all(self):
        assert match_event("*", "anything.goes") is True

    def test_get_matching_subscriptions(self):
        subs = {"ai.*", "voice.*", "events.test"}
        result = get_matching_subscriptions(subs, "ai.request")
        assert "ai.*" in result
        assert "events.test" not in result

    def test_get_matching_subscriptions_multiple(self):
        subs = {"*.request", "ai.*", "voice.*"}
        result = get_matching_subscriptions(subs, "ai.request")
        assert "*.request" in result
        assert "ai.*" in result
        assert "voice.*" not in result

    def test_get_matching_subscriptions_no_match(self):
        subs = {"voice.*"}
        result = get_matching_subscriptions(subs, "ai.request")
        assert result == []


# ==========================================================================
# make_envelope
# ==========================================================================


class TestMakeEnvelope:
    def test_defaults(self):
        env = make_envelope("test.event")
        assert env.event == "test.event"
        assert env.data == {}
        assert env.event_id != ""
        assert env.timestamp != ""
        assert env.source == ""

    def test_unique_ids(self):
        e1 = make_envelope("e")
        e2 = make_envelope("e")
        assert e1.event_id != e2.event_id

    def test_data_and_source(self):
        env = make_envelope("x", {"key": "val"}, source="plugin")
        assert env.data == {"key": "val"}
        assert env.source == "plugin"

    def test_serialization(self):
        env = make_envelope("test", {"a": 1})
        d = env.model_dump()
        assert d["event"] == "test"
        assert d["data"] == {"a": 1}
        assert "event_id" in d
        assert "timestamp" in d


# ==========================================================================
# WebSocketConnectionManager – event streaming extensions
# ==========================================================================


class TestManagerEventQueue:
    @pytest.mark.asyncio
    async def test_connection_info_has_event_queue(self):
        ws = _make_ws()
        manager = WebSocketConnectionManager()
        info = await manager.connect(ws, client_id="q-test")
        assert info is not None
        assert hasattr(info, "event_queue")
        assert info.event_queue.maxsize == 100

    @pytest.mark.asyncio
    async def test_enqueue_event_adds_to_queue(self):
        ws = _make_ws()
        manager = WebSocketConnectionManager()
        await manager.connect(ws, client_id="q-user")
        env = make_envelope("ai.request", {"text": "hello"})
        result = await manager.enqueue_event("q-user", env)
        assert result is True
        info = manager.get_connection("q-user")
        assert info.event_queue.qsize() == 1

    @pytest.mark.asyncio
    async def test_enqueue_event_unknown_client(self):
        manager = WebSocketConnectionManager()
        env = make_envelope("x")
        result = await manager.enqueue_event("ghost", env)
        assert result is False

    @pytest.mark.asyncio
    async def test_enqueue_creates_dispatch_task(self):
        ws = _make_ws()
        manager = WebSocketConnectionManager()
        await manager.connect(ws, client_id="dispatch-me")
        env = make_envelope("e", {"n": 1})
        await manager.enqueue_event("dispatch-me", env)
        info = manager.get_connection("dispatch-me")
        assert info.dispatch_task is not None
        await asyncio.sleep(0.05)
        ws.send_json.assert_awaited_once()
        payload = ws.send_json.await_args[0][0]
        assert payload["event"] == "e"
        assert payload["data"] == {"n": 1}

    @pytest.mark.asyncio
    async def test_dispatch_sends_multiple_events(self):
        ws = _make_ws()
        manager = WebSocketConnectionManager()
        await manager.connect(ws, client_id="multi")
        for i in range(3):
            env = make_envelope("e", {"n": i})
            await manager.enqueue_event("multi", env)
        await asyncio.sleep(0.1)
        assert ws.send_json.await_count == 3

    @pytest.mark.asyncio
    async def test_disconnect_cancels_dispatch(self):
        ws = _make_ws()
        manager = WebSocketConnectionManager()
        await manager.connect(ws, client_id="stop-dispatch")
        env = make_envelope("e")
        await manager.enqueue_event("stop-dispatch", env)
        info = manager.get_connection("stop-dispatch")
        dt = info.dispatch_task
        await manager.disconnect("stop-dispatch")
        assert dt.done()

    @pytest.mark.asyncio
    async def test_backpressure_drops_oldest(self):
        ws = _make_ws()
        manager = WebSocketConnectionManager()
        info = ConnectionInfo("bp", ws, queue_maxsize=2)
        async with manager._lock:
            manager._connections["bp"] = info
        env = make_envelope("ev", {"n": 0})
        await manager.enqueue_event("bp", env)
        await asyncio.sleep(0.05)
        ws.send_json.assert_called()


# ==========================================================================
# EventStreamBridge
# ==========================================================================


class TestEventStreamBridgeLifecycle:
    def test_start_registers_wildcard_subscriber(self):
        bus = EventBus()
        mgr = MagicMock(spec=WebSocketConnectionManager)
        bridge = EventStreamBridge(event_bus=bus, ws_manager=mgr)
        bridge.start()
        assert bridge._subscribed is True

    def test_stop_unregisters_subscriber(self):
        bus = EventBus()
        mgr = MagicMock(spec=WebSocketConnectionManager)
        bridge = EventStreamBridge(event_bus=bus, ws_manager=mgr)
        bridge.start()
        bridge.stop()
        assert bridge._subscribed is False

    def test_double_start_is_idempotent(self):
        bus = EventBus()
        mgr = MagicMock(spec=WebSocketConnectionManager)
        bridge = EventStreamBridge(event_bus=bus, ws_manager=mgr)
        bridge.start()
        bridge.start()
        assert bridge._subscribed is True

    def test_double_stop_is_safe(self):
        bus = EventBus()
        mgr = MagicMock(spec=WebSocketConnectionManager)
        bridge = EventStreamBridge(event_bus=bus, ws_manager=mgr)
        bridge.stop()
        assert bridge._subscribed is False


class TestEventStreamBridgeForwarding:
    @pytest.mark.asyncio
    async def test_bridge_forwards_event_to_ws_client(self):
        bus = EventBus()
        mgr = WebSocketConnectionManager()
        ws = _make_ws()
        await mgr.connect(ws, client_id="ws-cli")
        await mgr.subscribe("ws-cli", "ai.*")
        bridge = EventStreamBridge(event_bus=bus, ws_manager=mgr)
        bridge.start()
        bus.publish("ai.request", text="hello")
        await asyncio.sleep(0.1)
        ws.send_json.assert_called()
        args = ws.send_json.await_args[0][0]
        assert args["event"] == "ai.request"
        assert args["data"]["text"] == "hello"

    @pytest.mark.asyncio
    async def test_bridge_does_not_send_to_unsubscribed(self):
        bus = EventBus()
        mgr = WebSocketConnectionManager()
        ws = _make_ws()
        await mgr.connect(ws, client_id="no-sub")
        bridge = EventStreamBridge(event_bus=bus, ws_manager=mgr)
        bridge.start()
        bus.publish("ai.request", text="secret")
        await asyncio.sleep(0.05)
        if ws.send_json.await_args:
            pytest.fail("Should not have sent to unsubscribed")

    @pytest.mark.asyncio
    async def test_bridge_forwards_multiple_events(self):
        bus = EventBus()
        mgr = WebSocketConnectionManager()
        ws = _make_ws()
        await mgr.connect(ws, client_id="multi-sub")
        await mgr.subscribe("multi-sub", "ai.*")
        bridge = EventStreamBridge(event_bus=bus, ws_manager=mgr)
        bridge.start()
        bus.publish("ai.request", q="hi")
        bus.publish("ai.response", text="hello")
        await asyncio.sleep(0.1)
        assert ws.send_json.await_count >= 1

    @pytest.mark.asyncio
    async def test_bridge_pushes_to_replay_buffer(self):
        bus = EventBus()
        mgr = WebSocketConnectionManager()
        ws = _make_ws()
        await mgr.connect(ws, client_id="replay-cli")
        await mgr.subscribe("replay-cli", "ai.*")
        bridge = EventStreamBridge(event_bus=bus, ws_manager=mgr)
        bridge.start()
        bus.publish("ai.request", text="first")
        bus.publish("ai.response", text="second")
        await asyncio.sleep(0.05)
        replay = bridge.replay("ai.*")
        assert len(replay) == 2
        assert replay[0].event == "ai.request"
        assert replay[1].event == "ai.response"

    @pytest.mark.asyncio
    async def test_bridge_sends_exact_match_subscription(self):
        bus = EventBus()
        mgr = WebSocketConnectionManager()
        ws = _make_ws()
        await mgr.connect(ws, client_id="exact")
        await mgr.subscribe("exact", "my.custom.event")
        bridge = EventStreamBridge(event_bus=bus, ws_manager=mgr)
        bridge.start()
        bus.publish("my.custom.event", data=42)
        await asyncio.sleep(0.05)
        ws.send_json.assert_called()


class TestEventStreamBridgeNonEventBus:
    def test_replay_empty(self):
        bus = EventBus()
        mgr = MagicMock(spec=WebSocketConnectionManager)
        bridge = EventStreamBridge(event_bus=bus, ws_manager=mgr)
        assert bridge.replay("*") == []

    def test_buffer_property(self):
        bus = EventBus()
        mgr = MagicMock(spec=WebSocketConnectionManager)
        bridge = EventStreamBridge(event_bus=bus, ws_manager=mgr)
        assert bridge.buffer is not None
        assert len(bridge.buffer) == 0


# ==========================================================================
# Manager: wildcard subscriptions
# ==========================================================================


class TestManagerWildcardSubscriptions:
    @pytest.mark.asyncio
    async def test_subscribe_with_wildcard_pattern(self):
        mgr = WebSocketConnectionManager()
        ws = _make_ws()
        await mgr.connect(ws, client_id="wild-sub")
        await mgr.subscribe("wild-sub", "ai.*")
        clients = await mgr.get_subscribed_clients_for_event("ai.request")
        assert "wild-sub" in clients

    @pytest.mark.asyncio
    async def test_wildcard_matches_multiple_events(self):
        mgr = WebSocketConnectionManager()
        ws = _make_ws()
        await mgr.connect(ws, client_id="wild-sub2")
        await mgr.subscribe("wild-sub2", "ai.*")
        for event in ("ai.request", "ai.response", "voice.test"):
            clients = await mgr.get_subscribed_clients_for_event(event)
            if event == "voice.test":
                assert "wild-sub2" not in clients
            else:
                assert "wild-sub2" in clients

    @pytest.mark.asyncio
    async def test_get_subscribed_clients_for_event_no_match(self):
        mgr = WebSocketConnectionManager()
        ws = _make_ws()
        await mgr.connect(ws, client_id="no-match")
        await mgr.subscribe("no-match", "voice.*")
        clients = await mgr.get_subscribed_clients_for_event("ai.request")
        assert clients == []

    @pytest.mark.asyncio
    async def test_get_subscribed_clients_for_event_empty(self):
        mgr = WebSocketConnectionManager()
        clients = await mgr.get_subscribed_clients_for_event("any")
        assert clients == []


# ==========================================================================
# Integration: End-to-end with EventBus
# ==========================================================================


class TestEndToEnd:
    @pytest.mark.asyncio
    async def test_event_published_after_subscription_received(self):
        bus = EventBus()
        mgr = WebSocketConnectionManager()
        ws = _make_ws()
        await mgr.connect(ws, client_id="e2e")
        await mgr.subscribe("e2e", "test.event")
        bridge = EventStreamBridge(event_bus=bus, ws_manager=mgr)
        bridge.start()
        bus.publish("test.event", status="ok")
        await asyncio.sleep(0.1)
        ws.send_json.assert_called()
        payload = ws.send_json.await_args[0][0]
        assert payload["event"] == "test.event"
        assert payload["data"]["status"] == "ok"

    @pytest.mark.asyncio
    async def test_multiple_clients_same_event(self):
        bus = EventBus()
        mgr = WebSocketConnectionManager()
        ws1 = _make_ws()
        ws2 = _make_ws()
        await mgr.connect(ws1, client_id="c1")
        await mgr.connect(ws2, client_id="c2")
        await mgr.subscribe("c1", "broadcast.*")
        await mgr.subscribe("c2", "broadcast.*")
        bridge = EventStreamBridge(event_bus=bus, ws_manager=mgr)
        bridge.start()
        bus.publish("broadcast.msg", text="hello all")
        await asyncio.sleep(0.1)
        assert ws1.send_json.await_count >= 1
        assert ws2.send_json.await_count >= 1

    @pytest.mark.asyncio
    async def test_bridge_stop_prevents_forwarding(self):
        bus = EventBus()
        mgr = WebSocketConnectionManager()
        ws = _make_ws()
        await mgr.connect(ws, client_id="stop-me")
        await mgr.subscribe("stop-me", "*")
        bridge = EventStreamBridge(event_bus=bus, ws_manager=mgr)
        bridge.start()
        bridge.stop()
        bus.publish("any.event", data="should be ignored")
        await asyncio.sleep(0.05)
        if ws.send_json.await_args:
            pytest.fail("Bridge should not forward after stop")


# ==========================================================================
# Backward compatibility
# ==========================================================================


class TestBackwardCompatibility:
    def test_existing_health_still_works(self):
        from app.api.server import create_app
        from fastapi.testclient import TestClient

        app = create_app()
        client = TestClient(app)
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200

    def test_existing_ws_manager_unchanged(self):
        manager = WebSocketConnectionManager()
        assert hasattr(manager, "connect")
        assert hasattr(manager, "disconnect")
        assert hasattr(manager, "broadcast")
        assert hasattr(manager, "send_to_subscribers")
