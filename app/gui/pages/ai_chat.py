from __future__ import annotations

import customtkinter as ctk

from app.core.registry import ServiceRegistry
from app.gui.controllers.chat_controller import ChatController
from app.gui.pages.base_page import BasePage
from app.gui.theme import COLORS
from app.gui.widgets.chat_input import ChatInput
from app.gui.widgets.message_bubble import MessageBubble


class AIChatPage(BasePage):
    """Full AI chat page with conversation history and message bubbles."""

    name = "chat"
    title = "AI Chat"

    def __init__(self, master, registry: ServiceRegistry) -> None:
        super().__init__(master, registry)

        self._controller = ChatController(registry)
        self._controller.on_voice_input = self._on_send

        # Top bar with new-chat button
        top_row = ctk.CTkFrame(self, fg_color="transparent")
        top_row.pack(fill="x", padx=40, pady=(20, 5))

        ctk.CTkLabel(
            top_row,
            text="AI Chat",
            font=("Segoe UI", 24, "bold"),
            text_color="white",
        ).pack(side="left")

        self._new_chat_btn = ctk.CTkButton(
            top_row,
            text="New Chat",
            width=100,
            height=32,
            font=("Segoe UI", 13),
            fg_color=COLORS["card"],
            text_color=COLORS["text"],
            hover_color=COLORS["accent"],
            command=self._new_conversation,
        )
        self._new_chat_btn.pack(side="right")

        # Scrollable message area
        self._message_frame = ctk.CTkScrollableFrame(
            self,
            fg_color="transparent",
        )
        self._message_frame.pack(
            fill="both",
            expand=True,
            padx=40,
            pady=(10, 10),
        )
        self._message_frame.grid_columnconfigure(0, weight=1)

        # Keep track of displayed bubble rows for the typing indicator
        self._bubble_rows: list[ctk.CTkFrame] = []
        self._typing_row: ctk.CTkFrame | None = None

        # Chat input at the bottom
        self._chat_input = ChatInput(
            self,
            on_send=self._on_send,
        )
        self._chat_input.pack(fill="x", padx=40, pady=(0, 20))

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_activate(self) -> None:
        bus = self.registry.get("event_bus")
        self._controller.subscribe_events(bus)
        self._load_history()
        self._chat_input.focus()

    def on_deactivate(self) -> None:
        self._controller.unsubscribe_events()

    # ------------------------------------------------------------------
    # History loading
    # ------------------------------------------------------------------

    def _load_history(self) -> None:
        self._clear_bubbles()
        messages = self._controller.load_history()
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if content:
                self._add_bubble(content, role)

    def _new_conversation(self) -> None:
        self._controller.clear_conversation()
        self._load_history()
        self._chat_input.focus()

    # ------------------------------------------------------------------
    # Send / receive
    # ------------------------------------------------------------------

    def _on_send(self, text: str) -> None:
        self._add_bubble(text, "user")
        self._show_typing()

        try:
            result = self._controller.send_message(text)
        except Exception as exc:
            self._hide_typing()
            self._add_bubble(f"Error: {exc}", "assistant")
            self._chat_input.set_loading(False)
            return

        self._hide_typing()

        if result.success:
            self._add_bubble(result.message, "assistant")
        else:
            self._add_bubble(result.message or "I'm not sure how to respond.",
                             "assistant")

        self._chat_input.set_loading(False)
        self._scroll_to_bottom()

    # ------------------------------------------------------------------
    # Bubble management
    # ------------------------------------------------------------------

    def _add_bubble(self, text: str, role: str) -> None:
        row = ctk.CTkFrame(self._message_frame, fg_color="transparent")
        row.grid(sticky="ew", pady=(2, 2))
        row.grid_columnconfigure(0, weight=1)

        bubble = MessageBubble(row, text, role)
        bubble.pack(fill="x")

        self._bubble_rows.append(row)
        self._scroll_to_bottom()

    def _show_typing(self) -> None:
        self._chat_input.set_loading(True)
        row = ctk.CTkFrame(self._message_frame, fg_color="transparent")
        row.grid(sticky="ew", pady=(2, 2))
        row.grid_columnconfigure(0, weight=1)

        bubble = MessageBubble(row, "Thinking...", "assistant")
        bubble.pack(fill="x")

        self._typing_row = row
        self._scroll_to_bottom()

    def _hide_typing(self) -> None:
        if self._typing_row is not None:
            self._typing_row.destroy()
            self._typing_row = None

    def _clear_bubbles(self) -> None:
        for row in self._bubble_rows:
            row.destroy()
        self._bubble_rows.clear()
        self._hide_typing()

    def _scroll_to_bottom(self) -> None:
        self._message_frame._parent_canvas.yview_moveto(1.0)
