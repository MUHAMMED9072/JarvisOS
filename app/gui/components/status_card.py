from __future__ import annotations

import customtkinter as ctk

from app.gui.theme import COLORS


class StatusCard(ctk.CTkFrame):
    """A card widget for displaying a single metric."""

    def __init__(
        self,
        master,
        title: str = "",
        value: str = "",
        color: str = COLORS["accent"],
    ) -> None:
        super().__init__(master, corner_radius=15, fg_color=COLORS["card"])

        self.title_label = ctk.CTkLabel(
            self,
            text=title,
            font=("Segoe UI", 14),
            text_color=COLORS["text"],
        )
        self.title_label.pack(anchor="nw", padx=15, pady=(15, 5))

        self.value_label = ctk.CTkLabel(
            self,
            text=value,
            font=("Segoe UI", 24, "bold"),
            text_color=color,
        )
        self.value_label.pack(anchor="nw", padx=15, pady=(0, 15))

    def set_value(self, value: str) -> None:
        self.value_label.configure(text=value)

    def set_color(self, color: str) -> None:
        self.value_label.configure(text_color=color)
