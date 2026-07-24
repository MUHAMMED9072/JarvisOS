from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.skills.result import SkillResult


@pytest.mark.skipif(
    not pytest.importorskip("customtkinter", reason="customtkinter not installed"),
)
class TestAIChatPage:
    @pytest.fixture(autouse=True)
    def _ctk_patch(self):
        """Ensure customtkinter is importable for page construction."""
        pass

    @pytest.fixture
    def registry(self):
        return MagicMock()

    @pytest.fixture
    def page(self, registry):
        with patch(
            "app.gui.pages.ai_chat.ChatController",
        ) as mock_ctrl_cls:
            mock_ctrl = MagicMock()
            mock_ctrl.load_history.return_value = []
            mock_ctrl.send_message.return_value = SkillResult.ok(
                message="Hello!"
            )
            mock_ctrl_cls.return_value = mock_ctrl

            from app.gui.pages.ai_chat import AIChatPage

            p = AIChatPage(MagicMock(), registry)
            p._controller = mock_ctrl
            return p

    def test_page_has_name(self, page):
        assert page.name == "chat"

    def test_page_has_title(self, page):
        assert page.title == "AI Chat"

    def test_on_activate_loads_history(self, page):
        page.on_activate()
        page._controller.load_history.assert_called_once()

    def test_new_conversation_clears_and_reloads(self, page):
        page._new_conversation()
        page._controller.clear_conversation.assert_called_once()
        page._controller.load_history.assert_called()

    def test_send_message_adds_bubble(self, page):
        page._on_send("hello")
        assert len(page._bubble_rows) > 0

    def test_send_message_handles_error(self, page):
        page._controller.send_message.return_value = SkillResult.fail(
            message="Something went wrong",
        )
        page._on_send("hello")
        assert len(page._bubble_rows) > 0

    def test_on_activate_focuses_input(self, page):
        with patch.object(page._chat_input, "focus") as mock_focus:
            page.on_activate()
            mock_focus.assert_called_once()
