from __future__ import annotations

import customtkinter as ctk

from app.core.registry import ServiceRegistry
from app.gui.theme import COLORS


class StatusBar(ctk.CTkFrame):
    """Bottom status bar for system state."""

    def __init__(self, master, registry: ServiceRegistry) -> None:
        super().__init__(master, height=30, fg_color=COLORS["sidebar"])
        self.registry = registry

        self.label = ctk.CTkLabel(
            self,
            text="",
            text_color=COLORS["text"],
            font=("Consolas", 12),
        )
        self.label.pack(side="left", padx=15)

    def set_status(self, text: str) -> None:
        self.label.configure(text=text)
