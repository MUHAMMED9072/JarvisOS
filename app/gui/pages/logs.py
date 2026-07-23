from __future__ import annotations

import customtkinter as ctk

from app.core.registry import ServiceRegistry
from app.gui.pages.base_page import BasePage


class LogsPage(BasePage):
    name = "logs"
    title = "Logs"

    def __init__(self, master, registry: ServiceRegistry) -> None:
        super().__init__(master, registry)

        label = ctk.CTkLabel(
            self,
            text="Logs\n\nComing Soon",
            font=("Segoe UI", 24),
            text_color="#94A3B8",
            justify="center",
        )
        label.pack(expand=True)
