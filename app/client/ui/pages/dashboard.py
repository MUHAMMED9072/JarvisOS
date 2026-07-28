from __future__ import annotations

import logging
from typing import Any, Optional

import customtkinter as ctk

from app.client.client import JarvisClient
from app.client.events import EventDispatcher
from app.client.state import ClientState
from app.client.ui.base_view import BaseView
from app.client.ui.models import ServerStatus
from app.client.ui.theme import ThemeManager
from app.client.ui.worker import AsyncWorker

logger = logging.getLogger("jarvis.client.ui.pages.dashboard")


class DashboardView(BaseView):
    def __init__(
        self,
        master: Any,
        client: Optional[JarvisClient] = None,
        worker: Optional[AsyncWorker] = None,
        **kwargs: Any,
    ):
        super().__init__(master, **kwargs)
        self._client = client
        self._worker = worker
        self._status = ServerStatus()
        self._build_ui()

    def _build_ui(self) -> None:
        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=0)
        self.grid_rowconfigure(2, weight=0)
        self.grid_rowconfigure(3, weight=0)
        self.grid_rowconfigure(4, weight=1)
        self.grid_columnconfigure(0, weight=1)

        header = ctk.CTkLabel(
            self,
            text="Dashboard",
            font=("Segoe UI", 22, "bold"),
            anchor="w",
        )
        header.grid(row=0, column=0, sticky="w", padx=20, pady=(16, 4))

        self._subtitle = ctk.CTkLabel(
            self,
            text="",
            font=("Segoe UI", 11),
            anchor="w",
        )
        self._subtitle.grid(row=1, column=0, sticky="w", padx=20, pady=(0, 12))

        info_frame = ctk.CTkFrame(self)
        info_frame.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 8))
        info_frame.grid_columnconfigure((0, 1, 2, 3), weight=1)

        self._status_label = ctk.CTkLabel(
            info_frame,
            text="Status: Disconnected",
            font=("Segoe UI", 13),
        )
        self._status_label.grid(row=0, column=0, padx=8, pady=8, sticky="w")

        self._version_label = ctk.CTkLabel(
            info_frame,
            text="",
            font=("Segoe UI", 11),
        )
        self._version_label.grid(row=0, column=1, padx=8, pady=8, sticky="w")

        self._clients_label = ctk.CTkLabel(
            info_frame,
            text="",
            font=("Segoe UI", 11),
        )
        self._clients_label.grid(row=0, column=2, padx=8, pady=8, sticky="w")

        actions_frame = ctk.CTkFrame(self)
        actions_frame.grid(row=3, column=0, sticky="ew", padx=20, pady=(0, 12))
        actions_frame.grid_columnconfigure((0, 1, 2, 3), weight=1)

        self._connect_btn = ctk.CTkButton(
            actions_frame,
            text="Connect",
            command=self._on_connect,
            width=110,
        )
        self._connect_btn.grid(row=0, column=0, padx=6, pady=8)

        self._reconnect_btn = ctk.CTkButton(
            actions_frame,
            text="Reconnect",
            command=self._on_reconnect,
            width=110,
        )
        self._reconnect_btn.grid(row=0, column=1, padx=6, pady=8)

        self._disconnect_btn = ctk.CTkButton(
            actions_frame,
            text="Disconnect",
            command=self._on_disconnect,
            width=110,
        )
        self._disconnect_btn.grid(row=0, column=2, padx=6, pady=8)

        stats_frame = ctk.CTkFrame(self)
        stats_frame.grid(row=4, column=0, sticky="nsew", padx=20, pady=(0, 16))
        stats_frame.grid_rowconfigure(0, weight=1)
        stats_frame.grid_columnconfigure((0, 1, 2, 3), weight=1)

        self._skills_card = self._make_stat_card(stats_frame, "Skills", "0", 0)
        self._plugins_card = self._make_stat_card(stats_frame, "Plugins", "0", 1)
        self._memory_card = self._make_stat_card(stats_frame, "Memory", "0", 2)
        self._convos_card = self._make_stat_card(stats_frame, "Conversations", "0", 3)

        self._error_label = ctk.CTkLabel(
            self,
            text="",
            font=("Segoe UI", 10),
            text_color="#ff5252",
        )
        self._error_label.grid(row=5, column=0, sticky="w", padx=20, pady=(0, 4))

    def _make_stat_card(
        self,
        parent: Any,
        label: str,
        value: str,
        col: int,
    ) -> ctk.CTkFrame:
        card = ctk.CTkFrame(parent)
        card.grid(row=0, column=col, sticky="nsew", padx=4, pady=4)
        card.grid_rowconfigure(0, weight=1)
        card.grid_columnconfigure(0, weight=1)

        val = ctk.CTkLabel(card, text=value, font=("Segoe UI", 28, "bold"))
        val.grid(row=0, column=0, padx=12, pady=(12, 0))

        lbl = ctk.CTkLabel(card, text=label, font=("Segoe UI", 10))
        lbl.grid(row=1, column=0, padx=12, pady=(0, 12))

        card._value_label = val
        return card

    def on_refresh(self) -> None:
        if self._client:
            self._update_status_display()

    def _update_status_display(self) -> None:
        if not self._client:
            return
        connected = self._client.state.connection_status.value
        self._status_label.configure(text=f"Status: {connected.capitalize()}")
        if connected == "connected":
            self._connect_btn.configure(state="disabled")
            self._reconnect_btn.configure(state="normal")
            self._disconnect_btn.configure(state="normal")
        elif connected == "disconnected":
            self._connect_btn.configure(state="normal")
            self._reconnect_btn.configure(state="disabled")
            self._disconnect_btn.configure(state="disabled")
        else:
            self._connect_btn.configure(state="disabled")
            self._reconnect_btn.configure(state="disabled")
            self._disconnect_btn.configure(state="disabled")

    def _set_error(self, msg: str) -> None:
        self._error_label.configure(text=msg)
        if msg:
            self.after(5000, lambda: self._error_label.configure(text=""))

    def _on_connect(self) -> None:
        if not self._worker or not self._client:
            return
        self._set_error("")

        async def do_connect():
            ok = await self._client.connect()
            return ok

        def done(result: Any, error: str = "") -> None:
            if error or not result:
                self._set_error(f"Connection failed: {error or 'unknown error'}")
            self._update_status_display()

        self._worker.run(do_connect(), done)

    def _on_reconnect(self) -> None:
        if not self._worker or not self._client:
            return
        self._set_error("")

        async def do_reconnect():
            ok = await self._client.reconnect()
            return ok

        def done(result: Any, error: str = "") -> None:
            if error or not result:
                self._set_error(f"Reconnect failed: {error or 'unknown error'}")
            self._update_status_display()

        self._worker.run(do_reconnect(), done)

    def _on_disconnect(self) -> None:
        if not self._worker or not self._client:
            return

        async def do_disconnect():
            await self._client.disconnect()

        def done(result: Any = None, error: str = "") -> None:
            self._update_status_display()

        self._worker.run(do_disconnect(), done)

    def update_stats(
        self,
        skills: int = 0,
        plugins: int = 0,
        memory: int = 0,
        conversations: int = 0,
    ) -> None:
        self._skills_card._value_label.configure(text=str(skills))
        self._plugins_card._value_label.configure(text=str(plugins))
        self._memory_card._value_label.configure(text=str(memory))
        self._convos_card._value_label.configure(text=str(conversations))

    def update_connection_status(self, connected: bool) -> None:
        self._update_status_display()
