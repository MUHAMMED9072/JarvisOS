from __future__ import annotations

import customtkinter as ctk

from app.gui.theme import COLORS


class MessageBubble(ctk.CTkFrame):
    """A single chat message displayed as a styled bubble.

    Parameters
    ----------
    master :
        Parent widget.
    text : str
        Message content.
    role : str
        ``"user"`` or ``"assistant"`` — controls alignment and colour.
    """

    def __init__(
        self,
        master,
        text: str,
        role: str,
    ) -> None:
        super().__init__(master, fg_color="transparent")

        self.grid_columnconfigure(1, weight=1)

        is_user = role == "user"
        bg = COLORS["accent"] if is_user else COLORS["card"]
        txt_clr = "white"
        anchor = "e" if is_user else "w"
        col = 2 if is_user else 0

        self.bubble = ctk.CTkFrame(
            self,
            corner_radius=12,
            fg_color=bg,
        )
        self.bubble.grid(row=0, column=col, padx=(10, 10), pady=4, sticky="ew")
        self.bubble.grid_columnconfigure(0, weight=1)

        self.label = ctk.CTkLabel(
            self.bubble,
            text=text,
            font=("Segoe UI", 14),
            text_color=txt_clr,
            anchor=anchor,
            justify="left",
            wraplength=500,
        )
        self.label.grid(row=0, column=0, padx=14, pady=10, sticky="ew")

        # Spacer column so user messages push left and assistant
        # messages push right — the weight=1 column in the middle
        # creates the asymmetry.
        if is_user:
            self.grid_columnconfigure(0, weight=0)
            self.grid_columnconfigure(1, weight=1)
        else:
            self.grid_columnconfigure(0, weight=1)
            self.grid_columnconfigure(1, weight=0)
