from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.gui.controllers.chat_controller import ChatController
from app.skills.result import SkillResult


class TestChatController:
    @pytest.fixture
    def ai_handler(self):
        handler = MagicMock()
        handler.chat.return_value = "Hello! How can I help you?"
        return handler

    @pytest.fixture
    def memory_handler(self):
        handler = MagicMock()
        handler.get_session_context.return_value = {
            "messages": [
                {"role": "user", "content": "hi"},
                {"role": "assistant", "content": "hello"},
            ]
        }
        return handler

    @pytest.fixture
    def memory_manager(self):
        return MagicMock()

    @pytest.fixture
    def ai_router(self):
        router = MagicMock()
        router.providers = {"ollama": MagicMock(), "deepseek": MagicMock()}
        return router

    @pytest.fixture
    def registry(self, ai_router, memory_manager):
        r = MagicMock()
        r.get.side_effect = lambda name: {
            "ai_router": ai_router,
            "memory": memory_manager,
        }[name]
        return r

    @pytest.fixture
    def controller(self, registry):
        with patch(
            "app.gui.controllers.chat_controller.AIHandler",
        ) as mock_ai_cls, patch(
            "app.gui.controllers.chat_controller.MemoryHandler",
        ) as mock_mem_cls:
            mock_ai_cls.return_value = MagicMock()
            mock_ai_cls.return_value.chat.return_value = "Test response"
            mock_mem_cls.return_value = MagicMock()
            mock_mem_cls.return_value.get_session_context.return_value = {
                "messages": [
                    {"role": "user", "content": "hi"},
                    {"role": "assistant", "content": "hello"},
                ]
            }
            ctrl = ChatController(registry)
            ctrl._ai = mock_ai_cls.return_value
            ctrl._memory = mock_mem_cls.return_value
            return ctrl

    # ------------------------------------------------------------------
    # Provider selection
    # ------------------------------------------------------------------

    def test_resolve_provider_prefers_ollama(self, registry):
        with patch(
            "app.gui.controllers.chat_controller.AIHandler",
        ), patch(
            "app.gui.controllers.chat_controller.MemoryHandler",
        ):
            ctrl = ChatController(registry)
            assert ctrl._provider == "ollama"

    def test_resolve_provider_fallback_no_ollama(self, ai_router, memory_manager):
        ai_router.providers = {"deepseek": MagicMock()}
        r = MagicMock()
        r.get.side_effect = lambda name: {
            "ai_router": ai_router,
            "memory": memory_manager,
        }[name]
        with patch(
            "app.gui.controllers.chat_controller.AIHandler",
        ), patch(
            "app.gui.controllers.chat_controller.MemoryHandler",
        ):
            ctrl = ChatController(r)
            assert ctrl._provider == "deepseek"

    def test_resolve_provider_empty_router(self, memory_manager):
        ai_router = MagicMock()
        ai_router.providers = {}
        r = MagicMock()
        r.get.side_effect = lambda name: {
            "ai_router": ai_router,
            "memory": memory_manager,
        }[name]
        with patch(
            "app.gui.controllers.chat_controller.AIHandler",
        ), patch(
            "app.gui.controllers.chat_controller.MemoryHandler",
        ):
            ctrl = ChatController(r)
            assert ctrl._provider == "ollama"

    # ------------------------------------------------------------------
    # send_message
    # ------------------------------------------------------------------

    def test_send_message_returns_skill_result(self, controller):
        result = controller.send_message("hello")
        assert isinstance(result, SkillResult)

    def test_send_message_success(self, controller):
        result = controller.send_message("hello")
        assert result.success is True
        assert result.message == "Test response"

    def test_send_message_empty_text(self, controller):
        result = controller.send_message("")
        assert result.success is False
        assert "empty" in result.message.lower()

    def test_send_message_whitespace(self, controller):
        result = controller.send_message("   ")
        assert result.success is False

    def test_send_message_calls_ai_chat(self, controller):
        controller.send_message("hello")
        controller._ai.chat.assert_called_once()

    def test_send_message_passes_provider(self, controller):
        controller.send_message("hello", provider="ollama")
        _, kwargs = controller._ai.chat.call_args
        assert "provider" in kwargs

    def test_send_message_includes_context(self, controller):
        controller.send_message("hello")
        args, _ = controller._ai.chat.call_args
        prompt = args[0]
        assert "Previous conversation" in prompt
        assert "User: hello" in prompt

    def test_send_message_ai_error(self, controller):
        controller._ai.chat.side_effect = RuntimeError("AI failed")
        result = controller.send_message("hello")
        assert result.success is False
        assert "AI failed" in result.message

    # ------------------------------------------------------------------
    # load_history
    # ------------------------------------------------------------------

    def test_load_history_returns_messages(self, controller):
        history = controller.load_history()
        assert isinstance(history, list)
        assert len(history) == 2
        assert history[0]["role"] == "user"

    def test_load_history_empty(self, controller):
        controller._memory.get_session_context.return_value = {"messages": []}
        history = controller.load_history()
        assert history == []

    # ------------------------------------------------------------------
    # clear_conversation
    # ------------------------------------------------------------------

    def test_clear_conversation_calls_memory_clear(self, controller):
        controller.clear_conversation()
        controller.registry.get("memory").clear.assert_called_once()

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
