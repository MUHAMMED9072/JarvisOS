from __future__ import annotations

import datetime

import customtkinter as ctk

from app.gui.controllers.dashboard_controller import (
    DashboardController,
    QuickActionResult,
)
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
    """Live command centre: system monitor, quick actions, activity log."""

    name = "dashboard"
    title = "Dashboard"

    def __init__(self, master, registry) -> None:
        super().__init__(master, registry)

        self._ctrl = DashboardController(registry)

        # ------------------------------------------------------------------
        # Layout: left column (system + commands) | right column (activity)
        # ------------------------------------------------------------------
        self.grid_columnconfigure(0, weight=2, minsize=500)
        self.grid_columnconfigure(1, weight=1, minsize=280)

        self._build_system_card()
        self._build_command_palette()
        self._build_activity_log()

        self._timer_id: str | None = None

    # ==================================================================
    # System monitor card (left column, top)
    # ==================================================================

    def _build_system_card(self) -> None:
        card = ctk.CTkFrame(
            self,
            corner_radius=15,
            fg_color=COLORS["card"],
        )
        card.grid(row=0, column=0, sticky="nsew", padx=(40, 10), pady=(30, 10))
        card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            card,
            text="System Monitor",
            font=("Segoe UI", 20, "bold"),
            text_color="white",
            anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=20, pady=(20, 10))

        self._sys_status = ctk.CTkLabel(
            card,
            justify="left",
            font=("Consolas", 15),
            text_color="white",
            anchor="w",
        )
        self._sys_status.grid(row=1, column=0, sticky="w", padx=20, pady=(0, 20))

    # ==================================================================
    # Command palette (left column, bottom)
    # ==================================================================

    def _build_command_palette(self) -> None:
        palette = ctk.CTkFrame(
            self,
            corner_radius=15,
            fg_color=COLORS["card"],
        )
        palette.grid(row=1, column=0, sticky="nsew", padx=(40, 10), pady=(10, 30))
        palette.grid_columnconfigure((0, 1), weight=1)
        palette.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            palette,
            text="Quick Actions",
            font=("Segoe UI", 20, "bold"),
            text_color="white",
            anchor="w",
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=20, pady=(20, 10))

        self._voice_btn = ctk.CTkButton(
            palette,
            text="Voice: Off",
            width=140,
            height=36,
            font=("Segoe UI", 13),
            fg_color=COLORS["card"],
            text_color=COLORS["text"],
            hover_color=COLORS["accent"],
            border_width=1,
            border_color=COLORS["accent"],
            command=self._toggle_voice,
        )
        self._voice_btn.grid(row=1, column=0, padx=(20, 5), pady=5, sticky="ew")

        ctk.CTkButton(
            palette,
            text="AI Quick Ask",
            width=140,
            height=36,
            font=("Segoe UI", 13),
            fg_color=COLORS["card"],
            text_color=COLORS["text"],
            hover_color=COLORS["accent"],
            border_width=1,
            border_color=COLORS["accent"],
            command=self._show_ai_ask,
        ).grid(row=1, column=1, padx=(5, 20), pady=5, sticky="ew")

        ctk.CTkButton(
            palette,
            text="Memory Search",
            width=140,
            height=36,
            font=("Segoe UI", 13),
            fg_color=COLORS["card"],
            text_color=COLORS["text"],
            hover_color=COLORS["accent"],
            border_width=1,
            border_color=COLORS["accent"],
            command=self._show_memory_search,
        ).grid(row=2, column=0, padx=(20, 5), pady=5, sticky="ew")

        ctk.CTkButton(
            palette,
            text="Open App",
            width=140,
            height=36,
            font=("Segoe UI", 13),
            fg_color=COLORS["card"],
            text_color=COLORS["text"],
            hover_color=COLORS["accent"],
            border_width=1,
            border_color=COLORS["accent"],
            command=self._show_open_app,
        ).grid(row=2, column=1, padx=(5, 20), pady=5, sticky="ew")

        # Inline input row (hidden by default)
        self._cmd_input = ctk.CTkEntry(
            palette,
            placeholder_text="Type a command...",
            font=("Segoe UI", 13),
            fg_color=COLORS["background"],
            text_color="white",
            border_color=COLORS["accent"],
        )
        self._cmd_input.grid(
            row=3, column=0, columnspan=2,
            sticky="ew", padx=20, pady=(5, 5),
        )
        self._cmd_input.grid_remove()

        self._cmd_btn_go = ctk.CTkButton(
            palette,
            text="Go",
            width=60,
            height=28,
            font=("Segoe UI", 12),
            fg_color=COLORS["accent"],
            text_color=COLORS["background"],
            hover_color="#00B8E6",
            command=self._execute_cmd,
        )

        self._cmd_result = ctk.CTkLabel(
            palette,
            text="",
            font=("Segoe UI", 12),
            text_color=COLORS["success"],
            anchor="w",
            wraplength=450,
        )
        self._cmd_result.grid(
            row=4, column=0, columnspan=2,
            sticky="ew", padx=20, pady=(0, 15),
        )

        self._cmd_mode: str = ""

    # ==================================================================
    # Activity log (right column)
    # ==================================================================

    def _build_activity_log(self) -> None:
        log_frame = ctk.CTkFrame(
            self,
            corner_radius=15,
            fg_color=COLORS["card"],
        )
        log_frame.grid(row=0, column=1, rowspan=2, sticky="nsew", padx=(10, 40), pady=30)
        log_frame.grid_rowconfigure(1, weight=1)
        log_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            log_frame,
            text="Recent Activity",
            font=("Segoe UI", 20, "bold"),
            text_color="white",
            anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=20, pady=(20, 10))

        self._activity_scroll = ctk.CTkScrollableFrame(
            log_frame,
            fg_color="transparent",
        )
        self._activity_scroll.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        self._activity_scroll.grid_columnconfigure(0, weight=1)

        self._activity_labels: list[ctk.CTkLabel] = []
        self._last_activity_count = 0

    # ==================================================================
    # Lifecycle
    # ==================================================================

    def on_activate(self) -> None:
        bus = self.registry.get("event_bus")
        self._ctrl.subscribe_events(bus)
        self._refresh()

    def on_deactivate(self) -> None:
        self._ctrl.unsubscribe_events()
        if self._timer_id is not None:
            self.after_cancel(self._timer_id)
            self._timer_id = None

    def _refresh(self) -> None:
        self._update_system_stats()
        self._update_activity_log()
        self._timer_id = self.after(2000, self._refresh)

    # ==================================================================
    # System stats
    # ==================================================================

    def _update_system_stats(self) -> None:
        try:
            cpu = cpu_usage()
            ram = ram_usage()
            disk = disk_usage()
            internet = internet_status()
            os_name = operating_system()
            py = python_version()
            clock = current_time()
            self._sys_status.configure(
                text=(
                    f"CPU Usage      : {cpu}\n"
                    f"RAM Usage      : {ram}\n"
                    f"Disk Usage     : {disk}\n"
                    f"Internet       : {internet}\n"
                    f"Operating Sys  : {os_name}\n"
                    f"Python Version : {py}\n"
                    f"Time           : {clock}"
                )
            )
        except Exception as e:
            self._sys_status.configure(text=f"Dashboard Error:\n{e}")

    # ==================================================================
    # Activity log
    # ==================================================================

    def _update_activity_log(self) -> None:
        entries = self._ctrl.get_activity_log()
        if len(entries) == self._last_activity_count:
            return
        self._last_activity_count = len(entries)

        for lbl in self._activity_labels:
            lbl.destroy()
        self._activity_labels.clear()

        for entry in reversed(entries[-50:]):
            ts = datetime.datetime.fromtimestamp(entry.timestamp).strftime(
                "%H:%M:%S"
            )
            lbl = ctk.CTkLabel(
                self._activity_scroll,
                text=f"[{ts}]  {entry.summary}",
                font=("Segoe UI", 12),
                text_color=COLORS["text"],
                anchor="w",
                wraplength=240,
            )
            lbl.pack(fill="x", padx=5, pady=1)
            self._activity_labels.append(lbl)

    # ==================================================================
    # Quick-action commands
    # ==================================================================

    def _toggle_voice(self) -> None:
        state = self._ctrl.toggle_voice()
        self._voice_btn.configure(text=f"Voice: {'On' if state else 'Off'}")
        self._cmd_result.configure(
            text=f"Voice {'enabled' if state else 'disabled'}",
            text_color=COLORS["success"],
        )
        self._update_activity_log()

    def _show_ai_ask(self) -> None:
        self._cmd_mode = "ai_ask"
        self._cmd_input.configure(placeholder_text="Ask AI a question...")
        self._cmd_input.grid()
        self._cmd_btn_go.grid(
            row=3, column=1, sticky="e", padx=(0, 20), pady=(5, 5),
        )
        self._cmd_input.focus()

    def _show_memory_search(self) -> None:
        self._cmd_mode = "memory_search"
        self._cmd_input.configure(placeholder_text="Search memory...")
        self._cmd_input.grid()
        self._cmd_btn_go.grid(
            row=3, column=1, sticky="e", padx=(0, 20), pady=(5, 5),
        )
        self._cmd_input.focus()

    def _show_open_app(self) -> None:
        self._cmd_mode = "open_app"
        self._cmd_input.configure(placeholder_text="Application name...")
        self._cmd_input.grid()
        self._cmd_btn_go.grid(
            row=3, column=1, sticky="e", padx=(0, 20), pady=(5, 5),
        )
        self._cmd_input.focus()

    def _execute_cmd(self) -> None:
        text = self._cmd_input.get().strip()
        if not text:
            return

        result: QuickActionResult | None = None

        if self._cmd_mode == "ai_ask":
            result = self._ctrl.quick_ask(text)
        elif self._cmd_mode == "memory_search":
            result = self._ctrl.search_memory(text)
        elif self._cmd_mode == "open_app":
            result = self._ctrl.open_app(text)

        if result is not None:
            clr = COLORS["success"] if result.success else COLORS["danger"]
            self._cmd_result.configure(text=result.message, text_color=clr)

        self._cmd_input.delete(0, "end")
        self._update_activity_log()
