from __future__ import annotations

import logging
from typing import Any, Optional

import customtkinter as ctk

from app.client.client import JarvisClient
from app.client.ui.base_view import BaseView
from app.client.ui.theme import ThemeManager, ThemeMode
from app.client.ui.worker import AsyncWorker
from app.core.config import Config

logger = logging.getLogger("jarvis.client.ui.pages.settings")


class SettingsView(BaseView):
    def __init__(
        self,
        master: Any,
        client: Optional[JarvisClient] = None,
        worker: Optional[AsyncWorker] = None,
        config: Optional[Config] = None,
        **kwargs: Any,
    ):
        super().__init__(master, **kwargs)
        self._client = client
        self._worker = worker
        self._cfg = config or Config()
        self._build_ui()

    def _build_ui(self) -> None:
        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=0)
        self.grid_rowconfigure(2, weight=0)
        self.grid_rowconfigure(3, weight=0)
        self.grid_rowconfigure(4, weight=0)
        self.grid_rowconfigure(5, weight=1)
        self.grid_columnconfigure(0, weight=1)

        header = ctk.CTkLabel(
            self,
            text="Settings",
            font=("Segoe UI", 22, "bold"),
            anchor="w",
        )
        header.grid(row=0, column=0, sticky="w", padx=20, pady=(16, 8))

        conn_frame = ctk.CTkFrame(self)
        conn_frame.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 8))
        conn_frame.grid_columnconfigure(1, weight=1)

        conn_title = ctk.CTkLabel(
            conn_frame,
            text="Connection",
            font=("Segoe UI", 13, "bold"),
            anchor="w",
        )
        conn_title.grid(row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(8, 4))

        api_label = ctk.CTkLabel(conn_frame, text="API URL:", font=("Segoe UI", 11))
        api_label.grid(row=1, column=0, sticky="w", padx=12, pady=4)

        self._api_url_entry = ctk.CTkEntry(conn_frame, font=("Segoe UI", 11))
        self._api_url_entry.insert(0, self._cfg.CLIENT_API_URL)
        self._api_url_entry.grid(row=1, column=1, sticky="ew", padx=(0, 12), pady=4)

        ws_label = ctk.CTkLabel(conn_frame, text="WS URL:", font=("Segoe UI", 11))
        ws_label.grid(row=2, column=0, sticky="w", padx=12, pady=4)

        self._ws_url_entry = ctk.CTkEntry(conn_frame, font=("Segoe UI", 11))
        self._ws_url_entry.insert(0, self._cfg.CLIENT_WS_URL)
        self._ws_url_entry.grid(row=2, column=1, sticky="ew", padx=(0, 12), pady=4)

        theme_frame = ctk.CTkFrame(self)
        theme_frame.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 8))
        theme_frame.grid_columnconfigure(1, weight=1)

        theme_title = ctk.CTkLabel(
            theme_frame,
            text="Appearance",
            font=("Segoe UI", 13, "bold"),
            anchor="w",
        )
        theme_title.grid(row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(8, 4))

        theme_label = ctk.CTkLabel(theme_frame, text="Theme:", font=("Segoe UI", 11))
        theme_label.grid(row=1, column=0, sticky="w", padx=12, pady=4)

        self._theme_var = ctk.StringVar(value=self._theme.mode.value)
        self._theme_menu = ctk.CTkOptionMenu(
            theme_frame,
            values=["Dark", "Light", "System"],
            variable=self._theme_var,
            command=self._on_theme_change,
            font=("Segoe UI", 11),
        )
        self._theme_menu.grid(row=1, column=1, sticky="w", padx=(0, 12), pady=4)

        behavior_frame = ctk.CTkFrame(self)
        behavior_frame.grid(row=3, column=0, sticky="ew", padx=20, pady=(0, 8))
        behavior_frame.grid_columnconfigure(1, weight=1)

        behavior_title = ctk.CTkLabel(
            behavior_frame,
            text="Behavior",
            font=("Segoe UI", 13, "bold"),
            anchor="w",
        )
        behavior_title.grid(row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(8, 4))

        auto_reconnect_label = ctk.CTkLabel(
            behavior_frame,
            text="Auto-reconnect:",
            font=("Segoe UI", 11),
        )
        auto_reconnect_label.grid(row=1, column=0, sticky="w", padx=12, pady=4)

        self._auto_reconnect_var = ctk.StringVar(value="on" if self._cfg.CLIENT_AUTO_RECONNECT else "off")
        self._auto_reconnect_toggle = ctk.CTkSwitch(
            behavior_frame,
            text="",
            variable=self._auto_reconnect_var,
            onvalue="on",
            offvalue="off",
        )
        self._auto_reconnect_toggle.grid(row=1, column=1, sticky="w", padx=(0, 12), pady=4)

        animation_label = ctk.CTkLabel(
            behavior_frame,
            text="Animations:",
            font=("Segoe UI", 11),
        )
        animation_label.grid(row=2, column=0, sticky="w", padx=12, pady=4)

        self._animations_var = ctk.StringVar(value="on" if self._cfg.CLIENT_ANIMATIONS else "off")
        self._animations_toggle = ctk.CTkSwitch(
            behavior_frame,
            text="",
            variable=self._animations_var,
            onvalue="on",
            offvalue="off",
        )
        self._animations_toggle.grid(row=2, column=1, sticky="w", padx=(0, 12), pady=4)

        info_frame = ctk.CTkFrame(self)
        info_frame.grid(row=4, column=0, sticky="ew", padx=20, pady=(0, 8))
        info_frame.grid_columnconfigure(0, weight=1)

        info_title = ctk.CTkLabel(
            info_frame,
            text="About",
            font=("Segoe UI", 13, "bold"),
            anchor="w",
        )
        info_title.grid(row=0, column=0, sticky="w", padx=12, pady=(8, 4))

        version_label = ctk.CTkLabel(
            info_frame,
            text=f"JARVIS Desktop v{self._cfg.VERSION}",
            font=("Segoe UI", 11),
            anchor="w",
        )
        version_label.grid(row=1, column=0, sticky="w", padx=12, pady=(0, 8))

        self._status_label = ctk.CTkLabel(
            self,
            text="",
            font=("Segoe UI", 10),
        )
        self._status_label.grid(row=5, column=0, sticky="sw", padx=20, pady=(0, 4))

    def _on_theme_change(self, value: str) -> None:
        mode_map = {
            "Dark": ThemeMode.DARK,
            "Light": ThemeMode.LIGHT,
            "System": ThemeMode.SYSTEM,
        }
        mode = mode_map.get(value, ThemeMode.SYSTEM)
        self._theme.mode = mode

    def on_refresh(self) -> None:
        self._theme_var.set(self._theme.mode.value)
