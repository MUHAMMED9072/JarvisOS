from __future__ import annotations

from collections.abc import Callable

import customtkinter as ctk

from app.gui.theme import COLORS


class ChatInput(ctk.CTkFrame):
    """A chat text input with a send button.

    Parameters
    ----------
    master :
        Parent widget.
    on_send : Callable[[str], None]
        Called with the trimmed text when the user clicks Send or
        presses Enter.
    """

    def __init__(
        self,
        master,
        on_send: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(master, fg_color="transparent")

        self.on_send = on_send

        self.grid_columnconfigure(0, weight=1)

        self.entry = ctk.CTkEntry(
            self,
            placeholder_text="Type a message...",
            font=("Segoe UI", 14),
            height=40,
        )
        self.entry.grid(row=0, column=0, padx=(0, 8), sticky="ew")
        self.entry.bind("<Return>", lambda _: self._send())

        self.send_button = ctk.CTkButton(
            self,
            text="Send",
            width=80,
            height=40,
            font=("Segoe UI", 14, "bold"),
            fg_color=COLORS["accent"],
            text_color="white",
            command=self._send,
        )
        self.send_button.grid(row=0, column=1, padx=(0, 0))

    def _send(self) -> None:
        text = self.entry.get().strip()
        if not text:
            return
        if self.on_send is not None:
            self.on_send(text)
        self.entry.delete(0, "end")

    def set_loading(self, loading: bool) -> None:
        """Enable or disable the input during request processing."""
        state = "disabled" if loading else "normal"
        self.entry.configure(state=state)
        self.send_button.configure(state=state)

    def focus(self) -> None:
        self.entry.focus()
