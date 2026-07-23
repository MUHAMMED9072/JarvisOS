from __future__ import annotations

import customtkinter as ctk

from app.core.registry import ServiceRegistry


class BasePage(ctk.CTkFrame):
    """Base class for all GUI pages."""

    name: str = ""
    title: str = ""

    def __init__(self, master, registry: ServiceRegistry) -> None:
        super().__init__(master, fg_color="transparent")
        self.registry = registry

    def on_activate(self) -> None:
        """Called when page becomes visible."""

    def on_deactivate(self) -> None:
        """Called when page is hidden."""
