from __future__ import annotations

import customtkinter as ctk

from app.gui.pages.base_page import BasePage
from app.gui.theme import COLORS
from app.utils.system import (
    cpu_usage,
    current_time,
    disk_usage,
    internet_status,
    operating_system,
    python_version,
    ram_usage,
)


class DashboardPage(BasePage):
    """System monitor dashboard with live polling."""

    name = "dashboard"
    title = "Dashboard"

    def __init__(self, master, registry) -> None:
        super().__init__(master, registry)

        self.card = ctk.CTkFrame(
            self,
            width=900,
            height=320,
            corner_radius=15,
            fg_color=COLORS["card"],
        )

        self.card.pack(anchor="nw", padx=40, pady=30)
        self.card.pack_propagate(False)

        title = ctk.CTkLabel(
            self.card,
            text="System Monitor",
            font=("Segoe UI", 24, "bold"),
            text_color="white",
        )

        title.pack(anchor="nw", padx=20, pady=(20, 10))

        self.status = ctk.CTkLabel(
            self.card,
            justify="left",
            font=("Consolas", 17),
            text_color="white",
        )

        self.status.pack(anchor="nw", padx=20)

        self._timer_id: str | None = None

    def on_activate(self) -> None:
        self.update_dashboard()

    def on_deactivate(self) -> None:
        if self._timer_id is not None:
            self.after_cancel(self._timer_id)
            self._timer_id = None

    def update_dashboard(self) -> None:
        try:
            cpu = cpu_usage()
            ram = ram_usage()
            disk = disk_usage()
            internet = internet_status()
            os_name = operating_system()
            py = python_version()
            clock = current_time()

            self.status.configure(
                text=(
                    f"CPU Usage      : {cpu}\n\n"
                    f"RAM Usage      : {ram}\n\n"
                    f"Disk Usage     : {disk}\n\n"
                    f"Internet       : {internet}\n\n"
                    f"Operating Sys  : {os_name}\n\n"
                    f"Python Version : {py}\n\n"
                    f"Time           : {clock}\n\n"
                    f"Ollama Status  : Online\n\n"
                    f"Voice Engine   : Ready"
                )
            )

        except Exception as e:
            self.status.configure(text=f"Dashboard Error:\n\n{e}")

        self._timer_id = self.after(1000, self.update_dashboard)
