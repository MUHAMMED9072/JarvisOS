from __future__ import annotations

import logging
from typing import Any, Callable, Optional

import customtkinter as ctk

from app.client.events import EventDispatcher
from app.client.state import ClientState
from app.client.ui.bindings import StateBinding
from app.client.ui.navigation import Navigator
from app.client.ui.theme import ThemeManager
from app.client.ui.widgets import ConnectionIndicator, Toolbar, SidebarItem

logger = logging.getLogger("jarvis.client.ui.window")


class MainWindow(ctk.CTk):
    def __init__(
        self,
        title: str = "JARVIS Desktop",
        width: int = 1200,
        height: int = 800,
        min_width: int = 800,
        min_height: int = 600,
        theme: Optional[ThemeManager] = None,
        navigator: Optional[Navigator] = None,
        state: Optional[ClientState] = None,
        events: Optional[EventDispatcher] = None,
        **kwargs: Any,
    ):
        super().__init__(**kwargs)
        self.title(title)
        self.geometry(f"{width}x{height}")
        self.minsize(min_width, min_height)

        self._events = events or EventDispatcher()
        self._state = state
        self._theme = theme or ThemeManager(self._events)
        self._navigator = navigator or Navigator(self._events)
        self._bindings = StateBinding(state, self._events, self._theme) if state else None

        self._sidebar_visible = True
        self._sidebar_width = 220
        self._window_pos = (0, 0)
        self._sidebar_items: dict[str, SidebarItem] = {}

        self._configure_grid()
        self._build_sidebar()
        self._build_toolbar()
        self._build_content_area()
        self._build_status_bar()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._bind_state()

    def _configure_grid(self) -> None:
        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=1)
        self.grid_rowconfigure(2, weight=0)
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)

    def _build_sidebar(self) -> None:
        self._sidebar = ctk.CTkFrame(self, width=self._sidebar_width, corner_radius=0)
        self._sidebar.grid(row=0, column=0, rowspan=3, sticky="ns")
        self._sidebar.grid_propagate(False)

        self._sidebar.grid_rowconfigure(0, weight=0)
        self._sidebar.grid_rowconfigure(1, weight=0)
        self._sidebar.grid_rowconfigure(2, weight=1)
        self._sidebar.grid_rowconfigure(3, weight=0)
        self._sidebar.grid_columnconfigure(0, weight=1)

        self._brand_label = ctk.CTkLabel(
            self._sidebar,
            text="JARVIS",
            font=("Segoe UI", 16, "bold"),
        )
        self._brand_label.grid(row=0, column=0, pady=(16, 8))

        self._nav_separator = ctk.CTkFrame(self._sidebar, height=1)
        self._nav_separator.grid(row=1, column=0, sticky="ew", padx=8, pady=4)

        self._nav_frame = ctk.CTkScrollableFrame(self._sidebar)
        self._nav_frame.grid(row=2, column=0, sticky="nsew")
        self._nav_frame.grid_columnconfigure(0, weight=1)

        self._sidebar_bottom = ctk.CTkFrame(self._sidebar, fg_color="transparent")
        self._sidebar_bottom.grid(row=3, column=0, sticky="ew", pady=(0, 8))
        self._sidebar_bottom.grid_columnconfigure(0, weight=1)

        self._theme_btn = ctk.CTkButton(
            self._sidebar_bottom,
            text="🌙 Dark",
            command=self._toggle_theme,
            height=28,
            font=("Segoe UI", 11),
        )
        self._theme_btn.grid(row=0, column=0, padx=8, pady=2, sticky="ew")

    def _build_toolbar(self) -> None:
        self._toolbar = Toolbar(self)
        self._toolbar.grid(row=0, column=1, sticky="ew", padx=0, pady=0)

        self._toolbar.add_left("☰", command=self._toggle_sidebar)
        self._toolbar.add_left("←", command=self._go_back)
        self._toolbar.add_left("→", command=self._go_forward)

    def _build_content_area(self) -> None:
        self._content = ctk.CTkFrame(self)
        self._content.grid(row=1, column=1, sticky="nsew", padx=0, pady=0)
        self._content.grid_rowconfigure(0, weight=1)
        self._content.grid_columnconfigure(0, weight=1)

        self._navigator.set_container(self._content)

    def _build_status_bar(self) -> None:
        self._status_bar = ctk.CTkFrame(self, height=24, corner_radius=0)
        self._status_bar.grid(row=2, column=1, sticky="ew")
        self._status_bar.grid_propagate(False)

        self._status_bar.grid_columnconfigure(0, weight=0)
        self._status_bar.grid_columnconfigure(1, weight=1)
        self._status_bar.grid_columnconfigure(2, weight=0)

        self._connection_indicator = ConnectionIndicator(self._status_bar)
        self._connection_indicator.grid(row=0, column=0, padx=(4, 8), pady=2)

        self._status_label = ctk.CTkLabel(
            self._status_bar,
            text="Ready",
            font=("Segoe UI", 9),
        )
        self._status_label.grid(row=0, column=1, sticky="w", padx=4, pady=2)

        self._theme_mode_label = ctk.CTkLabel(
            self._status_bar,
            text="System",
            font=("Segoe UI", 9),
        )
        self._theme_mode_label.grid(row=0, column=2, padx=(4, 8), pady=2)

    def _bind_state(self) -> None:
        if not self._bindings:
            return

        self._bindings.bind_text(self._status_label, "connection_status")

    def add_sidebar_item(
        self,
        view_id: str,
        text: str,
        icon: str = "",
        command: Optional[Callable] = None,
    ) -> SidebarItem:
        if command is None:
            command = lambda vid=view_id: self._navigator.navigate(vid)

        item = SidebarItem(
            self._nav_frame,
            text=text,
            icon=icon,
            command=command,
        )
        item.grid(row=len(self._sidebar_items), column=0, sticky="ew", padx=4, pady=1)
        self._sidebar_items[view_id] = item

        self._events.subscribe("navigation.changed", lambda e, **d: self._update_sidebar_active(d.get("view_id", "")))
        return item

    def _update_sidebar_active(self, view_id: str) -> None:
        for vid, item in self._sidebar_items.items():
            item.set_active(vid == view_id)

    def _toggle_sidebar(self) -> None:
        self._sidebar_visible = not self._sidebar_visible
        if self._sidebar_visible:
            self._sidebar.grid()
        else:
            self._sidebar.grid_remove()

    def _toggle_theme(self) -> None:
        self._theme.toggle()
        self._theme_mode_label.configure(text=self._theme.mode.value)

    def _go_back(self) -> None:
        self._navigator.go_back()

    def _go_forward(self) -> None:
        self._navigator.go_forward()

    def _on_close(self) -> None:
        self._save_window_position()
        self._navigator.destroy_all()
        self.destroy()

    def _save_window_position(self) -> None:
        try:
            self._window_pos = (self.winfo_x(), self.winfo_y())
        except Exception:
            pass

    def set_status(self, text: str) -> None:
        self._status_label.configure(text=text)

    def set_connection_status(self, status: str) -> None:
        self._connection_indicator.set_status(status)

    def set_theme_label(self, text: str) -> None:
        self._theme_mode_label.configure(text=text)

    @property
    def navigator(self) -> Navigator:
        return self._navigator

    @property
    def theme(self) -> ThemeManager:
        return self._theme

    @property
    def events(self) -> EventDispatcher:
        return self._events

    @property
    def state(self) -> Optional[ClientState]:
        return self._state
