from __future__ import annotations

import datetime
from tkinter import filedialog

import customtkinter as ctk

from app.core.registry import ServiceRegistry
from app.gui.controllers.logs_controller import LogsController
from app.gui.pages.base_page import BasePage
from app.gui.theme import COLORS

_LEVEL_COLORS = {
    "DEBUG": "#64748B",
    "INFO": COLORS["text"],
    "WARNING": COLORS["warning"],
    "ERROR": COLORS["danger"],
    "CRITICAL": COLORS["danger"],
}


class LogsPage(BasePage):
    """Logs Viewer with filtering, search, auto-scroll, export."""

    name = "logs"
    title = "Logs"

    def __init__(self, master, registry: ServiceRegistry) -> None:
        super().__init__(master, registry)

        self._ctrl = LogsController(registry)

        self._level_filter: str | None = None
        self._auto_scroll = True

        self._build_top_bar()
        self._build_filters()
        self._build_log_view()
        self._build_status_bar()

        self._timer_id: str | None = None

    # ==================================================================
    # Top bar
    # ==================================================================

    def _build_top_bar(self) -> None:
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=40, pady=(20, 5))

        ctk.CTkLabel(
            top,
            text="Logs Viewer",
            font=("Segoe UI", 24, "bold"),
            text_color="white",
        ).pack(side="left")

    # ==================================================================
    # Filter row
    # ==================================================================

    def _build_filters(self) -> None:
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=40, pady=(10, 8))
        row.grid_columnconfigure(3, weight=1)

        # Level filter buttons
        self._level_btns: dict[str, ctk.CTkButton] = {}
        levels = ["All", "INFO", "WARNING", "ERROR", "DEBUG"]
        for i, lvl in enumerate(levels):
            btn = ctk.CTkButton(
                row,
                text=lvl,
                width=70,
                height=28,
                font=("Segoe UI", 12),
                fg_color=COLORS["accent"] if lvl == "All" else COLORS["card"],
                text_color=COLORS["background"] if lvl == "All" else COLORS["text"],
                hover_color=COLORS["accent"],
                command=lambda v=lvl: self._set_level_filter(v),
            )
            btn.grid(row=0, column=i, padx=(0, 6))
            self._level_btns[lvl] = btn

        # Search
        self._search_entry = ctk.CTkEntry(
            row,
            placeholder_text="Search logs...",
            font=("Segoe UI", 13),
            width=200,
            fg_color=COLORS["card"],
            text_color="white",
            border_color=COLORS["accent"],
        )
        self._search_entry.grid(row=0, column=3, padx=(20, 0), sticky="e")
        self._search_entry.bind("<Return>", lambda e: self._refresh_view())

    # ==================================================================
    # Control buttons row
    # ==================================================================

    def _build_controls_row(self, parent) -> None:
        controls = ctk.CTkFrame(parent, fg_color="transparent")
        controls.pack(fill="x", padx=0, pady=(0, 8))
        controls.grid_columnconfigure(3, weight=1)

        self._auto_btn = ctk.CTkButton(
            controls,
            text="Auto-scroll: ON",
            width=110,
            height=28,
            font=("Segoe UI", 12),
            fg_color=COLORS["card"],
            text_color=COLORS["text"],
            hover_color=COLORS["accent"],
            command=self._toggle_auto_scroll,
        )
        self._auto_btn.grid(row=0, column=0, padx=(0, 6))

        self._pause_btn = ctk.CTkButton(
            controls,
            text="Pause",
            width=70,
            height=28,
            font=("Segoe UI", 12),
            fg_color=COLORS["card"],
            text_color=COLORS["text"],
            hover_color=COLORS["accent"],
            command=self._toggle_pause,
        )
        self._pause_btn.grid(row=0, column=1, padx=(0, 6))

        ctk.CTkButton(
            controls,
            text="Clear",
            width=70,
            height=28,
            font=("Segoe UI", 12),
            fg_color=COLORS["card"],
            text_color=COLORS["text"],
            hover_color=COLORS["accent"],
            command=self._clear_view,
        ).grid(row=0, column=2, padx=(0, 6))

        ctk.CTkButton(
            controls,
            text="Export",
            width=70,
            height=28,
            font=("Segoe UI", 12),
            fg_color=COLORS["card"],
            text_color=COLORS["text"],
            hover_color=COLORS["accent"],
            command=self._export_logs,
        ).grid(row=0, column=4, padx=(6, 0))

    # ==================================================================
    # Log view
    # ==================================================================

    def _build_log_view(self) -> None:
        container = ctk.CTkFrame(self, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=40, pady=(0, 5))

        self._build_controls_row(container)

        self._log_text = ctk.CTkTextbox(
            container,
            font=("Consolas", 12),
            fg_color=COLORS["card"],
            text_color=COLORS["text"],
            wrap="none",
        )
        self._log_text.pack(fill="both", expand=True)

        # Define level colour tags
        for lvl, clr in _LEVEL_COLORS.items():
            self._log_text.tag_config(lvl, foreground=clr)
        self._log_text.tag_config("timestamp", foreground="#64748B")

    # ==================================================================
    # Status bar
    # ==================================================================

    def _build_status_bar(self) -> None:
        self._status_label = ctk.CTkLabel(
            self,
            text="",
            font=("Segoe UI", 12),
            text_color="#94A3B8",
            anchor="w",
        )
        self._status_label.pack(fill="x", padx=40, pady=(0, 10))

    # ==================================================================
    # Lifecycle
    # ==================================================================

    def on_activate(self) -> None:
        self._ctrl.refresh()
        self._refresh_view()
        self._timer_id = self.after(2000, self._poll)

    def on_deactivate(self) -> None:
        if self._timer_id is not None:
            self.after_cancel(self._timer_id)
            self._timer_id = None

    # ==================================================================
    # Polling
    # ==================================================================

    def _poll(self) -> None:
        if not self._ctrl.paused:
            self._ctrl.refresh()
            self._update_view()
        self._timer_id = self.after(2000, self._poll)

    # ==================================================================
    # View rendering
    # ==================================================================

    def _refresh_view(self) -> None:
        self._log_text.delete("1.0", "end")
        self._update_view()

    def _update_view(self) -> None:
        self._log_text.configure(state="normal")

        if self._ctrl.paused:
            return

        entries = self._ctrl.get_entries(
            level_filter=self._level_filter,
            search=self._search_entry.get().strip() or None,
        )

        self._log_text.delete("1.0", "end")

        for e in entries:
            ts_tag = "timestamp"
            level_tag = e.level if e.level in _LEVEL_COLORS else "INFO"

            self._log_text.insert("end", e.timestamp + " ", ts_tag)
            self._log_text.insert("end", "| " + e.level + " | ", level_tag)
            self._log_text.insert("end", e.message + "\n", level_tag)

        if self._auto_scroll:
            self._log_text.see("end")

        self._log_text.configure(state="disabled")

        self._status_label.configure(
            text=f"{len(entries)} entries  |  {self._ctrl.filepath}"
        )

    # ==================================================================
    # Actions
    # ==================================================================

    def _set_level_filter(self, level: str) -> None:
        self._level_filter = None if level == "All" else level
        for lvl, btn in self._level_btns.items():
            is_active = lvl == level
            btn.configure(
                fg_color=COLORS["accent"] if is_active else COLORS["card"],
                text_color=COLORS["background"] if is_active else COLORS["text"],
            )
        self._refresh_view()

    def _toggle_auto_scroll(self) -> None:
        self._auto_scroll = not self._auto_scroll
        self._auto_btn.configure(
            text=f"Auto-scroll: {'ON' if self._auto_scroll else 'OFF'}"
        )

    def _toggle_pause(self) -> None:
        self._ctrl.paused = not self._ctrl.paused
        self._pause_btn.configure(
            text="Resume" if self._ctrl.paused else "Pause",
            fg_color=COLORS["warning"] if self._ctrl.paused else COLORS["card"],
            text_color=COLORS["background"] if self._ctrl.paused else COLORS["text"],
        )

    def _clear_view(self) -> None:
        self._log_text.configure(state="normal")
        self._log_text.delete("1.0", "end")
        self._log_text.configure(state="disabled")

    def _export_logs(self) -> None:
        filepath = filedialog.asksaveasfilename(
            defaultextension=".log",
            filetypes=[("Log files", "*.log"), ("Text files", "*.txt"), ("All files", "*.*")],
            title="Export Logs",
        )
        if not filepath:
            return
        entries = self._ctrl.get_entries(
            level_filter=self._level_filter,
            search=self._search_entry.get().strip() or None,
        )
        self._ctrl.export_entries(entries, filepath)
