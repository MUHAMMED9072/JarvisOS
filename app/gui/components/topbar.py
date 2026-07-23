from __future__ import annotations

import customtkinter as ctk


class TopBar(ctk.CTkFrame):
    """Top bar showing the current page title."""

    def __init__(self, master) -> None:
        super().__init__(master, fg_color="transparent")

        self.title_label = ctk.CTkLabel(
            self,
            text="",
            font=("Segoe UI", 32, "bold"),
            text_color="white",
        )
        self.title_label.pack(anchor="nw")

    def set_title(self, title: str) -> None:
        self.title_label.configure(text=title)
