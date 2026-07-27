from __future__ import annotations

import time
from typing import Any


class WebSocketDiagnostics:
    """Generates structured diagnostic reports for the WebSocket subsystem."""

    def __init__(
        self,
        ws_manager: Any,
        session_store: Any = None,
        authenticator: Any = None,
        metrics_service: Any = None,
        health_monitor: Any = None,
        runtime_config: Any = None,
    ) -> None:
        self._ws = ws_manager
        self._session_store = session_store
        self._authenticator = authenticator
        self._metrics = metrics_service
        self._health = health_monitor
        self._runtime_config = runtime_config

    async def generate(self) -> dict[str, Any]:
        """Generate a comprehensive diagnostic report."""
        return {
            "manager": await self._manager_state(),
            "sessions": await self._session_state(),
            "retry_queues": await self._retry_queue_state(),
            "offline_queues": await self._offline_queue_state(),
            "heartbeat": await self._heartbeat_status(),
            "rooms": await self._room_usage(),
            "subscriptions": await self._subscriptions(),
            "active_streams": await self._active_streams(),
            "commands": [],
            "transfers": [],
            "auth_stats": await self._auth_statistics(),
            "metrics": await self._metrics.snapshot() if self._metrics else {},
            "runtime_config": self._runtime_config.get_all() if self._runtime_config else {},
            "timestamp": time.time(),
        }

    async def _manager_state(self) -> dict[str, Any]:
        cids = await self._ws.get_connected_ids()
        connections = []
        for cid in cids:
            info = self._ws.get_connection(cid)
            if info:
                connections.append({
                    "client_id": cid,
                    "connected_seconds": time.time() - info.connected_at if hasattr(info, "connected_at") else 0,
                    "rooms": list(info.rooms) if hasattr(info, "rooms") else [],
                    "subscriptions": list(info.subscriptions) if hasattr(info, "subscriptions") else [],
                    "reconnect_count": getattr(info, "reconnect_count", 0),
                    "has_retry_queue": getattr(info, "retry_queue", None) is not None,
                    "has_offline_queue": getattr(info, "offline_queue", None) is not None,
                })
        return {
            "active_connections": len(cids),
            "connections": connections,
            "room_count": len(self._ws._rooms) if hasattr(self._ws, "_rooms") else 0,
        }

    async def _session_state(self) -> dict[str, Any]:
        if self._session_store is None:
            return {"available": False}
        sessions = []
        if hasattr(self._session_store, "_sessions"):
            for sid, sess in list(self._session_store._sessions.items()):
                sessions.append({
                    "session_id": sid,
                    "client_id": getattr(sess, "client_id", ""),
                    "is_authenticated": getattr(sess, "is_authenticated", False),
                    "auth_method": getattr(sess, "auth_method", ""),
                    "time_remaining": getattr(sess, "time_remaining", 0),
                })
        return {
            "available": True,
            "total_sessions": len(sessions),
            "sessions": sessions[:50],
        }

    async def _retry_queue_state(self) -> dict[str, Any]:
        cids = await self._ws.get_connected_ids()
        queues = []
        total_pending = 0
        for cid in cids:
            info = self._ws.get_connection(cid)
            rq = getattr(info, "retry_queue", None)
            if rq is not None:
                count = await rq.pending_count()
                if count > 0:
                    queues.append({"client_id": cid, "pending": count})
                    total_pending += count
        return {
            "clients_with_pending": len(queues),
            "total_pending": total_pending,
            "queues": queues,
        }

    async def _offline_queue_state(self) -> dict[str, Any]:
        cids = await self._ws.get_connected_ids()
        queues = []
        total_queued = 0
        for cid in cids:
            info = self._ws.get_connection(cid)
            oq = getattr(info, "offline_queue", None)
            if oq is not None and oq.qsize > 0:
                queues.append({"client_id": cid, "size": oq.qsize})
                total_queued += oq.qsize
        return {
            "clients_with_queued": len(queues),
            "total_queued": total_queued,
            "queues": queues,
        }

    async def _heartbeat_status(self) -> dict[str, Any]:
        now = time.monotonic()
        cids = await self._ws.get_connected_ids()
        heartbeats = []
        stale_count = 0
        for cid in cids:
            info = self._ws.get_connection(cid)
            if info:
                last = getattr(info, "last_heartbeat", 0)
                age = now - last
                hb = {"client_id": cid, "age_seconds": round(age, 2)}
                if hasattr(info, "last_active_heartbeat"):
                    hb["active_age"] = round(now - info.last_active_heartbeat, 2)
                heartbeats.append(hb)
                if age > 30:
                    stale_count += 1
        return {
            "stale_count": stale_count,
            "total_checked": len(heartbeats),
            "heartbeats": heartbeats,
        }

    async def _room_usage(self) -> dict[str, Any]:
        if not hasattr(self._ws, "_rooms"):
            return {"total_rooms": 0, "rooms": []}
        rooms = []
        for name, members in list(self._ws._rooms.items()):
            rooms.append({"name": name, "member_count": len(members)})
        return {"total_rooms": len(rooms), "rooms": rooms}

    async def _subscriptions(self) -> dict[str, Any]:
        cids = await self._ws.get_connected_ids()
        by_client = {}
        total = 0
        for cid in cids:
            info = self._ws.get_connection(cid)
            if info and hasattr(info, "subscriptions"):
                subs = list(info.subscriptions)
                if subs:
                    by_client[cid] = subs
                    total += len(subs)
        return {"total_subscriptions": total, "by_client": by_client}

    async def _active_streams(self) -> dict[str, Any]:
        return {"count": 0, "streams": []}

    async def _auth_statistics(self) -> dict[str, Any]:
        if self._authenticator is None:
            return {"available": False}
        store = None
        if hasattr(self._authenticator, "_session_store"):
            store = self._authenticator._session_store
        if store is None:
            return {"available": False}
        total = 0
        authenticated = 0
        if hasattr(store, "_sessions"):
            for sess in store._sessions.values():
                total += 1
                if getattr(sess, "is_authenticated", False):
                    authenticated += 1
        return {
            "available": True,
            "total_sessions": total,
            "authenticated": authenticated,
            "anonymous": total - authenticated,
        }
