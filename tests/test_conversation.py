from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.ai.conversation import Conversation, ConversationManager, ConversationMessage
from app.ai.manager import AIManager
from app.ai.providers.base import AIResponse, AIStreamChunk, AIStreamResponse
from app.ai.router import AIRouter


# ---------------------------------------------------------------------------
# ConversationMessage
# ---------------------------------------------------------------------------


class TestConversationMessage:

    def test_defaults(self) -> None:
        msg = ConversationMessage()
        assert msg.role == "user"
        assert msg.content == ""
        assert msg.metadata == {}

    def test_custom(self) -> None:
        msg = ConversationMessage(role="assistant", content="Hello", metadata={"t": 1})
        assert msg.role == "assistant"
        assert msg.content == "Hello"
        assert msg.metadata == {"t": 1}

    def test_timestamp_is_float(self) -> None:
        msg = ConversationMessage()
        assert isinstance(msg.timestamp, float)

    def test_all_roles(self) -> None:
        for role in ("system", "user", "assistant", "tool"):
            msg = ConversationMessage(role=role, content="test")
            assert msg.role == role


# ---------------------------------------------------------------------------
# Conversation
# ---------------------------------------------------------------------------


class TestConversation:

    def test_defaults(self) -> None:
        conv = Conversation()
        assert conv.conversation_id is not None
        assert len(conv.conversation_id) == 12
        assert conv.messages == []
        assert conv.max_messages == 50

    def test_provider_and_model(self) -> None:
        conv = Conversation(provider="openai", model="gpt-4")
        assert conv.provider == "openai"
        assert conv.model == "gpt-4"

    def test_timestamps(self) -> None:
        conv = Conversation()
        assert isinstance(conv.created_at, float)
        assert isinstance(conv.updated_at, float)
        assert conv.created_at > 0

    def test_system_prompt(self) -> None:
        conv = Conversation(system_prompt="You are helpful.")
        assert conv.system_prompt == "You are helpful."


# ---------------------------------------------------------------------------
# ConversationManager
# ---------------------------------------------------------------------------


class TestConversationManager:

    def test_create_returns_conversation(self) -> None:
        mgr = ConversationManager()
        conv = mgr.create(provider="openai")
        assert isinstance(conv, Conversation)
        assert conv.provider == "openai"

    def test_create_increments_active_count(self) -> None:
        mgr = ConversationManager()
        assert mgr.active_count == 0
        mgr.create()
        assert mgr.active_count == 1
        mgr.create()
        assert mgr.active_count == 2

    def test_get_returns_conversation(self) -> None:
        mgr = ConversationManager()
        conv = mgr.create()
        retrieved = mgr.get(conv.conversation_id)
        assert retrieved is conv

    def test_get_returns_none_for_unknown(self) -> None:
        mgr = ConversationManager()
        assert mgr.get("nonexistent") is None

    def test_get_or_create_existing(self) -> None:
        mgr = ConversationManager()
        conv = mgr.create(provider="openai")
        same = mgr.get_or_create(conv.conversation_id)
        assert same is conv
        assert mgr.active_count == 1

    def test_get_or_create_new(self) -> None:
        mgr = ConversationManager()
        conv = mgr.get_or_create("new-id", provider="gemini")
        assert conv.conversation_id == "new-id"
        assert conv.provider == "gemini"
        assert mgr.active_count == 1

    def test_delete_existing(self) -> None:
        mgr = ConversationManager()
        conv = mgr.create()
        assert mgr.delete(conv.conversation_id) is True
        assert mgr.get(conv.conversation_id) is None
        assert mgr.active_count == 0

    def test_delete_nonexistent(self) -> None:
        mgr = ConversationManager()
        assert mgr.delete("nonexistent") is False

    def test_clear_messages(self) -> None:
        mgr = ConversationManager()
        conv = mgr.create()
        mgr.add_message(conv.conversation_id, "user", "hello")
        mgr.add_message(conv.conversation_id, "assistant", "hi")
        assert len(conv.messages) == 2
        mgr.clear(conv.conversation_id)
        assert len(conv.messages) == 0

    def test_clear_nonexistent(self) -> None:
        mgr = ConversationManager()
        assert mgr.clear("nonexistent") is False

    def test_add_message(self) -> None:
        mgr = ConversationManager()
        conv = mgr.create()
        msg = mgr.add_message(conv.conversation_id, "user", "Hello!")
        assert msg is not None
        assert msg.role == "user"
        assert msg.content == "Hello!"
        assert len(conv.messages) == 1

    def test_add_message_nonexistent(self) -> None:
        mgr = ConversationManager()
        assert mgr.add_message("nonexistent", "user", "test") is None

    def test_list_messages(self) -> None:
        mgr = ConversationManager()
        conv = mgr.create()
        mgr.add_message(conv.conversation_id, "user", "a")
        mgr.add_message(conv.conversation_id, "assistant", "b")
        msgs = mgr.list_messages(conv.conversation_id)
        assert len(msgs) == 2
        assert msgs[0].content == "a"
        assert msgs[1].content == "b"

    def test_list_messages_nonexistent(self) -> None:
        mgr = ConversationManager()
        assert mgr.list_messages("nonexistent") == ()

    def test_set_metadata(self) -> None:
        mgr = ConversationManager()
        conv = mgr.create()
        assert mgr.set_metadata(conv.conversation_id, "key", "val") is True
        assert conv.metadata["key"] == "val"

    def test_set_metadata_nonexistent(self) -> None:
        mgr = ConversationManager()
        assert mgr.set_metadata("nonexistent", "k", "v") is False

    def test_active_count_after_delete(self) -> None:
        mgr = ConversationManager()
        c1 = mgr.create()
        c2 = mgr.create()
        assert mgr.active_count == 2
        mgr.delete(c1.conversation_id)
        assert mgr.active_count == 1

    def test_update_timestamp(self) -> None:
        mgr = ConversationManager()
        conv = mgr.create()
        old = conv.updated_at
        assert mgr.update_timestamp(conv.conversation_id) is True
        assert conv.updated_at >= old

    def test_update_timestamp_nonexistent(self) -> None:
        mgr = ConversationManager()
        assert mgr.update_timestamp("nonexistent") is False


# ---------------------------------------------------------------------------
# Context trimming
# ---------------------------------------------------------------------------


class TestContextTrimming:

    def test_no_trim_when_under_limit(self) -> None:
        mgr = ConversationManager()
        conv = mgr.create(max_messages=5)
        for i in range(4):
            mgr.add_message(conv.conversation_id, "user", f"msg{i}")
        assert len(conv.messages) == 4

    def test_trims_when_over_limit(self) -> None:
        mgr = ConversationManager()
        conv = mgr.create(max_messages=3)
        for i in range(5):
            mgr.add_message(conv.conversation_id, "user", f"msg{i}")
        assert len(conv.messages) == 3
        assert conv.messages[-1].content == "msg4"
        assert conv.messages[0].content == "msg2"

    def test_preserves_system_prompts_during_trim(self) -> None:
        mgr = ConversationManager()
        conv = mgr.create(max_messages=4)
        mgr.add_message(conv.conversation_id, "system", "You are helpful.")
        for i in range(5):
            mgr.add_message(conv.conversation_id, "user", f"msg{i}")
        # system message preserved, plus 3 most recent = 4 total
        assert len(conv.messages) == 4
        assert conv.messages[0].role == "system"
        assert conv.messages[0].content == "You are helpful."

    def test_preserves_multiple_system_prompts(self) -> None:
        mgr = ConversationManager()
        conv = mgr.create(max_messages=3)
        mgr.add_message(conv.conversation_id, "system", "rule1")
        mgr.add_message(conv.conversation_id, "system", "rule2")
        for i in range(4):
            mgr.add_message(conv.conversation_id, "user", f"msg{i}")
        # Both system messages preserved, keep 1 user msg = 3 total
        assert len(conv.messages) == 3
        roles = [m.role for m in conv.messages]
        assert roles.count("system") == 2
        assert conv.messages[-1].content == "msg3"

    def test_no_trim_when_exactly_at_limit(self) -> None:
        mgr = ConversationManager()
        conv = mgr.create(max_messages=3)
        for i in range(3):
            mgr.add_message(conv.conversation_id, "user", f"msg{i}")
        assert len(conv.messages) == 3


# ---------------------------------------------------------------------------
# format_messages on providers
# ---------------------------------------------------------------------------


class TestFormatMessages:

    def test_default_format(self) -> None:
        from app.ai.providers.base import _ProviderBase
        p = _ProviderBase()
        msgs = [
            ConversationMessage(role="system", content="You are helpful."),
            ConversationMessage(role="user", content="Hello"),
            ConversationMessage(role="assistant", content="Hi!"),
        ]
        result = p.format_messages(msgs)
        assert len(result) == 3
        assert result[0] == {"role": "system", "content": "You are helpful."}
        assert result[1] == {"role": "user", "content": "Hello"}
        assert result[2] == {"role": "assistant", "content": "Hi!"}

    def test_default_format_with_metadata(self) -> None:
        from app.ai.providers.base import _ProviderBase
        p = _ProviderBase()
        msgs = [
            ConversationMessage(
                role="user", content="test", metadata={"t": 1},
            ),
        ]
        result = p.format_messages(msgs)
        assert result[0]["metadata"] == {"t": 1}

    def test_openai_format(self) -> None:
        from app.ai.providers.openai import OpenAIProvider
        p = OpenAIProvider(api_key="sk-test")
        msgs = [
            ConversationMessage(role="user", content="Hello"),
        ]
        result = p.format_messages(msgs)
        assert result == [{"role": "user", "content": "Hello"}]

    def test_anthropic_format(self) -> None:
        from app.ai.providers.claude import AnthropicProvider
        p = AnthropicProvider(api_key="sk-test")
        msgs = [
            ConversationMessage(role="user", content="Hello"),
        ]
        result = p.format_messages(msgs)
        # Anthropic uses the same dict format for messages
        assert result == [{"role": "user", "content": "Hello"}]

    def test_gemini_format(self) -> None:
        from app.ai.providers.gemini import GeminiProvider
        p = GeminiProvider(api_key="sk-test")
        msgs = [
            ConversationMessage(role="user", content="Hello"),
        ]
        result = p.format_messages(msgs)
        assert result == [{"role": "user", "content": "Hello"}]


# ---------------------------------------------------------------------------
# AIManager conversation integration
# ---------------------------------------------------------------------------


class TestAIManagerConversation:

    def _make_manager(self) -> tuple[AIManager, MagicMock]:
        mock_provider = MagicMock()
        mock_provider.generate.return_value = AIResponse(
            "assistant reply",
            provider="test",
            model="test-model",
            latency_ms=10.0,
        )
        mock_provider.provider_name = "test"
        mock_provider._model = "test-model"
        mock_provider.check_availability.return_value = True

        manager = AIManager()
        manager.router.providers = {"test": mock_provider}
        return manager, mock_provider

    def test_ask_without_conversation(self) -> None:
        mock_provider = MagicMock()
        mock_provider.generate.return_value = AIResponse(
            "reply", provider="test", model="m", latency_ms=5.0,
        )
        mock_provider.provider_name = "test"

        manager = AIManager()
        manager.router.providers = {"test": mock_provider}

        result = manager.ask("test", "hello")
        assert result == "reply"
        mock_provider.generate.assert_called_once()

    def test_ask_with_conversation(self) -> None:
        manager, mock_provider = self._make_manager()
        conv = manager.create_conversation(provider="test")

        result = manager.ask("test", "hello", conversation_id=conv.conversation_id)
        assert result == "assistant reply"
        assert len(conv.messages) == 2
        assert conv.messages[0].role == "user"
        assert conv.messages[0].content == "hello"
        assert conv.messages[1].role == "assistant"
        assert conv.messages[1].content == "assistant reply"
        assert conv.messages[1].metadata["provider"] == "test"

    def test_ask_with_conversation_appends_history(self) -> None:
        manager, mock_provider = self._make_manager()
        conv = manager.create_conversation(provider="test")

        result1 = manager.ask("test", "first", conversation_id=conv.conversation_id)
        result2 = manager.ask("test", "second", conversation_id=conv.conversation_id)

        assert len(conv.messages) == 4
        assert conv.messages[0].content == "first"
        assert conv.messages[1].content == "assistant reply"
        assert conv.messages[2].content == "second"
        assert conv.messages[3].content == "assistant reply"

    def test_ask_with_unknown_conversation_raises(self) -> None:
        manager = AIManager()
        with pytest.raises(ValueError, match="not found"):
            manager.ask("test", "hello", conversation_id="bad-id")

    def test_create_conversation_sets_provider_and_model(self) -> None:
        manager = AIManager()
        conv = manager.create_conversation(
            provider="openai", model="gpt-4", system_prompt="Be brief.",
        )
        assert conv.provider == "openai"
        assert conv.model == "gpt-4"
        assert conv.system_prompt == "Be brief."

    def test_conversation_metadata_preserved(self) -> None:
        manager, mock_provider = self._make_manager()
        conv = manager.create_conversation(
            provider="test",
            metadata={"session": "abc"},
        )
        assert conv.metadata["session"] == "abc"


class TestAIManagerConversationStreaming:

    def _make_manager_with_stream(
        self,
    ) -> tuple[AIManager, MagicMock]:
        def _gen() -> Generator[AIStreamChunk, None, None]:
            yield AIStreamChunk(content="hello ")
            yield AIStreamChunk(content="world")

        mock_provider = MagicMock()
        mock_provider.generate_stream.return_value = _gen()
        mock_provider._model = "test-model"
        mock_provider.provider_name = "test"
        mock_provider.check_availability.return_value = True

        manager = AIManager()
        manager.router.providers = {"test": mock_provider}
        # Disable auto-discovery for the router
        return manager, mock_provider

    def test_ask_stream_with_conversation(self) -> None:
        manager, mock_provider = self._make_manager_with_stream()
        conv = manager.create_conversation(provider="test")

        stream = manager.ask_stream(
            "test", "hi", conversation_id=conv.conversation_id,
        )
        chunks = [c.content for c in stream]
        assert chunks == ["hello ", "world"]

        # Assistant message appended after successful completion
        assert len(conv.messages) == 2
        assert conv.messages[0].role == "user"
        assert conv.messages[0].content == "hi"
        assert conv.messages[1].role == "assistant"
        assert conv.messages[1].content == "hello world"

    def test_ask_stream_without_conversation(self) -> None:
        """Non-conversation streaming still works unchanged."""
        manager, mock_provider = self._make_manager_with_stream()

        stream = manager.ask_stream("test", "hi")
        chunks = [c.content for c in stream]
        assert chunks == ["hello ", "world"]

    def test_ask_stream_unknown_conversation_raises(self) -> None:
        manager = AIManager()
        with pytest.raises(ValueError, match="not found"):
            manager.ask_stream("test", "hi", conversation_id="bad-id")


# ---------------------------------------------------------------------------
# _build_prompt_from_conversation
# ---------------------------------------------------------------------------


class TestBuildPrompt:

    def test_build_empty(self) -> None:
        conv = Conversation()
        prompt = AIManager._build_prompt_from_conversation(conv)
        assert prompt == ""

    def test_build_with_system_prompt(self) -> None:
        conv = Conversation(system_prompt="You are helpful.")
        prompt = AIManager._build_prompt_from_conversation(conv)
        assert "system: You are helpful." in prompt

    def test_build_with_messages(self) -> None:
        conv = Conversation()
        conv.messages = [
            ConversationMessage(role="user", content="Hello"),
            ConversationMessage(role="assistant", content="Hi!"),
        ]
        prompt = AIManager._build_prompt_from_conversation(conv)
        assert "user: Hello" in prompt
        assert "assistant: Hi!" in prompt

    def test_build_with_system_and_messages(self) -> None:
        conv = Conversation(system_prompt="Be brief.")
        conv.messages = [
            ConversationMessage(role="user", content="Q1"),
        ]
        prompt = AIManager._build_prompt_from_conversation(conv)
        lines = prompt.split("\n")
        assert lines[0] == "system: Be brief."
        assert lines[1] == "user: Q1"


from typing import Generator  # noqa: E402, F811
