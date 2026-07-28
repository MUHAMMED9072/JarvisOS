from __future__ import annotations

import logging
import time
from typing import Any, Optional

import customtkinter as ctk

from app.client.client import JarvisClient
from app.client.ui.base_view import BaseView
from app.client.ui.models import ChatMessage
from app.client.ui.worker import AsyncWorker

logger = logging.getLogger("jarvis.client.ui.pages.chat")


class AIChatView(BaseView):
    def __init__(
        self,
        master: Any,
        client: Optional[JarvisClient] = None,
        worker: Optional[AsyncWorker] = None,
        **kwargs: Any,
    ):
        super().__init__(master, **kwargs)
        self._client = client
        self._worker = worker
        self._messages: list[ChatMessage] = []
        self._streaming = False
        self._build_ui()

    def _build_ui(self) -> None:
        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=1)
        self.grid_rowconfigure(2, weight=0)
        self.grid_columnconfigure(0, weight=1)

        header = ctk.CTkLabel(
            self,
            text="AI Chat",
            font=("Segoe UI", 22, "bold"),
            anchor="w",
        )
        header.grid(row=0, column=0, sticky="w", padx=20, pady=(16, 8))

        chat_frame = ctk.CTkFrame(self)
        chat_frame.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 8))
        chat_frame.grid_rowconfigure(0, weight=1)
        chat_frame.grid_columnconfigure(0, weight=1)

        self._chat_display = ctk.CTkTextbox(chat_frame, wrap="word", font=("Segoe UI", 12))
        self._chat_display.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        self._chat_display.configure(state="disabled")

        input_frame = ctk.CTkFrame(self)
        input_frame.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 16))
        input_frame.grid_columnconfigure(0, weight=1)

        self._message_entry = ctk.CTkEntry(
            input_frame,
            placeholder_text="Type a message...",
            font=("Segoe UI", 12),
        )
        self._message_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8), pady=8)
        self._message_entry.bind("<Return>", lambda e: self._send_message())

        self._send_btn = ctk.CTkButton(
            input_frame,
            text="Send",
            command=self._send_message,
            width=80,
        )
        self._send_btn.grid(row=0, column=1, padx=0, pady=8)

        self._status_label = ctk.CTkLabel(
            self,
            text="",
            font=("Segoe UI", 10),
        )
        self._status_label.grid(row=3, column=0, sticky="w", padx=20, pady=(0, 4))

    def _send_message(self) -> None:
        text = self._message_entry.get().strip()
        if not text or self._streaming or not self._client or not self._worker:
            return

        self._message_entry.delete(0, "end")
        self._append_message("user", text)
        self._send_btn.configure(state="disabled", text="Sending...")
        self._streaming = True
        self._status_label.configure(text="Waiting for response...")

        async def do_chat():
            try:
                data = await self._client.rest.ai_chat(text)
                return data.get("response", "") or data.get("reply", "") or data.get("text", "") or str(data)
            except Exception as exc:
                return f"Error: {exc}"

        def done(result: Any, error: str = "") -> None:
            self._streaming = False
            self._send_btn.configure(state="normal", text="Send")
            if error:
                self._append_message("assistant", f"Error: {error}")
                self._status_label.configure(text=f"Error: {error}")
            elif result and isinstance(result, str):
                self._append_message("assistant", result)
                self._status_label.configure(text="")
            else:
                self._append_message("assistant", str(result) if result else "No response")
                self._status_label.configure(text="")

        self._worker.run(do_chat(), done)

    def _append_message(self, role: str, content: str) -> None:
        msg = ChatMessage(role=role, content=content, timestamp=time.time())
        self._messages.append(msg)

        self._chat_display.configure(state="normal")
        prefix = "You" if role == "user" else "AI"
        tag = "user" if role == "user" else "assistant"
        self._chat_display.insert("end", f"{prefix}: ", (tag,))
        self._chat_display.insert("end", f"{content}\n\n", (tag,))
        self._chat_display.see("end")
        self._chat_display.configure(state="disabled")

    def on_refresh(self) -> None:
        pass

    def on_destroy(self) -> None:
        self._messages.clear()
        super().on_destroy()
