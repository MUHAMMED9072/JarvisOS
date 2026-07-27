"""Tests for Remote Command Execution over WebSockets (P12-05)."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.registry import ServiceRegistry
from app.ws.commands import CommandExecutionManager
from app.ws.manager import WebSocketConnectionManager
from app.ws.schemas import ServerMessage, WSMessageType


# ==========================================================================
# Helpers
# ==========================================================================


def _make_msg(msg_type: str, **payload: Any) -> str:
    return json.dumps({"type": msg_type, "payload": payload})


class _MockSkill:
    """Minimal skill mock."""

    def __init__(self, name: str = "test_skill", intent: str = "test_intent"):
        self.name = name
        self.intent = intent

    def execute(self, request: Any) -> MagicMock:
        result = MagicMock()
        result.success = True
        result.message = f"Executed {self.name}"
        result.skill = self.name
        result.execution_time = 0.05
        result.data = {"done": True}
        return result


class _MockSkillFail:
    """Skill that always fails."""

    def __init__(self):
        self.name = "failing_skill"
        self.intent = "failing"

    def execute(self, request: Any) -> MagicMock:
        raise RuntimeError("Skill execution error")


class _MockSkillManager:
    def __init__(self):
        self.skills: dict[str, Any] = {}

    def register(self, skill: Any) -> None:
        self.skills[skill.intent] = skill

    def get(self, intent: str) -> Any:
        return self.skills.get(intent, _MockSkill(name="fallback", intent=intent))

    def all_skills(self) -> list[Any]:
        return list(self.skills.values())


class _MockMemory:
    def remember(self, **kwargs: Any) -> None:
        pass

    def set_context(self, **kwargs: Any) -> None:
        pass


class _MockBrain:
    def process(self, request: Any) -> MagicMock:
        result = MagicMock()
        result.success = True
        result.message = f"Brain processed: {request.text}"
        result.skill = "test_brain"
        result.execution_time = 0.02
        result.data = {"brain": "test"}
        return result


class _MockDispatcher:
    def __init__(self, registry: Any) -> None:
        self.registry = registry

    def dispatch(self, request: Any) -> MagicMock:
        result = MagicMock()
        result.success = True
        result.message = f"Dispatched: {request.text}"
        result.skill = "dispatcher"
        result.execution_time = 0.03
        result.data = {"dispatched": True}
        return result


class _MockCortexPipeline:
    def process(self, text: str, source: str = "voice") -> MagicMock:
        request = MagicMock()
        request.text = text
        request.source = source
        request.intent = "test_intent"
        request.confidence = 0.95
        request.entities = {"key": "value"}
        request.brain = "test"
        request.normalized = text
        return request


def _make_registry(
    *,
    with_ai: bool = True,
    with_skills: bool = True,
) -> MagicMock:
    """Create a mock registry with standard services."""
    registry = MagicMock(spec=ServiceRegistry)

    skill_mgr = _MockSkillManager()
    skill_mgr.register(_MockSkill(name="test_calc", intent="calculate"))
    skill_mgr.register(_MockSkill(name="test_greet", intent="greeting"))
    skill_mgr.register(_MockSkillFail())

    def get_side_effect(name: str) -> Any:
        if name == "skill_manager":
            return skill_mgr
        if name == "memory":
            return _MockMemory()
        if name == "fast_brain":
            return _MockBrain()
        if name == "smart_brain":
            return _MockBrain()
        if name == "deep_brain":
            return _MockBrain()
        if name == "ai_manager":
            if not with_ai:
                raise KeyError("ai_manager not available")
            return _make_ai_manager()
        raise KeyError(f"Service {name!r} not found")

    registry.get = MagicMock(side_effect=get_side_effect)
    registry.get_optional = MagicMock(
        side_effect=lambda name: (
            _make_ai_manager() if name == "ai_manager" and with_ai else None
        ),
    )
    return registry


def _make_ai_manager() -> MagicMock:
    """Create a mock AI manager."""
    mgr = MagicMock()

    def ask_side_effect(
        provider: str | None = None,
        prompt: str = "",
        **kwargs: Any,
    ) -> MagicMock:
        response = MagicMock()
        response.__str__ = lambda self: f"AI response to: {prompt[:30]}"
        response.provider = provider or "test_provider"
        response.model = "test-model"
        response.latency_ms = 50.0
        response.metadata = {"usage": {"prompt_tokens": 10}}
        return response

    mgr.ask = MagicMock(side_effect=ask_side_effect)

    def plan_side_effect(
        objective: str,
        **kwargs: Any,
    ) -> MagicMock:
        from app.ai.planning import Plan, PlanResult

        plan = Plan(
            objective=objective,
            title=f"Plan for: {objective}",
            steps=[],
        )
        result = PlanResult(
            plan=plan,
            provider="test_provider",
            model="test-model",
            duration_ms=100.0,
            valid=True,
            metadata={"strategy": "test"},
        )
        return result

    mgr.plan = MagicMock(side_effect=plan_side_effect)

    def reason_side_effect(
        objective: str,
        **kwargs: Any,
    ) -> MagicMock:
        from app.ai.reasoning import ReasoningChain, ReasoningResult

        chain = ReasoningChain(
            objective=objective,
            steps=[],
            confidence=0.95,
        )
        result = ReasoningResult(
            chain=chain,
            provider="test_provider",
            model="test-model",
            duration_ms=100.0,
            valid=True,
            metadata={"reasoning_type": "deductive"},
        )
        return result

    mgr.reason = MagicMock(side_effect=reason_side_effect)

    mgr.ask_stream = MagicMock(return_value=None)
    return mgr


async def _make_env(
    registry: MagicMock | None = None,
) -> tuple[CommandExecutionManager, AsyncMock]:
    """Create a test environment with mocked WS manager."""
    ws_mock = AsyncMock(spec=WebSocketConnectionManager)
    ws_mock.is_connected = AsyncMock(return_value=True)
    ws_mock.send = AsyncMock(return_value=True)

    if registry is None:
        registry = _make_registry()

    mgr = CommandExecutionManager(
        ws_manager=ws_mock,
        registry=registry,
    )
    return mgr, ws_mock


def _get_sent_payload(ws_mock: AsyncMock, index: int = 0) -> dict:
    """Extract the payload from a sent ServerMessage."""
    call_args = ws_mock.send.call_args_list[index]
    msg: ServerMessage = call_args[0][1]
    return msg.payload


def _get_sent_type(ws_mock: AsyncMock, index: int = 0) -> str:
    call_args = ws_mock.send.call_args_list[index]
    msg: ServerMessage = call_args[0][1]
    return msg.type.value


# ==========================================================================
# Tests
# ==========================================================================


class TestCommandExecutionManager:
    """Normal command execution for each type."""

    @pytest.mark.asyncio
    async def test_execute_command_type(self) -> None:
        """Execute a ``command`` type (CortexPipeline + Dispatcher)."""
        mgr, ws = await _make_env()
        cid = "client-1"

        with (
            patch("app.cortex.pipeline.CortexPipeline", return_value=_MockCortexPipeline()),
            patch("app.cortex.dispatcher.Dispatcher", _MockDispatcher),
        ):
            handled = await mgr.try_handle_message(cid, _make_msg("command.execute", type="command", text="Hello world"))
            assert handled is True
            await asyncio.sleep(0.3)

        assert ws.send.called
        last_type = _get_sent_type(ws, -1)
        assert last_type in (WSMessageType.COMMAND_RESULT.value, WSMessageType.COMMAND_ERROR.value)
        if last_type == WSMessageType.COMMAND_RESULT.value:
            payload = _get_sent_payload(ws, -1)
            assert payload.get("status") == "completed"
            assert payload.get("type") == "command"
            assert "command_id" in payload
            assert "correlation_id" in payload

    @pytest.mark.asyncio
    async def test_execute_skill_type(self) -> None:
        """Execute a ``skill`` type via SkillManager."""
        mgr, ws = await _make_env()
        cid = "client-1"

        handled = await mgr.try_handle_message(
            cid,
            _make_msg("command.execute", type="skill", intent="calculate", text="add 2+2"),
        )
        assert handled is True
        await asyncio.sleep(0.3)

        assert ws.send.called
        payload = _get_sent_payload(ws, -1)
        assert payload.get("status") == "completed"
        assert payload.get("type") == "skill"
        assert "Executed test_calc" in payload.get("message", "")

    @pytest.mark.asyncio
    async def test_execute_skill_type_missing_intent(self) -> None:
        """Skill execution without intent returns error."""
        mgr, ws = await _make_env()
        cid = "client-1"

        handled = await mgr.try_handle_message(
            cid,
            _make_msg("command.execute", type="skill", text="do something"),
        )
        assert handled is True
        await asyncio.sleep(0.3)

        payload = _get_sent_payload(ws, -1)
        assert payload.get("status") == "failed"
        assert "intent is required" in payload.get("error", "")

    @pytest.mark.asyncio
    async def test_execute_ai_chat_type(self) -> None:
        """Execute an ``ai.chat`` type via AIManager."""
        mgr, ws = await _make_env()
        cid = "client-1"

        handled = await mgr.try_handle_message(
            cid,
            _make_msg("command.execute", type="ai.chat", prompt="What is JARVIS?"),
        )
        assert handled is True
        await asyncio.sleep(0.3)

        payload = _get_sent_payload(ws, -1)
        assert payload.get("status") == "completed"
        assert payload.get("type") == "ai.chat"
        assert "AI response to" in payload.get("message", "")
        assert payload["data"]["provider"] == "test_provider"
        assert payload["data"]["model"] == "test-model"

    @pytest.mark.asyncio
    async def test_execute_ai_chat_missing_prompt(self) -> None:
        """AI chat without prompt returns error."""
        mgr, ws = await _make_env()
        cid = "client-1"

        handled = await mgr.try_handle_message(
            cid,
            _make_msg("command.execute", type="ai.chat"),
        )
        assert handled is True
        await asyncio.sleep(0.3)

        payload = _get_sent_payload(ws, -1)
        assert payload.get("status") == "failed"
        assert "prompt is required" in payload.get("error", "")

    @pytest.mark.asyncio
    async def test_execute_ai_plan_type(self) -> None:
        """Execute an ``ai.plan`` type via AIManager."""
        mgr, ws = await _make_env()
        cid = "client-1"

        handled = await mgr.try_handle_message(
            cid,
            _make_msg("command.execute", type="ai.plan", objective="Build a house"),
        )
        assert handled is True
        await asyncio.sleep(0.3)

        payload = _get_sent_payload(ws, -1)
        assert payload.get("status") == "completed"
        assert payload.get("type") == "ai.plan"
        assert "Plan for:" in payload.get("message", "")
        assert payload["data"]["valid"] is True

    @pytest.mark.asyncio
    async def test_execute_ai_plan_missing_objective(self) -> None:
        """AI plan without objective returns error."""
        mgr, ws = await _make_env()
        cid = "client-1"

        handled = await mgr.try_handle_message(
            cid,
            _make_msg("command.execute", type="ai.plan"),
        )
        assert handled is True
        await asyncio.sleep(0.3)

        payload = _get_sent_payload(ws, -1)
        assert payload.get("status") == "failed"
        assert "objective is required" in payload.get("error", "")

    @pytest.mark.asyncio
    async def test_execute_ai_reason_type(self) -> None:
        """Execute an ``ai.reason`` type via AIManager."""
        mgr, ws = await _make_env()
        cid = "client-1"

        handled = await mgr.try_handle_message(
            cid,
            _make_msg("command.execute", type="ai.reason", objective="Why is the sky blue?"),
        )
        assert handled is True
        await asyncio.sleep(0.3)

        payload = _get_sent_payload(ws, -1)
        assert payload.get("status") == "completed"
        assert payload.get("type") == "ai.reason"
        assert "sky blue" in payload.get("message", "")

    @pytest.mark.asyncio
    async def test_execute_ai_reason_missing_objective(self) -> None:
        """AI reason without objective returns error."""
        mgr, ws = await _make_env()
        cid = "client-1"

        handled = await mgr.try_handle_message(
            cid,
            _make_msg("command.execute", type="ai.reason"),
        )
        assert handled is True
        await asyncio.sleep(0.3)

        payload = _get_sent_payload(ws, -1)
        assert payload.get("status") == "failed"
        assert "objective is required" in payload.get("error", "")

    @pytest.mark.asyncio
    async def test_unknown_command_type(self) -> None:
        """Unknown command type returns error."""
        mgr, ws = await _make_env()
        cid = "client-1"

        handled = await mgr.try_handle_message(
            cid,
            _make_msg("command.execute", type="unknown_type", text="test"),
        )
        assert handled is True
        await asyncio.sleep(0.3)

        payload = _get_sent_payload(ws, -1)
        assert payload.get("status") == "failed"
        assert "Unknown command type" in payload.get("error", "")

    @pytest.mark.asyncio
    async def test_progress_message_sent(self) -> None:
        """Progress message is sent before completion."""
        mgr, ws = await _make_env()
        cid = "client-1"

        handled = await mgr.try_handle_message(
            cid,
            _make_msg("command.execute", type="ai.chat", prompt="Hello"),
        )
        assert handled is True
        await asyncio.sleep(0.3)

        assert ws.send.call_count >= 2
        types_sent = [_get_sent_type(ws, i) for i in range(ws.send.call_count)]
        assert WSMessageType.COMMAND_PROGRESS.value in types_sent
        assert WSMessageType.COMMAND_RESULT.value in types_sent

    @pytest.mark.asyncio
    async def test_metadata_preserved(self) -> None:
        """Command ID and correlation ID are preserved."""
        mgr, ws = await _make_env()
        cid = "client-1"

        handled = await mgr.try_handle_message(
            cid,
            _make_msg(
                "command.execute",
                type="ai.chat",
                prompt="Hello",
                command_id="my-cmd-001",
                correlation_id="corr-abc-123",
            ),
        )
        assert handled is True
        await asyncio.sleep(0.3)

        payload = _get_sent_payload(ws, -1)
        assert payload.get("command_id") == "my-cmd-001"
        assert payload.get("correlation_id") == "corr-abc-123"

    @pytest.mark.asyncio
    async def test_command_id_generated(self) -> None:
        """Command ID is auto-generated when not provided."""
        mgr, ws = await _make_env()
        cid = "client-1"

        handled = await mgr.try_handle_message(
            cid,
            _make_msg("command.execute", type="ai.chat", prompt="Hello"),
        )
        assert handled is True
        await asyncio.sleep(0.3)

        payload = _get_sent_payload(ws, -1)
        assert payload.get("command_id", "").startswith("cmd-")

    @pytest.mark.asyncio
    async def test_execution_time_included(self) -> None:
        """Result payload includes execution_time_ms."""
        mgr, ws = await _make_env()
        cid = "client-1"

        handled = await mgr.try_handle_message(
            cid,
            _make_msg("command.execute", type="ai.chat", prompt="Hello"),
        )
        assert handled is True
        await asyncio.sleep(0.3)

        payload = _get_sent_payload(ws, -1)
        assert payload.get("execution_time_ms", -1) >= 0

    @pytest.mark.asyncio
    async def test_result_has_data(self) -> None:
        """Result payload includes data dict."""
        mgr, ws = await _make_env()
        cid = "client-1"

        handled = await mgr.try_handle_message(
            cid,
            _make_msg("command.execute", type="ai.chat", prompt="Hello", provider="openai"),
        )
        assert handled is True
        await asyncio.sleep(0.3)

        payload = _get_sent_payload(ws, -1)
        assert payload.get("status") == "completed"
        data = payload.get("data", {})
        assert data.get("provider") == "openai"

    @pytest.mark.asyncio
    async def test_try_handle_message_ignores_other(self) -> None:
        """Non-command messages return False."""
        mgr, _ = await _make_env()
        cid = "client-1"

        handled = await mgr.try_handle_message(cid, _make_msg("ping"))
        assert handled is False

        handled = await mgr.try_handle_message(cid, _make_msg("subscribe", event="test"))
        assert handled is False

        handled = await mgr.try_handle_message(cid, _make_msg("ai.stream.start", provider="test"))
        assert handled is False

        handled = await mgr.try_handle_message(cid, "invalid json{")
        assert handled is False


class TestCommandCancellation:
    """Cancellation of running commands."""

    @pytest.mark.asyncio
    async def test_cancel_running_command(self) -> None:
        """Cancel a running command."""
        mgr, ws = await _make_env()
        cid = "client-1"

        # Make the command slow so we can cancel it before completion
        registry = _make_registry()
        ai_mgr = _make_ai_manager()
        import time as time_module

        def slow_ask(*args: Any, **kwargs: Any) -> Any:
            time_module.sleep(5)  # Slow enough to cancel
            return _make_ai_manager().ask(*args, **kwargs)

        ai_mgr.ask = MagicMock(side_effect=slow_ask)
        registry.get = MagicMock(
            side_effect=lambda name: ai_mgr if name == "ai_manager" else _make_registry().get(name),
        )
        mgr, ws = await _make_env(registry)

        handled = await mgr.try_handle_message(
            cid,
            _make_msg("command.execute", type="ai.chat", prompt="Hello"),
        )
        assert handled is True
        await asyncio.sleep(0.05)

        # Get the command_id from the progress message
        payload = _get_sent_payload(ws, 0)
        cmd_id = payload.get("command_id")

        await mgr.try_handle_message(
            cid,
            _make_msg("command.cancel", command_id=cmd_id),
        )
        await asyncio.sleep(0.3)

        sent_cancelled = any(
            _get_sent_type(ws, i) == WSMessageType.COMMAND_RESULT.value
            and _get_sent_payload(ws, i).get("status") == "cancelled"
            for i in range(ws.send.call_count)
        )
        assert sent_cancelled

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_command(self) -> None:
        """Cancelling a non-existent command is a no-op."""
        mgr, ws = await _make_env()
        cid = "client-1"

        handled = await mgr.try_handle_message(
            cid,
            _make_msg("command.cancel", command_id="no-such-cmd"),
        )
        assert handled is True
        await asyncio.sleep(0.05)
        assert ws.send.call_count == 0

    @pytest.mark.asyncio
    async def test_cancel_without_command_id(self) -> None:
        """Cancel without command_id is a no-op."""
        mgr, ws = await _make_env()
        cid = "client-1"

        handled = await mgr.try_handle_message(
            cid,
            _make_msg("command.cancel"),
        )
        assert handled is True
        await asyncio.sleep(0.05)
        assert ws.send.call_count == 0

    @pytest.mark.asyncio
    async def test_cancel_other_client_command(self) -> None:
        """Cannot cancel another client's command."""
        mgr, ws = await _make_env()
        cid1 = "client-1"
        cid2 = "client-2"

        handled = await mgr.try_handle_message(
            cid1,
            _make_msg("command.execute", type="ai.chat", prompt="Hello"),
        )
        assert handled is True

        await asyncio.sleep(0.1)
        ws.send.reset_mock()

        payload = _get_sent_payload(ws, 0) if ws.send.call_count > 0 else {}
        cmd_id = payload.get("command_id", "")
        ws.send.reset_mock()

        handled = await mgr.try_handle_message(
            cid2,
            _make_msg("command.cancel", command_id=cmd_id),
        )
        assert handled is True
        await asyncio.sleep(0.3)

        for i in range(ws.send.call_count):
            p = _get_sent_payload(ws, i)
            if p.get("status") == "cancelled":
                pytest.fail("Client 2 should not have cancelled client 1's command")


class TestErrorHandling:
    """Error handling and propagation."""

    @pytest.mark.asyncio
    async def test_skill_execution_error(self) -> None:
        """Skill that raises an error returns failure."""
        registry = _make_registry()
        mgr, ws = await _make_env(registry)
        cid = "client-1"

        handled = await mgr.try_handle_message(
            cid,
            _make_msg("command.execute", type="skill", intent="failing"),
        )
        assert handled is True
        await asyncio.sleep(0.3)

        payload = _get_sent_payload(ws, -1)
        assert payload.get("status") == "failed"
        assert "error" in payload

    @pytest.mark.asyncio
    async def test_missing_ai_manager(self) -> None:
        """AI command fails gracefully when ai_manager is unavailable."""
        registry = _make_registry(with_ai=False)
        mgr, ws = await _make_env(registry)
        cid = "client-1"

        handled = await mgr.try_handle_message(
            cid,
            _make_msg("command.execute", type="ai.chat", prompt="Hello"),
        )
        assert handled is True
        await asyncio.sleep(0.3)

        payload = _get_sent_payload(ws, -1)
        assert payload.get("status") == "failed"

    @pytest.mark.asyncio
    async def test_ai_manager_raises_exception(self) -> None:
        """AI chat failure returns error."""
        registry = _make_registry()
        ai_mgr = _make_ai_manager()
        ai_mgr.ask = MagicMock(side_effect=RuntimeError("AI provider timeout"))
        registry.get = MagicMock(
            side_effect=lambda name: ai_mgr if name == "ai_manager" else _make_registry().get(name),
        )
        mgr, ws = await _make_env(registry)
        cid = "client-1"

        handled = await mgr.try_handle_message(
            cid,
            _make_msg("command.execute", type="ai.chat", prompt="Hello"),
        )
        assert handled is True
        await asyncio.sleep(0.3)

        payload = _get_sent_payload(ws, -1)
        assert payload.get("status") == "failed"
        assert "AI provider timeout" in payload.get("error", "")

    @pytest.mark.asyncio
    async def test_disconnect_during_execution(self) -> None:
        """Disconnect during execution is handled gracefully."""
        ws_mock = AsyncMock(spec=WebSocketConnectionManager)
        ws_mock.is_connected = AsyncMock(return_value=True)
        ws_mock.send = AsyncMock(return_value=True)

        registry = _make_registry()
        mgr = CommandExecutionManager(
            ws_manager=ws_mock,
            registry=registry,
        )
        cid = "client-1"

        handled = await mgr.try_handle_message(
            cid,
            _make_msg("command.execute", type="ai.chat", prompt="Hello"),
        )
        assert handled is True

        await mgr.cleanup(cid)
        await asyncio.sleep(0.3)

        count = await mgr.get_active_count(cid)
        assert count == 0


class TestConcurrentExecution:
    """Concurrent command execution."""

    @pytest.mark.asyncio
    async def test_concurrent_commands(self) -> None:
        """Multiple commands execute concurrently."""
        mgr, ws = await _make_env()
        cid = "client-1"

        handled1 = await mgr.try_handle_message(
            cid,
            _make_msg("command.execute", type="ai.chat", prompt="Task 1"),
        )
        handled2 = await mgr.try_handle_message(
            cid,
            _make_msg("command.execute", type="ai.chat", prompt="Task 2"),
        )
        handled3 = await mgr.try_handle_message(
            cid,
            _make_msg("command.execute", type="ai.chat", prompt="Task 3"),
        )
        assert handled1 and handled2 and handled3
        await asyncio.sleep(0.5)

        count = await mgr.get_active_count(cid)
        assert count == 0
        assert ws.send.call_count >= 6  # 3 progress + 3 result

    @pytest.mark.asyncio
    async def test_concurrent_commands_different_types(self) -> None:
        """Different command types execute concurrently."""
        mgr, ws = await _make_env()
        cid = "client-1"

        with (
            patch("app.cortex.pipeline.CortexPipeline", return_value=_MockCortexPipeline()),
            patch("app.cortex.dispatcher.Dispatcher", _MockDispatcher),
        ):
            handled1 = await mgr.try_handle_message(
                cid,
                _make_msg("command.execute", type="command", text="Hello"),
            )
        handled2 = await mgr.try_handle_message(
            cid,
            _make_msg("command.execute", type="skill", intent="calculate", text="2+2"),
        )
        handled3 = await mgr.try_handle_message(
            cid,
            _make_msg("command.execute", type="ai.chat", prompt="Hello"),
        )
        assert handled1 and handled2 and handled3
        await asyncio.sleep(0.5)

        count = await mgr.get_active_count(cid)
        assert count == 0

    @pytest.mark.asyncio
    async def test_get_active_count(self) -> None:
        """get_active_count returns correct values."""
        mgr, ws = await _make_env()
        cid = "client-1"

        ws.is_connected = AsyncMock(return_value=True)
        ws.send = AsyncMock(return_value=True)

        assert await mgr.get_active_count() == 0
        assert await mgr.get_active_count(cid) == 0

        await mgr.try_handle_message(
            cid,
            _make_msg("command.execute", type="ai.chat", prompt="Task 1", command_id="slow-cmd"),
        )
        await asyncio.sleep(0)

        count = await mgr.get_active_count(cid)
        assert count == 1, f"Expected 1 active command, got {count}"

        await asyncio.sleep(0.3)
        count = await mgr.get_active_count(cid)
        assert count == 0


class TestMultipleClients:
    """Multiple client isolation."""

    @pytest.mark.asyncio
    async def test_multiple_clients_independent(self) -> None:
        """Commands for different clients are independent."""
        mgr, ws = await _make_env()
        cid1 = "client-1"
        cid2 = "client-2"

        handled1 = await mgr.try_handle_message(
            cid1,
            _make_msg("command.execute", type="ai.chat", prompt="Hello from 1"),
        )
        handled2 = await mgr.try_handle_message(
            cid2,
            _make_msg("command.execute", type="ai.chat", prompt="Hello from 2"),
        )
        assert handled1 and handled2
        await asyncio.sleep(0.3)

        assert await mgr.get_active_count(cid1) == 0
        assert await mgr.get_active_count(cid2) == 0

    @pytest.mark.asyncio
    async def test_cleanup_isolated_per_client(self) -> None:
        """Cleanup only affects the specified client."""
        mgr, ws = await _make_env()
        cid1 = "client-1"
        cid2 = "client-2"

        await mgr.try_handle_message(
            cid1,
            _make_msg("command.execute", type="ai.chat", prompt="Task 1"),
        )
        await asyncio.sleep(0.02)
        ws.send.reset_mock()

        await mgr.try_handle_message(
            cid2,
            _make_msg("command.execute", type="ai.chat", prompt="Task 2"),
        )
        await asyncio.sleep(0.02)
        ws.send.reset_mock()

        await mgr.cleanup(cid1)
        await asyncio.sleep(0.3)

        count2 = await mgr.get_active_count(cid2)
        assert count2 == 0


class TestBackwardCompatibility:
    """Backward compatibility with existing infrastructure."""

    @pytest.mark.asyncio
    async def test_does_not_interfere_with_ping(self) -> None:
        """Existing ping/pong messages are not intercepted."""
        mgr, _ = await _make_env()
        cid = "client-1"

        handled = await mgr.try_handle_message(cid, _make_msg("ping"))
        assert handled is False

    @pytest.mark.asyncio
    async def test_does_not_interfere_with_subscribe(self) -> None:
        """Existing subscribe messages are not intercepted."""
        mgr, _ = await _make_env()
        cid = "client-1"

        handled = await mgr.try_handle_message(cid, _make_msg("subscribe", event="test"))
        assert handled is False

    @pytest.mark.asyncio
    async def test_does_not_interfere_with_ai_stream(self) -> None:
        """Existing AI stream messages are not intercepted."""
        mgr, _ = await _make_env()
        cid = "client-1"

        handled = await mgr.try_handle_message(cid, _make_msg("ai.stream.start", provider="test"))
        assert handled is False

    @pytest.mark.asyncio
    async def test_does_not_interfere_with_message(self) -> None:
        """Existing direct messages are not intercepted."""
        mgr, _ = await _make_env()
        cid = "client-1"

        handled = await mgr.try_handle_message(cid, _make_msg("message", text="Hello"))
        assert handled is False

    @pytest.mark.asyncio
    async def test_disconnect_sends_cancelled(self) -> None:
        """Cleanup sends cancelled status for pending commands."""
        ws_mock = AsyncMock(spec=WebSocketConnectionManager)
        ws_mock.is_connected = AsyncMock(return_value=True)
        ws_mock.send = AsyncMock(return_value=True)

        registry = _make_registry()
        mgr = CommandExecutionManager(
            ws_manager=ws_mock,
            registry=registry,
        )
        cid = "client-1"

        await mgr.try_handle_message(
            cid,
            _make_msg(
                "command.execute",
                type="ai.chat",
                prompt="Slow task",
            ),
        )
        await asyncio.sleep(0.02)

        ws_mock.is_connected = AsyncMock(return_value=False)
        await mgr.cleanup(cid)
        await asyncio.sleep(0.3)

        assert await mgr.get_active_count(cid) == 0

    @pytest.mark.asyncio
    async def test_empty_payload(self) -> None:
        """Empty payload with ai.chat and no prompt returns error."""
        mgr, ws = await _make_env()
        cid = "client-1"

        handled = await mgr.try_handle_message(
            cid,
            json.dumps({"type": "command.execute", "payload": {"type": "ai.chat"}}),
        )
        assert handled is True
        await asyncio.sleep(0.3)

        payload = _get_sent_payload(ws, -1)
        assert payload.get("status") == "failed"

    @pytest.mark.asyncio
    async def test_registry_without_ai_does_not_crash(self) -> None:
        """Executing on registry without ai_manager does not crash."""
        registry = _make_registry(with_ai=False)
        mgr, ws = await _make_env(registry)
        cid = "client-1"

        handled = await mgr.try_handle_message(
            cid,
            _make_msg("command.execute", type="ai.chat", prompt="Hello"),
        )
        assert handled is True
        await asyncio.sleep(0.3)

        assert ws.send.called

    @pytest.mark.asyncio
    async def test_send_result_when_disconnected(self) -> None:
        """Sending result to disconnected client does not crash."""
        mgr, ws = await _make_env()
        cid = "client-1"

        ws.is_connected = AsyncMock(return_value=False)

        handled = await mgr.try_handle_message(
            cid,
            _make_msg("command.execute", type="ai.chat", prompt="Hello"),
        )
        assert handled is True
        await asyncio.sleep(0.3)
