from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

from fastapi import WebSocket

from app.core.logger import JarvisLogger
from app.ws.manager import WebSocketConnectionManager
from app.ws.schemas import ServerMessage, WSMessageType


class AIStreamManager:
    """Manages live AI streaming sessions over WebSocket connections.

    Each call to ``start_stream`` launches an asyncio task that iterates
    an ``AIStreamResponse`` (from ``AIManager.ask_stream()``) and
    pushes chunk / complete / error events to the WebSocket client.
    """

    def __init__(
        self,
        ai_manager: Any,
        ws_manager: WebSocketConnectionManager,
    ) -> None:
        self._ai = ai_manager
        self._ws = ws_manager
        self._streams: dict[str, _StreamState] = {}
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def start_stream(
        self,
        client_id: str,
        provider: str,
        prompt: str = "",
        *,
        conversation_id: str | None = None,
        prompt_template: str | None = None,
        template_variables: dict[str, str] | None = None,
        stream_id: str | None = None,
    ) -> str:
        """Begin an AI streaming session.

        Returns the generated (or supplied) *stream_id*.
        """
        sid = stream_id or f"ws-{uuid.uuid4().hex[:12]}"
        stream = self._ai.ask_stream(
            provider,
            prompt,
            conversation_id=conversation_id,
            prompt_template=prompt_template,
            template_variables=template_variables,
        )
        task = asyncio.create_task(
            self._run_stream(sid, client_id, stream, provider, conversation_id)
        )
        state = _StreamState(
            stream_id=sid,
            client_id=client_id,
            task=task,
            stream=stream,
            provider=provider,
        )
        async with self._lock:
            self._streams[sid] = state
        await asyncio.sleep(0)
        return sid

    async def cancel_stream(self, client_id: str, stream_id: str) -> bool:
        """Cancel a specific stream.  Returns ``True`` if cancelled."""
        async with self._lock:
            s = self._streams.get(stream_id)
            if s is None or s.client_id != client_id:
                return False
            s.task.cancel()
            s.stream.cancel()
            del self._streams[stream_id]
        return True

    async def cancel_all(self, client_id: str) -> int:
        """Cancel every stream owned by *client_id*.  Returns count."""
        count = 0
        async with self._lock:
            for sid, state in list(self._streams.items()):
                if state.client_id == client_id:
                    state.task.cancel()
                    state.stream.cancel()
                    del self._streams[sid]
                    count += 1
        return count

    async def cleanup(self, client_id: str) -> None:
        """Cancel all streams for a disconnected client."""
        cancelled = await self.cancel_all(client_id)
        if cancelled:
            JarvisLogger.info(
                "Cleaned up %d stream(s) for disconnected client %s",
                cancelled,
                client_id,
            )

    async def get_active_count(self, client_id: str | None = None) -> int:
        """Count active streams, optionally filtered by client."""
        async with self._lock:
            if client_id is None:
                return len(self._streams)
            return sum(
                1 for s in self._streams.values() if s.client_id == client_id
            )

    # ------------------------------------------------------------------
    # Incoming message routing
    # ------------------------------------------------------------------

    async def try_handle_message(
        self,
        client_id: str,
        raw: str,
    ) -> bool:
        """Try to parse *raw* as an AI stream control message.

        Returns ``True`` if the message was recognised and handled
        (responses are sent internally via ``self._ws``).
        """
        try:
            data = json.loads(raw)
            msg_type = data.get("type")
        except json.JSONDecodeError:
            return False

        payload: dict = data.get("payload") or {}

        if msg_type == "ai.stream.start":
            await self._handle_start(client_id, payload)
            return True
        if msg_type == "ai.stream.cancel":
            await self._handle_cancel(client_id, payload)
            return True

        return False

    async def _handle_start(
        self,
        client_id: str,
        payload: dict[str, Any],
    ) -> None:
        provider: str = payload.get("provider", "")
        if not provider:
            await self._ws.send(
                client_id,
                ServerMessage(
                    type=WSMessageType.ERROR,
                    payload={"error": "provider is required for ai.stream.start"},
                ),
            )
            return
        prompt: str = payload.get("prompt", "")
        conversation_id: str | None = payload.get("conversation_id")
        prompt_template: str | None = payload.get("prompt_template")
        template_variables: dict | None = payload.get("template_variables")
        try:
            sid = await self.start_stream(
                client_id,
                provider,
                prompt,
                conversation_id=conversation_id,
                prompt_template=prompt_template,
                template_variables=template_variables,
            )
            await self._ws.send(
                client_id,
                ServerMessage(
                    type=WSMessageType.AI_STREAM_STARTED,
                    event="ai.stream.started",
                    payload={
                        "stream_id": sid,
                        "conversation_id": conversation_id,
                        "provider": provider,
                    },
                ),
            )
        except Exception as exc:
            JarvisLogger.exception("AI stream start failed: %s", exc)
            await self._ws.send(
                client_id,
                ServerMessage(
                    type=WSMessageType.ERROR,
                    payload={
                        "error": f"Failed to start AI stream: {exc}",
                        "provider": provider,
                    },
                ),
            )

    async def _handle_cancel(
        self,
        client_id: str,
        payload: dict[str, Any],
    ) -> None:
        stream_id: str | None = payload.get("stream_id")
        if stream_id:
            await self.cancel_stream(client_id, stream_id)

    # ------------------------------------------------------------------
    # Internal: stream runner
    # ------------------------------------------------------------------

    async def _run_stream(
        self,
        stream_id: str,
        client_id: str,
        stream: Any,
        provider: str,
        conversation_id: str | None,
    ) -> None:
        try:
            await asyncio.sleep(0)
            for chunk in stream:
                if not await self._ws.is_connected(client_id):
                    break
                sent = await self._ws.send(
                    client_id,
                    ServerMessage(
                        type=WSMessageType.AI_STREAM_CHUNK,
                        event="ai.stream.chunk",
                        payload={
                            "stream_id": stream_id,
                            "conversation_id": conversation_id,
                            "content": chunk.content,
                            "provider": provider,
                            "model": getattr(stream, "_model", ""),
                        },
                    ),
                )
                if not sent:
                    break

            if await self._ws.is_connected(client_id):
                final = stream.final_response()
                meta = dict(final.metadata) if final.metadata else {}
                finish_reason: str | None = meta.pop("finish_reason", None)
                await self._ws.send(
                    client_id,
                    ServerMessage(
                        type=WSMessageType.AI_STREAM_COMPLETE,
                        event="ai.stream.complete",
                        payload={
                            "stream_id": stream_id,
                            "conversation_id": conversation_id,
                            "content": str(final),
                            "provider": final.provider,
                            "model": final.model,
                            "latency_ms": final.latency_ms,
                            "finish_reason": finish_reason,
                            "usage": meta,
                        },
                    ),
                )

        except asyncio.CancelledError:
            if await self._ws.is_connected(client_id):
                await self._ws.send(
                    client_id,
                    ServerMessage(
                        type=WSMessageType.AI_STREAM_CANCELLED,
                        event="ai.stream.cancelled",
                        payload={
                            "stream_id": stream_id,
                            "conversation_id": conversation_id,
                        },
                    ),
                )
        except Exception as exc:
            JarvisLogger.exception("AI stream %s failed: %s", stream_id, exc)
            if await self._ws.is_connected(client_id):
                await self._ws.send(
                    client_id,
                    ServerMessage(
                        type=WSMessageType.AI_STREAM_ERROR,
                        event="ai.stream.error",
                        payload={
                            "stream_id": stream_id,
                            "conversation_id": conversation_id,
                            "error": str(exc),
                        },
                    ),
                )
        finally:
            async with self._lock:
                self._streams.pop(stream_id, None)


class _StreamState:
    """Internal bookkeeping for an active AI stream."""

    __slots__ = ("stream_id", "client_id", "task", "stream", "provider")

    def __init__(
        self,
        stream_id: str,
        client_id: str,
        task: asyncio.Task[None],
        stream: Any,
        provider: str,
    ) -> None:
        self.stream_id = stream_id
        self.client_id = client_id
        self.task = task
        self.stream = stream
        self.provider = provider
