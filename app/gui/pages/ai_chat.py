from __future__ import annotations

import threading

import customtkinter as ctk

from app.core.registry import ServiceRegistry
from app.gui.controllers.chat_controller import ChatController
from app.gui.pages.base_page import BasePage
from app.gui.theme import COLORS
from app.gui.widgets.chat_input import ChatInput
from app.gui.widgets.message_bubble import MessageBubble


class AIChatPage(BasePage):
    """Full AI chat page with conversation history, streaming,
    metadata, and plan/reason support."""

    name = "chat"
    title = "AI Chat"

    def __init__(self, master, registry: ServiceRegistry) -> None:
        super().__init__(master, registry)

        self._controller = ChatController(registry)
        self._controller.on_voice_input = self._on_send

        # Top row: title + new-chat button
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

        # Mode row: Chat / Plan / Reason toggle
        mode_row = ctk.CTkFrame(self, fg_color="transparent")
        mode_row.pack(fill="x", padx=40, pady=(5, 5))

        self._mode_var = ctk.StringVar(value="chat")
        for mode_val, label in [("chat", "Chat"), ("plan", "Plan"), ("reason", "Reason")]:
            btn = ctk.CTkButton(
                mode_row,
                text=label,
                width=80,
                height=28,
                font=("Segoe UI", 12),
                fg_color=COLORS["card"],
                text_color=COLORS["text"],
                hover_color=COLORS["accent"],
                command=lambda v=mode_val: self._set_mode(v),
            )
            btn.pack(side="left", padx=(0, 8))
            if mode_val == "chat":
                btn.configure(fg_color=COLORS["accent"], text_color=COLORS["background"])

        self._mode_buttons = mode_row

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

        self._bubble_rows: list[ctk.CTkFrame] = []
        self._typing_row: ctk.CTkFrame | None = None
        self._stream_bubble: ctk.CTkFrame | None = None
        self._stream_label: ctk.CTkLabel | None = None

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
    # Mode switching
    # ------------------------------------------------------------------

    def _set_mode(self, mode: str) -> None:
        self._mode_var.set(mode)
        placeholder = {
            "chat": "Type a message...",
            "plan": "Enter an objective to plan...",
            "reason": "Enter a topic to reason about...",
        }.get(mode, "Type a message...")
        self._chat_input.entry.configure(placeholder_text=placeholder)
        for child in self._mode_buttons.winfo_children():
            if isinstance(child, ctk.CTkButton):
                txt = child.cget("text").lower()
                if txt == mode:
                    child.configure(fg_color=COLORS["accent"], text_color=COLORS["background"])
                else:
                    child.configure(fg_color=COLORS["card"], text_color=COLORS["text"])

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
        self._controller.new_conversation()
        self._load_history()
        self._chat_input.focus()

    # ------------------------------------------------------------------
    # Send / receive
    # ------------------------------------------------------------------

    def _on_send(self, text: str) -> None:
        mode = self._mode_var.get()
        self._add_bubble(text, "user")
        self._show_typing()

        if mode == "plan":
            self._chat_input.set_loading(True)
            threading.Thread(
                target=self._run_plan,
                args=(text,),
                daemon=True,
            ).start()
        elif mode == "reason":
            self._chat_input.set_loading(True)
            threading.Thread(
                target=self._run_reason,
                args=(text,),
                daemon=True,
            ).start()
        else:
            self._chat_input.set_loading(True)
            threading.Thread(
                target=self._run_stream_chat,
                args=(text,),
                daemon=True,
            ).start()

    def _run_stream_chat(self, text: str) -> None:
        try:
            stream = self._controller.send_message_stream(text)
            self._hide_typing()
            self._show_stream_bubble()
            for chunk in stream:
                self.after(0, self._append_stream_text, chunk.content)
            result = stream.final_response()
            self.after(0, self._finalize_stream, str(result), result)
        except Exception as exc:
            self.after(0, self._show_error, f"AI error: {exc}")

    def _run_plan(self, objective: str) -> None:
        try:
            result = self._controller.send_plan(objective)
            self.after(0, self._show_result, result)
        except Exception as exc:
            self.after(0, self._show_error, f"Plan error: {exc}")

    def _run_reason(self, objective: str) -> None:
        try:
            result = self._controller.send_reason(objective)
            self.after(0, self._show_result, result)
        except Exception as exc:
            self.after(0, self._show_error, f"Reason error: {exc}")

    # ------------------------------------------------------------------
    # Stream bubble management
    # ------------------------------------------------------------------

    def _show_stream_bubble(self) -> None:
        row = ctk.CTkFrame(self._message_frame, fg_color="transparent")
        row.grid(sticky="ew", pady=(2, 2))
        row.grid_columnconfigure(0, weight=1)

        bg = COLORS["card"]
        bubble = ctk.CTkFrame(row, corner_radius=12, fg_color=bg)
        bubble.grid(row=0, column=0, padx=(10, 10), pady=4, sticky="ew")
        bubble.grid_columnconfigure(0, weight=1)

        self._stream_label = ctk.CTkLabel(
            bubble,
            text="",
            font=("Segoe UI", 14),
            text_color="white",
            anchor="w",
            justify="left",
            wraplength=500,
        )
        self._stream_label.grid(row=0, column=0, padx=14, pady=10, sticky="ew")

        self._stream_bubble = row
        self._bubble_rows.append(row)
        self._scroll_to_bottom()

    def _append_stream_text(self, text: str) -> None:
        if self._stream_label is not None:
            current = self._stream_label.cget("text")
            self._stream_label.configure(text=current + text)
            self._scroll_to_bottom()

    def _finalize_stream(self, full_text: str, response) -> None:
        self._chat_input.set_loading(False)
        self._show_metadata(
            provider=response.provider if response else "",
            model=response.model if response else "",
            latency_ms=response.latency_ms if response else 0.0,
        )
        self._stream_bubble = None
        self._stream_label = None

    # ------------------------------------------------------------------
    # Non-streaming result display
    # ------------------------------------------------------------------

    def _show_result(self, result) -> None:
        self._chat_input.set_loading(False)
        self._hide_typing()
        if result.success:
            self._add_bubble(result.response, "assistant")
            self._show_metadata(
                provider=result.provider,
                model=result.model,
                latency_ms=result.latency_ms,
                response_type=result.response_type,
            )
        else:
            self._add_bubble(result.error or "I'm not sure how to respond.", "assistant")
        self._scroll_to_bottom()

    def _show_error(self, message: str) -> None:
        self._chat_input.set_loading(False)
        self._hide_typing()
        if self._stream_bubble is not None:
            self._stream_bubble.destroy()
            self._stream_bubble = None
            self._stream_label = None
        self._add_bubble(message, "assistant")
        self._scroll_to_bottom()

    # ------------------------------------------------------------------
    # Metadata display
    # ------------------------------------------------------------------

    def _show_metadata(
        self,
        *,
        provider: str = "",
        model: str = "",
        latency_ms: float = 0.0,
        response_type: str = "chat",
    ) -> None:
        parts = []
        if provider:
            parts.append(f"Provider: {provider}")
        if model:
            parts.append(f"Model: {model}")
        if latency_ms:
            parts.append(f"Latency: {latency_ms:.0f}ms")
        if response_type and response_type != "chat":
            parts.append(f"Type: {response_type}")
        if not parts:
            return
        meta_text = " | ".join(parts)
        row = ctk.CTkFrame(self._message_frame, fg_color="transparent")
        row.grid(sticky="ew", pady=(0, 4))
        row.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            row,
            text=meta_text,
            font=("Consolas", 10),
            text_color="#64748B",
            anchor="w",
        ).grid(row=0, column=0, padx=(24, 0), sticky="w")
        self._bubble_rows.append(row)

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
        if self._stream_bubble is not None:
            self._stream_bubble.destroy()
            self._stream_bubble = None
            self._stream_label = None

    def _scroll_to_bottom(self) -> None:
        self._message_frame._parent_canvas.yview_moveto(1.0)
