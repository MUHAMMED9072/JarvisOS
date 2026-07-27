from __future__ import annotations

import asyncio
from typing import Any

from app.core.event_bus import EventBus
from app.core.logger import JarvisLogger
from app.ws.events import (
    EventEnvelope,
    EventReplayBuffer,
    make_envelope,
)
from app.ws.manager import WebSocketConnectionManager


class EventStreamBridge:
    def __init__(
        self,
        event_bus: EventBus,
        ws_manager: WebSocketConnectionManager,
        replay_buffer: EventReplayBuffer | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._ws_manager = ws_manager
        self._buffer = replay_buffer or EventReplayBuffer()
        self._subscribed: bool = False

    def start(self) -> None:
        if self._subscribed:
            return
        self._event_bus.subscribe_wildcard("*", self._on_event)
        self._subscribed = True
        JarvisLogger.info("EventStreamBridge started")

    def stop(self) -> None:
        if not self._subscribed:
            return
        self._event_bus.unsubscribe("*", self._on_event)
        self._subscribed = False
        JarvisLogger.info("EventStreamBridge stopped")

    def _on_event(self, event: str, **_data: Any) -> None:
        envelope = make_envelope(event, dict(_data), source="event_bus")
        self._buffer.push(envelope)

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            JarvisLogger.warning("No running event loop; skipping dispatch")
            return

        asyncio.run_coroutine_threadsafe(
            self._dispatch_to_clients(envelope), loop
        )

    async def _dispatch_to_clients(self, envelope: EventEnvelope) -> None:
        client_ids = await self._ws_manager.get_subscribed_clients_for_event(
            envelope.event
        )
        for cid in client_ids:
            await self._ws_manager.enqueue_event(cid, envelope)

    def replay(self, event_pattern: str) -> list[EventEnvelope]:
        return self._buffer.replay(event_pattern)

    @property
    def buffer(self) -> EventReplayBuffer:
        return self._buffer
