from __future__ import annotations

import asyncio
import json
import time
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import WebSocket

from app.ws.manager import ConnectionInfo, WebSocketConnectionManager
from app.ws.reliability import (
    ConnectionStats,
    OfflineQueue,
    RetryQueue,
    compress_payload,
    decompress_payload,
)
from app.ws.schemas import ServerMessage, WSMessageType


# ======================================================================
# ConnectionStats
# ======================================================================


class TestConnectionStats:
    def test_defaults(self):
        s = ConnectionStats()
        assert s.bytes_sent == 0
        assert s.messages_sent == 0
        assert s.latency_min == 0.0

    def test_record_latency(self):
        s = ConnectionStats()
        s.record_latency(0.1)
        assert s.latency_min == 0.1
        assert s.latency_max == 0.1
        assert s.latency_avg == 0.1

        s.record_latency(0.5)
        assert s.latency_min == 0.1
        assert s.latency_max == 0.5
        assert s.latency_avg == 0.3

    def test_record_latency_multiple(self):
        s = ConnectionStats()
        for v in [0.2, 0.3, 0.1, 0.4]:
            s.record_latency(v)
        assert s.latency_min == 0.1
        assert s.latency_max == 0.4
        assert s.latency_avg == 0.25

    def test_reset_latency(self):
        s = ConnectionStats()
        s.record_latency(0.5)
        s.reset_latency()
        assert s.latency_min == 0.0
        assert s.latency_max == 0.0
        assert s.latency_avg == 0.0
        assert len(s.latency_samples) == 0

    def test_to_dict(self):
        s = ConnectionStats()
        s.bytes_sent = 100
        s.messages_sent = 5
        s.dropped_messages = 2
        s.record_latency(0.25)
        d = s.to_dict()
        assert d["bytes_sent"] == 100
        assert d["messages_sent"] == 5
        assert d["dropped_messages"] == 2
        assert d["latency_avg"] == 0.25

    def test_latency_samples_capped(self):
        s = ConnectionStats()
        for i in range(200):
            s.record_latency(float(i) / 100)
        assert len(s.latency_samples) == 100


# ======================================================================
# RetryQueue
# ======================================================================


class TestRetryQueue:
    @pytest.mark.asyncio
    async def test_add_and_pending(self):
        q = RetryQueue("client1")
        assert await q.pending_count() == 0
        await q.add("msg1", {"type": "test", "payload": {}})
        assert await q.pending_count() == 1

    @pytest.mark.asyncio
    async def test_ack_removes_entry(self):
        q = RetryQueue("client1")
        await q.add("msg1", {"type": "test"})
        entry = await q.ack("msg1")
        assert entry is not None
        assert entry.message_id == "msg1"
        assert await q.pending_count() == 0

    @pytest.mark.asyncio
    async def test_ack_nonexistent(self):
        q = RetryQueue("client1")
        entry = await q.ack("nonexistent")
        assert entry is None

    @pytest.mark.asyncio
    async def test_get_entry(self):
        q = RetryQueue("client1")
        await q.add("msg1", {"type": "test"})
        entry = await q.get("msg1")
        assert entry is not None
        assert entry.message_id == "msg1"

    @pytest.mark.asyncio
    async def test_clear_returns_all(self):
        q = RetryQueue("client1")
        await q.add("msg1", {"a": 1})
        await q.add("msg2", {"b": 2})
        msgs = await q.clear()
        assert len(msgs) == 2
        assert await q.pending_count() == 0

    @pytest.mark.asyncio
    async def test_get_all_pending(self):
        q = RetryQueue("client1")
        await q.add("msg1", {"a": 1})
        entries = await q.get_all_pending()
        assert len(entries) == 1
        assert entries[0].message_id == "msg1"

    @pytest.mark.asyncio
    async def test_retry_loop_resends(self):
        sent: list[dict] = []

        async def fake_send(msg: dict) -> bool:
            sent.append(msg)
            return True

        q = RetryQueue("client1", max_retries=2, retry_interval=0.05)
        q.set_send_fn(fake_send)
        await q.start_retry_loop()
        await q.add("msg1", {"type": "test", "payload": {}})

        # Wait for retry interval
        await asyncio.sleep(0.15)
        await q.stop_retry_loop()

        # Should have been retried at least once
        assert len(sent) >= 1

    @pytest.mark.asyncio
    async def test_concurrent_add_and_ack(self):
        q = RetryQueue("client1")

        async def adder():
            for i in range(10):
                await q.add(f"msg{i}", {"i": i})

        async def acker():
            for i in range(10):
                await q.ack(f"msg{i}")

        await asyncio.gather(adder(), acker())
        assert await q.pending_count() == 0


# ======================================================================
# OfflineQueue
# ======================================================================


class TestOfflineQueue:
    @pytest.mark.asyncio
    async def test_put_and_drain(self):
        q = OfflineQueue(maxsize=10)
        assert await q.put({"a": 1}) is True
        assert await q.put({"b": 2}) is True
        msgs = await q.drain()
        assert len(msgs) == 2
        assert await q.drain() == []

    @pytest.mark.asyncio
    async def test_overflow_drop_oldest(self):
        q = OfflineQueue(maxsize=2, overflow_strategy="drop_oldest")
        await q.put({"a": 1})
        await q.put({"b": 2})
        await q.put({"c": 3})  # drops "a"
        msgs = await q.drain()
        assert len(msgs) == 2
        assert msgs[0] == {"b": 2}
        assert msgs[1] == {"c": 3}

    @pytest.mark.asyncio
    async def test_overflow_drop_newest(self):
        q = OfflineQueue(maxsize=2, overflow_strategy="drop_newest")
        assert await q.put({"a": 1}) is True
        assert await q.put({"b": 2}) is True
        assert await q.put({"c": 3}) is False  # dropped
        msgs = await q.drain()
        assert len(msgs) == 2
        assert msgs[0] == {"a": 1}
        assert msgs[1] == {"b": 2}

    @pytest.mark.asyncio
    async def test_qsize(self):
        q = OfflineQueue(maxsize=10)
        assert q.qsize == 0
        await q.put({"a": 1})
        assert q.qsize == 1

    @pytest.mark.asyncio
    async def test_overflow_count(self):
        q = OfflineQueue(maxsize=1, overflow_strategy="drop_newest")
        await q.put({"a": 1})
        await q.put({"b": 2})  # dropped
        assert q.overflow_count == 1

    @pytest.mark.asyncio
    async def test_clear(self):
        q = OfflineQueue(maxsize=10)
        await q.put({"a": 1})
        await q.clear()
        assert q.qsize == 0


# ======================================================================
# Compression
# ======================================================================


class TestCompression:
    def test_compress_small_payload(self):
        payload = {"msg": "hello"}
        result, size = compress_payload(payload, min_size=100)
        assert result is None  # Too small to compress
        assert size > 0

    def test_compress_large_payload(self):
        payload = {"data": "x" * 10000}
        compressed, size = compress_payload(payload, min_size=100)
        assert compressed is not None
        assert len(compressed) < size  # compressed smaller than original

    def test_compress_and_decompress_roundtrip(self):
        original = {"msg": "hello world", "values": [1, 2, 3]}
        compressed, _ = compress_payload(original, min_size=1)
        assert compressed is not None
        restored = decompress_payload(compressed)
        assert restored == original

    def test_decompress_invalid_data(self):
        with pytest.raises(Exception):
            decompress_payload(b"not valid gzip data")

    def test_compress_empty_dict(self):
        compressed, size = compress_payload({}, min_size=100)
        assert compressed is None
        assert size > 0


# ======================================================================
# Manager: ACK handling
# ======================================================================


class TestManagerAck:
    @pytest.mark.asyncio
    async def test_handle_ack_message(self):
        manager = WebSocketConnectionManager()
        ws = AsyncMock(spec=WebSocket)
        ws.headers = {}
        await manager.connect(ws, client_id="client1")

        # Send a reliable message to set up retry queue
        msg = ServerMessage(type=WSMessageType.MESSAGE, payload={"text": "hello"})
        await manager.send("client1", msg, require_ack=True)

        # Verify pending count
        count = await manager.get_pending_ack_count("client1")
        assert count == 1

        # Send ACK
        ack_raw = json.dumps({
            "type": "ack",
            "payload": {"message_id": msg.message_id},
        })
        await manager.handle_message("client1", ack_raw)

        # Verify ack removed entry
        count = await manager.get_pending_ack_count("client1")
        assert count == 0

    @pytest.mark.asyncio
    async def test_ack_nonexistent_message(self):
        manager = WebSocketConnectionManager()
        ws = AsyncMock(spec=WebSocket)
        ws.headers = {}
        await manager.connect(ws, client_id="client1")

        ack_raw = json.dumps({
            "type": "ack",
            "payload": {"message_id": "nonexistent"},
        })
        response = await manager.handle_message("client1", ack_raw)
        assert response is None  # No error response for unknown ack

    @pytest.mark.asyncio
    async def test_ack_empty_message_id(self):
        manager = WebSocketConnectionManager()
        ws = AsyncMock(spec=WebSocket)
        ws.headers = {}
        await manager.connect(ws, client_id="client1")

        ack_raw = json.dumps({
            "type": "ack",
            "payload": {},
        })
        response = await manager.handle_message("client1", ack_raw)
        assert response is None

    @pytest.mark.asyncio
    async def test_reliable_send_tracks_stats(self):
        manager = WebSocketConnectionManager()
        ws = AsyncMock(spec=WebSocket)
        ws.headers = {}
        await manager.connect(ws, client_id="client1")

        msg = ServerMessage(type=WSMessageType.MESSAGE, payload={"text": "hello"})
        await manager.send("client1", msg, require_ack=True)

        assert msg.message_id is not None
        stats = await manager.get_connection_stats("client1")
        assert stats["messages_sent"] == 1

    @pytest.mark.asyncio
    async def test_pending_ack_count_no_client(self):
        manager = WebSocketConnectionManager()
        count = await manager.get_pending_ack_count("nonexistent")
        assert count == 0

    @pytest.mark.asyncio
    async def test_send_reliable_helper(self):
        manager = WebSocketConnectionManager()
        ws = AsyncMock(spec=WebSocket)
        ws.headers = {}
        await manager.connect(ws, client_id="client1")

        msg = ServerMessage(type=WSMessageType.MESSAGE, payload={"text": "hello"})
        result = await manager.send_reliable("client1", msg)
        assert result is True
        assert msg.message_id is not None
        count = await manager.get_pending_ack_count("client1")
        assert count == 1


# ======================================================================
# Manager: Connection statistics
# ======================================================================


class TestManagerStats:
    @pytest.mark.asyncio
    async def test_connection_stats_initialized(self):
        manager = WebSocketConnectionManager()
        ws = AsyncMock(spec=WebSocket)
        ws.headers = {}
        info = await manager.connect(ws, client_id="client1")
        assert info.stats is not None
        assert info.stats.messages_sent == 0
        assert info.stats.bytes_sent == 0

    @pytest.mark.asyncio
    async def test_get_connection_stats(self):
        manager = WebSocketConnectionManager()
        ws = AsyncMock(spec=WebSocket)
        ws.headers = {}
        await manager.connect(ws, client_id="client1")

        stats = await manager.get_connection_stats("client1")
        assert stats is not None
        assert "bytes_sent" in stats
        assert "messages_sent" in stats

    @pytest.mark.asyncio
    async def test_get_connection_stats_nonexistent(self):
        manager = WebSocketConnectionManager()
        stats = await manager.get_connection_stats("nonexistent")
        assert stats is None

    @pytest.mark.asyncio
    async def test_stats_track_on_handle_message(self):
        manager = WebSocketConnectionManager()
        ws = AsyncMock(spec=WebSocket)
        ws.headers = {}
        await manager.connect(ws, client_id="client1")

        await manager.handle_message("client1", json.dumps({
            "type": "ping",
        }))

        info = manager.get_connection("client1")
        assert info is not None
        assert info.stats.messages_received == 1
        assert info.stats.bytes_received > 0


# ======================================================================
# Manager: Reconnection
# ======================================================================


class TestManagerReconnect:
    @pytest.mark.asyncio
    async def test_generate_reconnect_token(self):
        manager = WebSocketConnectionManager()
        ws = AsyncMock(spec=WebSocket)
        ws.headers = {}
        info = await manager.connect(ws, client_id="client1")
        assert info is not None

        token = await manager.generate_reconnect_token("client1")
        assert token is not None
        assert token.startswith("rtok:")
        assert info.reconnect_token == token

    @pytest.mark.asyncio
    async def test_validate_reconnect_token_valid(self):
        manager = WebSocketConnectionManager()
        ws = AsyncMock(spec=WebSocket)
        ws.headers = {}
        await manager.connect(ws, client_id="client1")

        token = await manager.generate_reconnect_token("client1")
        cid = await manager.validate_reconnect_token(token)
        assert cid == "client1"

    @pytest.mark.asyncio
    async def test_validate_reconnect_token_invalid(self):
        manager = WebSocketConnectionManager()
        cid = await manager.validate_reconnect_token("invalid-token")
        assert cid is None

    @pytest.mark.asyncio
    async def test_revoke_reconnect_token(self):
        manager = WebSocketConnectionManager()
        ws = AsyncMock(spec=WebSocket)
        ws.headers = {}
        await manager.connect(ws, client_id="client1")

        await manager.generate_reconnect_token("client1")
        result = await manager.revoke_reconnect_token("client1")
        assert result is True

        info = manager.get_connection("client1")
        assert info is not None
        assert info.reconnect_token is None

    @pytest.mark.asyncio
    async def test_revoke_reconnect_token_nonexistent(self):
        manager = WebSocketConnectionManager()
        result = await manager.revoke_reconnect_token("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_reconnect_state_restore(self):
        manager = WebSocketConnectionManager()
        ws1 = AsyncMock(spec=WebSocket)
        ws1.headers = {}
        info1 = await manager.connect(ws1, client_id="client1")

        # Set up some state
        await manager.subscribe("client1", "test.event")
        await manager.join_room("client1", "room1")

        token = await manager.generate_reconnect_token("client1")

        # Now reconnect with a new websocket
        ws2 = AsyncMock(spec=WebSocket)
        ws2.headers = {}
        info2 = await manager.connect(ws2, client_id="client1", reconnect_token=token)

        assert info2 is not None
        assert info2.client_id == "client1"
        # Subscription and room should be restored
        assert "test.event" in info2.subscriptions
        assert "room1" in info2.rooms

    @pytest.mark.asyncio
    async def test_reconnect_updates_websocket(self):
        manager = WebSocketConnectionManager()
        ws1 = AsyncMock(spec=WebSocket)
        ws1.headers = {}
        await manager.connect(ws1, client_id="client1")

        token = await manager.generate_reconnect_token("client1")

        ws2 = AsyncMock(spec=WebSocket)
        ws2.headers = {}
        info2 = await manager.connect(ws2, client_id="client1", reconnect_token=token)

        assert info2 is not None
        # WebSocket should now be the new one
        assert info2.websocket == ws2

    @pytest.mark.asyncio
    async def test_reconnect_with_expired_token(self):
        manager = WebSocketConnectionManager()
        ws = AsyncMock(spec=WebSocket)
        ws.headers = {}
        await manager.connect(ws, client_id="client1")

        token = await manager.generate_reconnect_token("client1")

        # Expire the token manually
        info = manager.get_connection("client1")
        assert info is not None
        old_expiry = info.reconnect_token_expires
        info.reconnect_token_expires = time.monotonic() - 1

        # Validate should return None for expired token
        cid = await manager.validate_reconnect_token(token)
        assert cid is None

        # Restore expiry, should work again
        info.reconnect_token_expires = old_expiry
        cid = await manager.validate_reconnect_token(token)
        assert cid == "client1"

    @pytest.mark.asyncio
    async def test_reconnect_increments_count(self):
        manager = WebSocketConnectionManager()
        ws1 = AsyncMock(spec=WebSocket)
        ws1.headers = {}
        await manager.connect(ws1, client_id="client1")

        token = await manager.generate_reconnect_token("client1")

        ws2 = AsyncMock(spec=WebSocket)
        ws2.headers = {}
        info = await manager.connect(ws2, client_id="client1", reconnect_token=token)
        assert info is not None
        assert info.reconnect_count == 1

    @pytest.mark.asyncio
    async def test_reconnect_token_reuse_blocked(self):
        manager = WebSocketConnectionManager()
        ws1 = AsyncMock(spec=WebSocket)
        ws1.headers = {}
        await manager.connect(ws1, client_id="client1")

        token = await manager.generate_reconnect_token("client1")

        ws2 = AsyncMock(spec=WebSocket)
        ws2.headers = {}
        info = await manager.connect(ws2, client_id="client1", reconnect_token=token)
        assert info is not None

        # Token should be invalidated after use - validate returns None
        cid = await manager.validate_reconnect_token(token)
        assert cid is None

    @pytest.mark.asyncio
    async def test_reconnect_offline_queue_drained(self):
        manager = WebSocketConnectionManager()
        ws1 = AsyncMock(spec=WebSocket)
        ws1.headers = {}
        await manager.connect(ws1, client_id="client1")

        token = await manager.generate_reconnect_token("client1")

        # Queue offline messages
        info = manager.get_connection("client1")
        assert info is not None
        assert info.offline_queue is not None
        await info.offline_queue.put({"type": "offline_msg"})

        ws2 = AsyncMock(spec=WebSocket)
        ws2.headers = {}
        info2 = await manager.connect(ws2, client_id="client1", reconnect_token=token)
        assert info2 is not None

        # Offline queue should be drained after reconnect
        assert info2.offline_queue is not None
        assert info2.offline_queue.qsize == 0


# ======================================================================
# Manager: Active heartbeat
# ======================================================================


class TestManagerHeartbeat:
    @pytest.mark.asyncio
    async def test_handle_heartbeat_ack(self):
        manager = WebSocketConnectionManager()
        ws = AsyncMock(spec=WebSocket)
        ws.headers = {}
        await manager.connect(ws, client_id="client1")

        info = manager.get_connection("client1")
        assert info is not None

        # Simulate a pending heartbeat
        hb_id = "hb-test123"
        info.pending_heartbeats[hb_id] = time.monotonic() - 0.1  # 100ms ago

        hb_ack_raw = json.dumps({
            "type": "heartbeat_ack",
            "payload": {"heartbeat_id": hb_id},
        })
        await manager.handle_message("client1", hb_ack_raw)

        # Latency should be recorded
        assert info.stats.latency_samples
        assert info.stats.latency_min > 0

    @pytest.mark.asyncio
    async def test_handle_heartbeat_ack_unknown_id(self):
        manager = WebSocketConnectionManager()
        ws = AsyncMock(spec=WebSocket)
        ws.headers = {}
        await manager.connect(ws, client_id="client1")

        hb_ack_raw = json.dumps({
            "type": "heartbeat_ack",
            "payload": {"heartbeat_id": "nonexistent"},
        })
        response = await manager.handle_message("client1", hb_ack_raw)
        assert response is None

    @pytest.mark.asyncio
    async def test_heartbeat_updates_last_active(self):
        manager = WebSocketConnectionManager()
        ws = AsyncMock(spec=WebSocket)
        ws.headers = {}
        info = await manager.connect(ws, client_id="client1")
        assert info is not None

        old = info.last_active_heartbeat
        await asyncio.sleep(0.01)

        hb_ack_raw = json.dumps({
            "type": "heartbeat_ack",
            "payload": {"heartbeat_id": "test"},
        })
        await manager.handle_message("client1", hb_ack_raw)

        assert info.last_active_heartbeat > old


# ======================================================================
# AuthSession: reconnect_token
# ======================================================================


class TestAuthSessionReconnect:
    def test_reconnect_token_default(self):
        from app.ws.session import AuthSession
        s = AuthSession()
        assert s.reconnect_token == ""
        assert s.reconnect_token_valid is False

    def test_set_reconnect_token(self):
        from app.ws.session import AuthSession
        s = AuthSession()
        s.set_reconnect_token("rtok:abc:123", ttl=300)
        assert s.reconnect_token == "rtok:abc:123"
        assert s.reconnect_token_valid is True

    def test_expired_reconnect_token(self):
        from app.ws.session import AuthSession
        s = AuthSession()
        s.set_reconnect_token("rtok:abc:123", ttl=0)
        assert s.reconnect_token_valid is False

    def test_reconnect_token_components(self):
        from app.ws.session import AuthSession
        s = AuthSession()
        s.set_reconnect_token("rtok:abc:123", ttl=300)
        assert s.reconnect_token_expires > 0
        import time
        assert s.reconnect_token_expires > time.monotonic()

    def test_state_snapshot(self):
        from app.ws.session import AuthSession
        s = AuthSession(state_snapshot={"subscriptions": {"test.*"}, "rooms": ["room1"]})
        assert s.state_snapshot["subscriptions"] == {"test.*"}
        assert "room1" in s.state_snapshot["rooms"]


# ======================================================================
# Manager: Offline queue integration
# ======================================================================


class TestManagerOfflineQueue:
    @pytest.mark.asyncio
    async def test_offline_queue_on_disconnect(self):
        manager = WebSocketConnectionManager()
        ws = AsyncMock(spec=WebSocket)
        ws.headers = {}
        info = await manager.connect(ws, client_id="client1")
        assert info is not None

        # Queue some unacked messages
        msg = ServerMessage(type=WSMessageType.MESSAGE, payload={"text": "test"})
        await manager.send("client1", msg, require_ack=True)

        # Disconnect - should move unacked to offline queue
        await manager.disconnect("client1")

        # Verify offline queue has the pending message
        assert info.offline_queue is not None
        assert info.offline_queue.qsize == 1

    @pytest.mark.asyncio
    async def test_offline_queue_no_retry_queue(self):
        """Offline queue still works even without retry queue."""
        from app.core.config import Config
        old = Config.WS_RELIABLE_SEND_ENABLED
        Config.WS_RELIABLE_SEND_ENABLED = False
        try:
            manager = WebSocketConnectionManager()
            ws = AsyncMock(spec=WebSocket)
            ws.headers = {}
            info = await manager.connect(ws, client_id="client1")
            assert info is not None
            assert info.retry_queue is None
            assert info.offline_queue is not None
        finally:
            Config.WS_RELIABLE_SEND_ENABLED = old


# ======================================================================
# ConnectionInfo: config-based initialization
# ======================================================================


class TestConnectionInfoReliability:
    def test_reliability_defaults(self):
        ws = AsyncMock(spec=WebSocket)
        info = ConnectionInfo("client1", ws)
        assert info.stats is not None
        assert info.retry_queue is not None
        assert info.offline_queue is not None
        assert info.reconnect_token is None

    def test_pending_heartbeats_init(self):
        ws = AsyncMock(spec=WebSocket)
        info = ConnectionInfo("client1", ws)
        assert info.pending_heartbeats == {}
        assert info.last_active_heartbeat > 0
