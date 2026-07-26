from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.gui.controllers.chat_controller import ChatController, ChatResult


class TestChatController:
    @pytest.fixture
    def ai_handler(self):
        handler = MagicMock()
        from app.ai.providers.base import AIResponse
        handler.chat.return_value = AIResponse(
            "Hello! How can I help you?",
            provider="test",
            model="mock",
            latency_ms=10.0,
        )
        handler.chat_stream.return_value = MagicMock()
        handler.plan.return_value = AIResponse(
            "Plan: test\nObjective: test",
            provider="test",
            model="mock",
            latency_ms=20.0,
        )
        handler.reason.return_value = AIResponse(
            "Conclusion: test",
            provider="test",
            model="mock",
            latency_ms=15.0,
        )
        handler.load_history.return_value = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ]
        handler.create_conversation.return_value = MagicMock(
            conversation_id="conv_gui",
        )
        return handler

    @pytest.fixture
    def memory_handler(self):
        handler = MagicMock()
        return handler

    @pytest.fixture
    def ai_router(self):
        router = MagicMock()
        router.providers = {"deepseek": MagicMock(), "ollama": MagicMock()}
        return router

    @pytest.fixture
    def registry(self, ai_router):
        r = MagicMock()
        r.get.side_effect = lambda name: {
            "ai_router": ai_router,
        }[name]
        return r

    @pytest.fixture
    def controller(self, registry, ai_handler, memory_handler):
        with patch(
            "app.gui.controllers.chat_controller.AIHandler",
            return_value=ai_handler,
        ), patch(
            "app.gui.controllers.chat_controller.MemoryHandler",
            return_value=memory_handler,
        ):
            ctrl = ChatController(registry)
            ctrl._ai = ai_handler
            ctrl._memory = memory_handler
            return ctrl

    # ------------------------------------------------------------------
    # Provider selection
    # ------------------------------------------------------------------

    def test_resolve_provider_prefers_deepseek(self, registry):
        with patch(
            "app.gui.controllers.chat_controller.AIHandler",
        ), patch(
            "app.gui.controllers.chat_controller.MemoryHandler",
        ):
            ctrl = ChatController(registry)
            assert ctrl._provider == "deepseek"

    def test_resolve_provider_fallback_no_deepseek(self, ai_router):
        ai_router.providers = {"ollama": MagicMock()}
        r = MagicMock()
        r.get.side_effect = lambda name: {"ai_router": ai_router}[name]
        with patch(
            "app.gui.controllers.chat_controller.AIHandler",
        ), patch(
            "app.gui.controllers.chat_controller.MemoryHandler",
        ):
            ctrl = ChatController(r)
            assert ctrl._provider == "ollama"

    def test_resolve_provider_empty_router(self):
        ai_router = MagicMock()
        ai_router.providers = {}
        r = MagicMock()
        r.get.side_effect = lambda name: {"ai_router": ai_router}[name]
        with patch(
            "app.gui.controllers.chat_controller.AIHandler",
        ), patch(
            "app.gui.controllers.chat_controller.MemoryHandler",
        ):
            ctrl = ChatController(r)
            assert ctrl._provider == "deepseek"

    # ------------------------------------------------------------------
    # Conversation management
    # ------------------------------------------------------------------

    def test_new_conversation_resets_id(self, controller):
        controller._conversation_id = "old_conv"
        controller.new_conversation()
        assert controller._conversation_id is None

    def test_ensure_conversation_creates_on_demand(self, controller):
        conv_id = controller._ensure_conversation()
        assert conv_id == "conv_gui"
        assert controller._conversation_id == "conv_gui"

    def test_ensure_conversation_reuses_existing(self, controller):
        controller._conversation_id = "existing_conv"
        conv_id = controller._ensure_conversation()
        assert conv_id == "existing_conv"

    # ------------------------------------------------------------------
    # send_message
    # ------------------------------------------------------------------

    def test_send_message_returns_chat_result(self, controller):
        result = controller.send_message("hello")
        assert isinstance(result, ChatResult)

    def test_send_message_success(self, controller):
        result = controller.send_message("hello")
        assert result.success is True
        assert result.response == "Hello! How can I help you?"
        assert result.provider == "test"
        assert result.model == "mock"
        assert result.conversation_id == "conv_gui"
        assert result.latency_ms == 10.0

    def test_send_message_empty_text(self, controller):
        result = controller.send_message("")
        assert result.success is False
        assert "empty" in result.error.lower()

    def test_send_message_whitespace(self, controller):
        result = controller.send_message("   ")
        assert result.success is False

    def test_send_message_calls_ai_chat(self, controller):
        controller.send_message("hello")
        controller._ai.chat.assert_called_once()

    def test_send_message_passes_conversation_id(self, controller):
        controller.send_message("hello")
        _, kwargs = controller._ai.chat.call_args
        assert kwargs.get("conversation_id") == "conv_gui"

    def test_send_message_ai_error(self, controller):
        controller._ai.chat.side_effect = RuntimeError("AI failed")
        result = controller.send_message("hello")
        assert result.success is False
        assert "AI failed" in result.error

    # ------------------------------------------------------------------
    # send_message_stream
    # ------------------------------------------------------------------

    def test_send_message_stream_returns_stream(self, controller):
        stream = controller.send_message_stream("hello")
        assert stream is not None

    def test_send_message_stream_calls_chat_stream(self, controller):
        controller.send_message_stream("hello")
        controller._ai.chat_stream.assert_called_once()

    def test_send_message_stream_passes_conversation_id(self, controller):
        controller.send_message_stream("hello")
        _, kwargs = controller._ai.chat_stream.call_args
        assert kwargs.get("conversation_id") == "conv_gui"

    # ------------------------------------------------------------------
    # send_plan
    # ------------------------------------------------------------------

    def test_send_plan_returns_chat_result(self, controller):
        result = controller.send_plan("build a house")
        assert isinstance(result, ChatResult)

    def test_send_plan_success(self, controller):
        result = controller.send_plan("build a house")
        assert result.success is True
        assert "Plan:" in result.response
        assert result.response_type == "plan"
        assert result.provider == "test"

    def test_send_plan_empty(self, controller):
        result = controller.send_plan("")
        assert result.success is False
        assert "empty" in result.error.lower()

    def test_send_plan_calls_ai_plan(self, controller):
        controller.send_plan("build a house")
        controller._ai.plan.assert_called_once()

    def test_send_plan_error(self, controller):
        controller._ai.plan.side_effect = RuntimeError("plan fail")
        result = controller.send_plan("build a house")
        assert result.success is False
        assert "plan fail" in result.error

    # ------------------------------------------------------------------
    # send_reason
    # ------------------------------------------------------------------

    def test_send_reason_returns_chat_result(self, controller):
        result = controller.send_reason("why is the sky blue")
        assert isinstance(result, ChatResult)

    def test_send_reason_success(self, controller):
        result = controller.send_reason("why is the sky blue")
        assert result.success is True
        assert "Conclusion:" in result.response
        assert result.response_type == "reason"
        assert result.provider == "test"

    def test_send_reason_empty(self, controller):
        result = controller.send_reason("")
        assert result.success is False
        assert "empty" in result.error.lower()

    def test_send_reason_calls_ai_reason(self, controller):
        controller.send_reason("why is the sky blue")
        controller._ai.reason.assert_called_once()

    def test_send_reason_error(self, controller):
        controller._ai.reason.side_effect = RuntimeError("reason fail")
        result = controller.send_reason("why is the sky blue")
        assert result.success is False
        assert "reason fail" in result.error

    # ------------------------------------------------------------------
    # load_history
    # ------------------------------------------------------------------

    def test_load_history_returns_messages(self, controller):
        controller._conversation_id = "conv_gui"
        history = controller.load_history()
        assert isinstance(history, list)
        assert len(history) == 2
        assert history[0]["role"] == "user"

    def test_load_history_no_conversation(self, controller):
        controller.load_history()
        controller._ai.load_history.assert_called_once_with(
            conversation_id=None,
        )

    # ------------------------------------------------------------------
    # clear_conversation
    # ------------------------------------------------------------------

    def test_clear_conversation_resets_id(self, controller):
        controller._conversation_id = "old_conv"
        controller.clear_conversation()
        assert controller._conversation_id is None

    # ------------------------------------------------------------------
    # Metadata accessors
    # ------------------------------------------------------------------

    def test_get_provider_returns_provider(self, controller):
        assert controller.get_provider() == "deepseek"

    def test_get_conversation_id_returns_id(self, controller):
        controller._conversation_id = "conv_123"
        assert controller.get_conversation_id() == "conv_123"

    def test_get_conversation_id_none(self, controller):
        assert controller.get_conversation_id() is None

    # ------------------------------------------------------------------
    # EventBus integration
    # ------------------------------------------------------------------

    def test_subscribe_events_registers_transcript(self, controller):
        bus = MagicMock()
        controller.subscribe_events(bus)
        bus.subscribe.assert_called_once_with(
            "voice.transcript", controller._on_transcript,
        )

    def test_unsubscribe_events_removes_callback(self, controller):
        bus = MagicMock()
        controller.subscribe_events(bus)
        controller.unsubscribe_events()
        bus.unsubscribe.assert_called_once_with(
            "voice.transcript", controller._on_transcript,
        )
        assert controller._event_bus is None

    def test_unsubscribe_events_no_bus(self, controller):
        controller.unsubscribe_events()

    def test_on_transcript_calls_on_voice_input(self, controller):
        callback = MagicMock()
        controller.on_voice_input = callback
        controller._on_transcript("voice text")
        callback.assert_called_once_with("voice text")

    def test_on_transcript_no_callback(self, controller):
        controller.on_voice_input = None
        controller._on_transcript("voice text")
