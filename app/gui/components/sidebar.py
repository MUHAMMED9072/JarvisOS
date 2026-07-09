from __future__ import annotations

import customtkinter as ctk


class Sidebar(ctk.CTkFrame):
    """Main navigation sidebar."""

    def __init__(self, master):
        super().__init__(master, width=220, corner_radius=0)

        self.grid_rowconfigure(99, weight=1)

        # Logo
        self.logo = ctk.CTkLabel(
            self,
            text="JARVIS",
            font=("Segoe UI", 24, "bold")
        )
        self.logo.pack(pady=(25, 30))

        self.buttons = {}

        menu_items = [
            "Dashboard",
            "AI Chat",
            "Voice",
            "Memory",
            "Automation",
            "Plugins",
            "Settings",
        ]

        for item in menu_items:
            button = ctk.CTkButton(
                self,
                text=item,
                height=42,
                anchor="w"
            )

            button.pack(fill="x", padx=15, pady=5)

            self.buttons[item] = button
            