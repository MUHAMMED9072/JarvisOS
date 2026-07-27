from __future__ import annotations

import asyncio
import time
from typing import Any


class WebSocketMaintenance:
    """Maintenance operations for the WebSocket subsystem."""

    def __init__(
        self,
        ws_manager: Any,
        session_store: Any = None,
        authenticator: Any = None,
        metrics_service: Any = None,
        runtime_config: Any = None,
        event_bus: Any = None,
    ) -> None:
        self._ws = ws_manager
        self._session_store = session_store
        self._authenticator = authenticator
        self._metrics = metrics_service
        self._runtime_config = runtime_config
        self._event_bus = event_bus

    async def clear_retry_queues(self, client_id: str | None = None) -> dict[str, Any]:
        cleared = 0
        if client_id:
            info = self._ws.get_connection(client_id)
            rq = getattr(info, "retry_queue", None)
            if rq:
                msgs = await rq.clear()
                cleared = len(msgs)
        else:
            cids = await self._ws.get_connected_ids()
            for cid in cids:
                info = self._ws.get_connection(cid)
                rq = getattr(info, "retry_queue", None)
                if rq:
                    msgs = await rq.clear()
                    cleared += len(msgs)
        self._publish("ws.maintenance.completed", operation="clear_retry_queues", cleared=cleared)
        return {"operation": "clear_retry_queues", "cleared": cleared}

    async def clear_offline_queues(self, client_id: str | None = None) -> dict[str, Any]:
        cleared = 0
        if client_id:
            info = self._ws.get_connection(client_id)
            oq = getattr(info, "offline_queue", None)
            if oq:
                msgs = await oq.drain()
                cleared = len(msgs)
        else:
            cids = await self._ws.get_connected_ids()
            for cid in cids:
                info = self._ws.get_connection(cid)
                oq = getattr(info, "offline_queue", None)
                if oq:
                    msgs = await oq.drain()
                    cleared += len(msgs)
        self._publish("ws.maintenance.completed", operation="clear_offline_queues", cleared=cleared)
        return {"operation": "clear_offline_queues", "cleared": cleared}

    async def clear_inactive_sessions(self) -> dict[str, Any]:
        removed = 0
        if self._session_store is not None:
            removed = await self._session_store.cleanup_expired()
        self._publish("ws.maintenance.completed", operation="clear_inactive_sessions", removed=removed)
        return {"operation": "clear_inactive_sessions", "removed": removed}

    async def prune_expired_tokens(self) -> dict[str, Any]:
        pruned = 0
        cids = await self._ws.get_connected_ids()
        now = time.monotonic()
        for cid in cids:
            info = self._ws.get_connection(cid)
            if info:
                token_exp = getattr(info, "reconnect_token_expires", 0)
                if token_exp > 0 and now >= token_exp:
                    info.reconnect_token = None
                    info.reconnect_token_expires = 0.0
                    pruned += 1
        self._publish("ws.maintenance.completed", operation="prune_expired_tokens", pruned=pruned)
        return {"operation": "prune_expired_tokens", "pruned": pruned}

    async def prune_expired_acks(self) -> dict[str, Any]:
        pruned = 0
        cids = await self._ws.get_connected_ids()
        for cid in cids:
            info = self._ws.get_connection(cid)
            rq = getattr(info, "retry_queue", None)
            if rq:
                entries = await rq.get_all_pending()
                for entry in entries:
                    if entry.is_expired:
                        await rq.ack(entry.message_id)
                        pruned += 1
        self._publish("ws.maintenance.completed", operation="prune_expired_acks", pruned=pruned)
        return {"operation": "prune_expired_acks", "pruned": pruned}

    async def reset_metrics(self) -> dict[str, Any]:
        if self._metrics is not None:
            await self._metrics.reset()
        self._publish("ws.maintenance.completed", operation="reset_metrics")
        return {"operation": "reset_metrics", "success": True}

    async def run_all(self) -> dict[str, Any]:
        results = {}
        results["retry_queues"] = await self.clear_retry_queues()
        results["offline_queues"] = await self.clear_offline_queues()
        results["sessions"] = await self.clear_inactive_sessions()
        results["tokens"] = await self.prune_expired_tokens()
        results["acks"] = await self.prune_expired_acks()
        results["metrics"] = await self.reset_metrics()
        return {"operations": results}

    def _publish(self, event: str, **data: Any) -> None:
        if self._event_bus is not None:
            try:
                self._event_bus.publish(event, **data)
            except Exception:
                pass
