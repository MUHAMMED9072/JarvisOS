from __future__ import annotations

from collections.abc import Callable

import customtkinter as ctk

from app.gui.theme import COLORS, SIDEBAR_WIDTH


class Sidebar(ctk.CTkFrame):
    """Main navigation sidebar with active page highlighting."""

    def __init__(
        self,
        master,
        on_navigate: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(
            master,
            width=SIDEBAR_WIDTH,
            corner_radius=0,
            fg_color=COLORS["sidebar"],
        )

        self.on_navigate = on_navigate
        self._buttons: dict[str, ctk.CTkButton] = {}
        self._active_button: ctk.CTkButton | None = None

        # Logo
        self.logo = ctk.CTkLabel(
            self,
            text="\U0001f916 JARVIS",
            font=("Segoe UI", 30, "bold"),
            text_color=COLORS["accent"],
        )
        self.logo.pack(pady=(35, 25))

        # Menu items: (display_text, page_name)
        menu_items: list[tuple[str, str]] = [
            ("\U0001f3e0 Dashboard", "dashboard"),
            ("\U0001f4ac Chat", "chat"),
            ("\U0001f3a4 Voice", "voice"),
            ("\U0001f9e0 Memory", "memory"),
            ("\u26a1 Skills", "skills"),
            ("\U0001f916 AI", "ai"),
            ("\u2699 Settings", "settings"),
            ("\U0001f4dc Logs", "logs"),
        ]

        for text, page_name in menu_items:
            button = ctk.CTkButton(
                self,
                text=text,
                anchor="w",
                height=42,
                corner_radius=8,
                fg_color="transparent",
                text_color=COLORS["text"],
                hover_color=COLORS["card"],
                command=lambda p=page_name: self._on_click(p),
            )
            button.pack(fill="x", padx=15, pady=5)
            self._buttons[page_name] = button

        # Spacer at bottom
        self.grid_rowconfigure(99, weight=1)

    def _on_click(self, page_name: str) -> None:
        if self.on_navigate is not None:
            self.on_navigate(page_name)

    def set_active(self, page_name: str) -> None:
        """Highlight the button for the active page."""
        if self._active_button is not None:
            self._active_button.configure(
                fg_color="transparent",
                text_color=COLORS["text"],
            )

        button = self._buttons.get(page_name)
        if button is not None:
            button.configure(
                fg_color=COLORS["card"],
                text_color=COLORS["accent"],
            )
            self._active_button = button
