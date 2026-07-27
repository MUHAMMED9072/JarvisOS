from __future__ import annotations

import asyncio
import fnmatch
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from app.core.logger import JarvisLogger
from app.cortex.models import CortexRequest
from app.ws.manager import WebSocketConnectionManager
from app.ws.schemas import ServerMessage, WSMessageType


class CommandExecutionManager:
    """Manages remote command execution over WebSocket connections.

    Each ``command.execute`` message creates an asyncio task that runs
    the command through the existing Cortex + Dispatcher pipeline (or
    directly via AIManager / SkillManager).  Results, errors, and
    progress updates are sent back to the client via the WebSocket
    connection manager.
    """

    def __init__(
        self,
        ws_manager: WebSocketConnectionManager,
        registry: Any,
    ) -> None:
        self._ws = ws_manager
        self._registry = registry
        self._commands: dict[str, _CmdState] = {}
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_active_count(self, client_id: str | None = None) -> int:
        """Number of active (running or pending) commands."""
        async with self._lock:
            if client_id is None:
                return len(self._commands)
            return sum(
                1 for c in self._commands.values() if c.client_id == client_id
            )

    async def cleanup(self, client_id: str) -> None:
        """Cancel all commands for a disconnected client."""
        count = await self.cancel_all(client_id)
        if count:
            JarvisLogger.info(
                "Cleaned up %d command(s) for disconnected client %s",
                count,
                client_id,
            )

    async def cancel_all(self, client_id: str) -> int:
        """Cancel every command owned by *client_id*.  Returns the count."""
        count = 0
        async with self._lock:
            for cid, state in list(self._commands.items()):
                if state.client_id == client_id:
                    state.task.cancel()
                    del self._commands[cid]
                    count += 1
        return count

    # ------------------------------------------------------------------
    # Incoming message routing
    # ------------------------------------------------------------------

    async def try_handle_message(
        self,
        client_id: str,
        raw: str,
    ) -> bool:
        """Parse *raw* as a remote command message.

        Returns ``True`` if the message was recognised and handled.
        """
        try:
            data = json.loads(raw)
            msg_type = data.get("type")
        except json.JSONDecodeError:
            return False

        payload: dict = data.get("payload") or {}

        if msg_type == "command.execute":
            await self._handle_execute(client_id, payload)
            return True
        if msg_type == "command.cancel":
            await self._handle_cancel(client_id, payload)
            return True

        return False

    async def _check_permission(
        self,
        client_id: str,
        permission: str,
    ) -> bool:
        info = self._ws.get_connection(client_id)
        if info is None:
            return False
        metadata = info.metadata or {}
        if not isinstance(metadata, dict):
            return True
        session_id = metadata.get("session_id")
        if not session_id:
            return True
        roles = metadata.get("roles", [])
        if "admin" in roles:
            return True
        perms = metadata.get("permissions", set())
        if isinstance(perms, list):
            perms = set(perms)
        if permission in perms:
            return True
        for perm_pattern in perms:
            if fnmatch.fnmatch(permission, perm_pattern):
                return True
        return False

    async def _handle_execute(
        self,
        client_id: str,
        payload: dict[str, Any],
    ) -> None:
        """Process an incoming ``command.execute`` message."""
        if not await self._check_permission(client_id, "command.execute"):
            return

        command_type: str = payload.get("type", "command")
        command_id: str = payload.get("command_id") or f"cmd-{uuid.uuid4().hex[:12]}"
        correlation_id: str = payload.get("correlation_id") or uuid.uuid4().hex

        state = _CmdState(
            command_id=command_id,
            client_id=client_id,
            command_type=command_type,
            payload=payload,
            correlation_id=correlation_id,
        )

        task = asyncio.create_task(
            self._run_command(state, client_id, payload)
        )
        state.task = task

        async with self._lock:
            self._commands[command_id] = state

    async def _handle_cancel(
        self,
        client_id: str,
        payload: dict[str, Any],
    ) -> None:
        """Process an incoming ``command.cancel`` message."""
        command_id: str | None = payload.get("command_id")
        if command_id is None:
            return

        async with self._lock:
            state = self._commands.get(command_id)
            if state is None or state.client_id != client_id:
                return
            state.task.cancel()
            del self._commands[command_id]

        if await self._ws.is_connected(client_id):
            await self._ws.send(
                client_id,
                _result_msg(
                    command_id=command_id,
                    command_type=state.command_type,
                    status="cancelled",
                    correlation_id=state.correlation_id,
                ),
            )

    # ------------------------------------------------------------------
    # Command execution
    # ------------------------------------------------------------------

    async def _run_command(
        self,
        state: _CmdState,
        client_id: str,
        payload: dict[str, Any],
    ) -> None:
        """Execute a command in a thread pool and send the result."""
        command_type = state.command_type
        command_id = state.command_id

        state.started_at = time.monotonic()

        try:
            await self._send_progress(
                client_id, command_id, command_type, state,
                status="running", progress=0,
                message=f"Starting {command_type} execution",
            )

            loop = asyncio.get_running_loop()
            if command_type == "command":
                result = await loop.run_in_executor(
                    None, self._exec_command, payload,
                )
            elif command_type == "skill":
                result = await loop.run_in_executor(
                    None, self._exec_skill, payload,
                )
            elif command_type == "ai.chat":
                result = await loop.run_in_executor(
                    None, self._exec_ai_chat, payload,
                )
            elif command_type == "ai.plan":
                result = await loop.run_in_executor(
                    None, self._exec_ai_plan, payload,
                )
            elif command_type == "ai.reason":
                result = await loop.run_in_executor(
                    None, self._exec_ai_reason, payload,
                )
            else:
                await self._send_error(
                    client_id, command_id, command_type, state,
                    error=f"Unknown command type: {command_type}",
                )
                return

            state.completed_at = time.monotonic()
            elapsed = round((state.completed_at - state.started_at) * 1000, 2)

            if result.get("success"):
                await self._send_result(
                    client_id, command_id, command_type, state,
                    success=True, data=result.get("data"),
                    message=result.get("message", ""),
                    elapsed=elapsed,
                )
            else:
                await self._send_error(
                    client_id, command_id, command_type, state,
                    error=result.get("message", "Execution failed"),
                    elapsed=elapsed,
                )

        except asyncio.CancelledError:
            pass
        except Exception as exc:
            JarvisLogger.exception("Command %s failed: %s", command_id, exc)
            state.completed_at = time.monotonic()
            elapsed = round((state.completed_at - state.started_at) * 1000, 2)
            await self._send_error(
                client_id, command_id, command_type, state,
                error=str(exc), elapsed=elapsed,
            )
        finally:
            async with self._lock:
                self._commands.pop(command_id, None)

    # ------------------------------------------------------------------
    # Command type implementations (run in thread pool)
    # ------------------------------------------------------------------

    def _exec_command(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Execute a normal JARVIS command via CortexPipeline + Dispatcher."""
        text: str = payload.get("text", "")
        source: str = payload.get("source", "websocket")
        brain: str | None = payload.get("brain")

        try:
            from app.cortex.pipeline import CortexPipeline

            pipeline = CortexPipeline()
            request = pipeline.process(text, source=source)

            if brain:
                request.brain = brain

            from app.cortex.dispatcher import Dispatcher
            dispatcher = Dispatcher(self._registry)

            result = dispatcher.dispatch(request)

            return {
                "success": result.success,
                "message": result.message,
                "data": {
                    "skill": result.skill,
                    "execution_time": result.execution_time,
                    "intent": request.intent,
                    "confidence": request.confidence,
                    "entities": request.entities,
                    "brain": request.brain,
                },
            }
        except Exception as exc:
            JarvisLogger.exception("Command execution failed: %s", exc)
            return {"success": False, "message": str(exc), "data": {}}

    def _exec_skill(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Execute a specific skill by intent."""
        intent: str = payload.get("intent", "")
        text: str = payload.get("text", "")

        if not intent:
            return {"success": False, "message": "intent is required for skill execution", "data": {}}

        try:
            skill_manager = self._registry.get("skill_manager")
            skill = skill_manager.get(intent)

            request = _SkillRequest(
                text=text,
                intent=intent,
                entities=payload.get("entities", {}),
                normalized=payload.get("normalized", text),
                source=payload.get("source", "websocket"),
            )

            result = skill.execute(request)

            return {
                "success": result.success,
                "message": result.message,
                "data": {
                    "skill": result.skill,
                    "execution_time": result.execution_time,
                    "intent": intent,
                },
            }
        except Exception as exc:
            JarvisLogger.exception("Skill execution failed: %s", exc)
            return {"success": False, "message": str(exc), "data": {}}

    def _exec_ai_chat(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Execute an AI chat request."""
        prompt: str = payload.get("prompt", "")
        provider: str | None = payload.get("provider")
        conversation_id: str | None = payload.get("conversation_id")
        prompt_template: str | None = payload.get("prompt_template")
        template_variables: dict | None = payload.get("template_variables")

        if not prompt:
            return {"success": False, "message": "prompt is required for ai.chat", "data": {}}

        try:
            ai_manager = self._registry.get("ai_manager")
            response = ai_manager.ask(
                provider,
                prompt,
                conversation_id=conversation_id,
                prompt_template=prompt_template,
                template_variables=template_variables,
            )

            return {
                "success": True,
                "message": str(response),
                "data": {
                    "provider": response.provider,
                    "model": response.model,
                    "latency_ms": response.latency_ms,
                    "conversation_id": conversation_id,
                    "metadata": dict(response.metadata) if response.metadata else {},
                },
            }
        except Exception as exc:
            JarvisLogger.exception("AI chat failed: %s", exc)
            return {"success": False, "message": str(exc), "data": {}}

    def _exec_ai_plan(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Execute an AI planning request."""
        objective: str = payload.get("objective", "")
        provider: str | None = payload.get("provider")
        conversation_id: str | None = payload.get("conversation_id")
        prompt_template: str | None = payload.get("prompt_template")
        template_variables: dict | None = payload.get("template_variables")

        if not objective:
            return {"success": False, "message": "objective is required for ai.plan", "data": {}}

        try:
            ai_manager = self._registry.get("ai_manager")
            result = ai_manager.plan(
                objective,
                provider=provider,
                conversation_id=conversation_id,
                prompt_template=prompt_template,
                template_variables=template_variables,
            )

            return {
                "success": True,
                "message": str(result.plan),
                "data": {
                    "provider": result.provider,
                    "model": result.model,
                    "duration_ms": result.duration_ms,
                    "valid": result.valid,
                    "validation_errors": list(result.validation_errors),
                    "metadata": dict(result.metadata) if result.metadata else {},
                },
            }
        except Exception as exc:
            JarvisLogger.exception("AI plan failed: %s", exc)
            return {"success": False, "message": str(exc), "data": {}}

    def _exec_ai_reason(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Execute an AI reasoning request."""
        objective: str = payload.get("objective", "")
        provider: str | None = payload.get("provider")
        conversation_id: str | None = payload.get("conversation_id")
        prompt_template: str | None = payload.get("prompt_template")
        template_variables: dict | None = payload.get("template_variables")

        if not objective:
            return {"success": False, "message": "objective is required for ai.reason", "data": {}}

        try:
            ai_manager = self._registry.get("ai_manager")
            result = ai_manager.reason(
                objective,
                provider=provider,
                conversation_id=conversation_id,
                prompt_template=prompt_template,
                template_variables=template_variables,
            )

            return {
                "success": True,
                "message": str(result.chain),
                "data": {
                    "provider": result.provider,
                    "model": result.model,
                    "duration_ms": result.duration_ms,
                    "valid": result.valid,
                    "validation_errors": list(result.validation_errors),
                    "metadata": dict(result.metadata) if result.metadata else {},
                },
            }
        except Exception as exc:
            JarvisLogger.exception("AI reason failed: %s", exc)
            return {"success": False, "message": str(exc), "data": {}}

    # ------------------------------------------------------------------
    # WS message helpers
    # ------------------------------------------------------------------

    async def _send_progress(
        self,
        client_id: str,
        command_id: str,
        command_type: str,
        state: _CmdState,
        *,
        status: str,
        progress: int,
        message: str,
    ) -> None:
        if not await self._ws.is_connected(client_id):
            return
        elapsed = round((time.monotonic() - state.started_at) * 1000, 2) if state.started_at else 0
        await self._ws.send(
            client_id,
            ServerMessage(
                type=WSMessageType.COMMAND_PROGRESS,
                payload={
                    "command_id": command_id,
                    "type": command_type,
                    "status": status,
                    "progress": progress,
                    "message": message,
                    "execution_time_ms": elapsed,
                    "correlation_id": state.correlation_id,
                },
            ),
        )

    async def _send_result(
        self,
        client_id: str,
        command_id: str,
        command_type: str,
        state: _CmdState,
        *,
        success: bool,
        data: dict | None,
        message: str,
        elapsed: float,
    ) -> None:
        if not await self._ws.is_connected(client_id):
            return
        await self._ws.send(
            client_id,
            ServerMessage(
                type=WSMessageType.COMMAND_RESULT,
                payload={
                    "command_id": command_id,
                    "type": command_type,
                    "status": "completed" if success else "failed",
                    "success": success,
                    "message": message,
                    "data": data or {},
                    "execution_time_ms": elapsed,
                    "correlation_id": state.correlation_id,
                },
            ),
        )

    async def _send_error(
        self,
        client_id: str,
        command_id: str,
        command_type: str,
        state: _CmdState,
        *,
        error: str,
        elapsed: float = 0,
    ) -> None:
        if not await self._ws.is_connected(client_id):
            return
        await self._ws.send(
            client_id,
            ServerMessage(
                type=WSMessageType.COMMAND_ERROR,
                payload={
                    "command_id": command_id,
                    "type": command_type,
                    "status": "failed",
                    "error": error,
                    "execution_time_ms": elapsed,
                    "correlation_id": state.correlation_id,
                },
            ),
        )


def _result_msg(
    *,
    command_id: str,
    command_type: str,
    status: str,
    correlation_id: str = "",
    message: str = "",
    data: dict | None = None,
    elapsed: float = 0,
) -> ServerMessage:
    return ServerMessage(
        type=WSMessageType.COMMAND_RESULT,
        payload={
            "command_id": command_id,
            "type": command_type,
            "status": status,
            "message": message,
            "data": data or {},
            "execution_time_ms": elapsed,
            "correlation_id": correlation_id,
        },
    )


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------


@dataclass
class _CmdState:
    """Internal bookkeeping for an active remote command."""

    command_id: str
    client_id: str
    command_type: str
    payload: dict[str, Any]
    correlation_id: str = ""
    task: asyncio.Task | None = None
    started_at: float | None = None
    completed_at: float | None = None


class _SkillRequest:
    """Minimal duck-type request object for ``Skill.execute()``."""

    __slots__ = ("text", "intent", "entities", "normalized", "source")

    def __init__(
        self,
        text: str,
        intent: str,
        entities: dict,
        normalized: str,
        source: str,
    ) -> None:
        self.text = text
        self.intent = intent
        self.entities = entities
        self.normalized = normalized
        self.source = source
